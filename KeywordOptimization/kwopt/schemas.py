"""Typed data structures shared across the engine (stdlib dataclasses, no heavy deps)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Metadata:
    title: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        m: dict = {"title": self.title}
        if self.description:
            m["description"] = self.description
        if self.keywords:
            m["keywords"] = self.keywords
        return m


@dataclass
class Filters:
    regions: list[int] = field(default_factory=list)
    categories: list[int] = field(default_factory=list)
    limit: int = 1000

    def to_payload(self) -> dict:
        p: dict = {"limit": self.limit}
        if self.regions:
            p["regions"] = self.regions
        if self.categories:
            p["categories"] = self.categories
        return p


@dataclass
class TargetSpec:
    """The thing we optimize keywords for."""
    target_id: str
    title: str
    description: str
    timeseries: dict[str, float]            # YYYY-MM-DD -> value
    filters: Filters = field(default_factory=Filters)
    recency_factor: float = 0.6
    horizon: int = 3
    strictly_positive: bool = True


@dataclass
class DriverEntry:
    name: str
    importance: float = 0.0  # 0-100, FORECAST external_signals only (post feature-selection)
    direction: float = 0.0   # signed, [-1,1], forecast only
    correlation: float = 0.0  # signed, [-1,1], forecast only
    category: str = "other"
    stability: float = 1.0
    score: float = 0.0        # 0-1 relevance, /drivers candidate endpoint only
    source: str = ""          # /drivers only (e.g. general_market, sector, commodity)

    @property
    def used(self) -> bool:
        return self.importance > 0.0

    @property
    def inverted(self) -> bool:
        return self.direction < 0.0


@dataclass
class ScreenResult:
    score: float                 # the screen objective S(K)
    n_returned: int
    coverage: int                # distinct categories among candidates
    relevance_mass: float = 0.0  # sum of /drivers relevance scores
    mean_score: float = 0.0      # mean /drivers relevance
    source_diversity: int = 0    # distinct sources
    # forecast-only fields (populated only when analyzing external_signals):
    used_mass: float = 0.0
    dead_count: int = 0
    n_used: int = 0
    inverted_used: int = 0
    mean_stability: float = 1.0
    drivers: list = field(default_factory=list)


@dataclass
class ForecastResult:
    job_id: str
    mape_12m: float
    eur_cents: int
    artifacts: dict          # name -> parsed json (or hrefs)


@dataclass
class KeywordSet:
    keywords: list[str]
    origin: str = "seed"     # "seed" | "mutation" | "llm"


@dataclass
class Attempt:
    target_id: str
    attempt_no: int
    keywords: list[str]
    screen_score: Optional[float] = None
    mape_12m: Optional[float] = None
