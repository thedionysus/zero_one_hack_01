"""Driver parsing + objectives.

VERIFIED against the live API (2026-05): the two layers return DIFFERENT things.
  /drivers (cheap, sync)  -> data.drivers[] = {driver_name, score(0-1 relevance), source}
                             NO importance / direction / correlation.
  forecast external_signals.json -> {uuid: {importance(0-100), direction, pearson_correlation}}.

So:
  - cheap screen ranks keyword sets by candidate RELEVANCE + diversity  -> screen_candidates()
  - true importance / direction / inversion / dead-drivers come ONLY from a full forecast.
  - true objective is 12m MAPE (minimize).
"""
from __future__ import annotations

from typing import Any, Iterable

from ..schemas import DriverEntry, ScreenResult


def classify_driver(name: str) -> str:
    n = name.lower()
    if any(w in n for w in ["risk", "uncertainty", "geopolitical", "conflict", "war", "crisis"]):
        return "risk"
    if any(w in n for w in ["energy", "ppi", "producer price", "commodity", "commodities", "oil", "gas",
                            "freight", "shipping", "transport", "price"]):
        return "cost"
    if any(w in n for w in ["equities", "equity", "stock", "financial", "credit", "interest",
                            "currency", "fx", "dollar", "reserve"]):
        return "finance"
    if any(w in n for w in ["labor", "labour", "employment", "unemployment", "job opening", "job openings",
                            "vacanc", "wage", "workforce", "participation", "quit rate", "jolts"]):
        return "labor"
    if any(w in n for w in ["manufacturing", "industrial", "industry", "factory", "durable", "automotive",
                            "electronics", "semiconductor", "machine tool", "capex", "capital", "services"]):
        return "demand"
    if any(w in n for w in ["supply", "logistics", "inventory", "shipment", "supplier", "port"]):
        return "supply_chain"
    return "other"


# ----------------- /drivers (candidate, relevance) -----------------
def parse_candidates(payload: dict) -> list[DriverEntry]:
    """Parse the synchronous /drivers response: data.drivers[] with score + source."""
    data = payload.get("data", payload)
    rows = data.get("drivers", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        rows = []
    out = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        name = str(it.get("driver_name") or it.get("name") or "Unknown")
        out.append(DriverEntry(name=name, category=classify_driver(name),
                               score=float(it.get("score", 0.0)), source=str(it.get("source", ""))))
    return out


def screen_candidates(cands: list[DriverEntry], lam_c: float = 10.0, lam_src: float = 5.0) -> ScreenResult:
    """Cheap screen S(K) from /drivers: relevance mass + category & source diversity.

    NOTE: this is a RELEVANCE proxy, not importance. Only full-forecast MAPE is truth.
    """
    rel_mass = sum(d.score for d in cands)
    mean = rel_mass / len(cands) if cands else 0.0
    coverage = len({d.category for d in cands})
    src = len({d.source for d in cands if d.source})
    score = rel_mass * 10.0 + lam_c * coverage + lam_src * src   # scale relevance into a comparable range
    return ScreenResult(score=score, n_returned=len(cands), coverage=coverage,
                        relevance_mass=rel_mass, mean_score=mean, source_diversity=src,
                        drivers=sorted(cands, key=lambda d: d.score, reverse=True))


# ----------------- forecast external_signals (importance) -----------------
def _iter_numbers(obj: Any) -> Iterable[float]:
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_numbers(v)


def _nested(d: Any, key: str, agg: str, default: float = 0.0) -> float:
    try:
        v = d.get(key)
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            ov = v.get("overall")
            if isinstance(ov, dict) and agg in ov:
                return float(ov[agg])
            leaves = list(_iter_numbers(v))
            return sum(leaves) / len(leaves) if leaves else default
    except Exception:
        return default
    return default


def _stability(item: dict) -> float:
    parts = []
    for key in ("importance", "direction", "pearson_correlation"):
        v = item.get(key)
        if isinstance(v, dict) and isinstance(v.get("overall"), dict):
            ov = v["overall"]
            lo, hi, mean = ov.get("min"), ov.get("max"), ov.get("mean")
            if lo is not None and hi is not None:
                spread = abs(float(hi) - float(lo))
                scale = max(abs(float(mean)) if mean is not None else 1.0, 1.0)
                parts.append(max(0.0, 1.0 - spread / scale))
    return sum(parts) / len(parts) if parts else 1.0


def parse_signals(payload: dict) -> list[DriverEntry]:
    """Parse a forecast's external_signals.json: uuid -> {importance, direction, pearson}."""
    data = payload.get("data", payload)
    entries = list(data.values()) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    out = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        name = str(item.get("driver_name") or item.get("name") or "Unknown")
        out.append(DriverEntry(
            name=name, category=classify_driver(name),
            importance=_nested(item, "importance", "max", 0.0),
            direction=_nested(item, "direction", "mean", 0.0),
            correlation=_nested(item, "pearson_correlation", "mean", 0.0) or _nested(item, "correlation", "mean", 0.0),
            stability=_stability(item),
        ))
    return out


def analyze_signals(signals: list[DriverEntry]) -> ScreenResult:
    """Post-forecast importance analysis: used_mass, dead, inverted, stability (reporting + tuning)."""
    used = [d for d in signals if d.used]
    used_mass = sum(d.importance for d in used)
    dead = len(signals) - len(used)
    coverage = len({d.category for d in used})
    inverted = sum(1 for d in used if d.inverted)
    mstab = (sum(d.stability * d.importance for d in used) / used_mass) if (used and used_mass) else 0.0
    return ScreenResult(score=used_mass, n_returned=len(signals), coverage=coverage,
                        used_mass=used_mass, dead_count=dead, n_used=len(used),
                        inverted_used=inverted, mean_stability=mstab,
                        drivers=sorted(signals, key=lambda d: d.importance, reverse=True))


def robust_drivers(screens: list[ScreenResult], min_fraction: float = 0.5):
    from collections import defaultdict
    seen = defaultdict(list)
    for sr in screens:
        for d in sr.drivers:
            seen[d.name].append(d.score or d.importance)
    n = max(len(screens), 1)
    rows = [(name, len(v), sum(v) / len(v)) for name, v in seen.items() if len(v) / n >= min_fraction]
    return sorted(rows, key=lambda r: (r[1], r[2]), reverse=True)


def mape_12m(backtest_metrics: dict) -> float:
    data = backtest_metrics.get("data", backtest_metrics)
    for window in ("12m", "24m", "60m", "6m"):
        try:
            return float(data[window]["metrics"]["MAPE"])
        except Exception:
            continue
    raise KeyError("no MAPE found in backtest_metrics")
