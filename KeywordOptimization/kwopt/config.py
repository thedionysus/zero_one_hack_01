"""Central settings, all overridable via environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # --- Sybilion API ---
    api_base: str = os.environ.get("SYBILION_API_BASE", "https://api.sybilion.dev")
    api_token: str | None = os.environ.get("SYBILION_API_TOKEN")
    poll_seconds: int = int(os.environ.get("KWOPT_POLL_SECONDS", "10"))
    max_wait_minutes: int = int(os.environ.get("KWOPT_MAX_WAIT_MIN", "30"))

    # --- Forecast request defaults ---
    horizon: int = int(os.environ.get("KWOPT_HORIZON", "3"))
    recency_factor: float = float(os.environ.get("KWOPT_RECENCY", "0.6"))
    driver_limit: int = int(os.environ.get("KWOPT_DRIVER_LIMIT", "1000"))
    strictly_positive: bool = os.environ.get("KWOPT_STRICT_POS", "1") == "1"

    # --- Scoring weights:  S(K) = M - lam_w*W + lam_c*C + lam_s*stability + lam_i*inverted ---
    lam_w: float = float(os.environ.get("KWOPT_LAM_W", "5.0"))   # penalty per dead driver
    lam_c: float = float(os.environ.get("KWOPT_LAM_C", "10.0"))  # reward per covered category
    lam_s: float = float(os.environ.get("KWOPT_LAM_S", "0.0"))   # reward for stable (robust) drivers
    lam_i: float = float(os.environ.get("KWOPT_LAM_I", "0.0"))   # reward per important inverted driver

    # --- Budget / stopping (unlimited credit -> guard time & concurrency, not euros) ---
    max_forecasts: int = int(os.environ.get("KWOPT_MAX_FORECASTS", "20"))
    max_concurrency: int = int(os.environ.get("KWOPT_CONCURRENCY", "4"))
    max_wall_minutes: float = float(os.environ.get("KWOPT_MAX_WALL_MIN", "0"))  # 0 => no wall limit
    shortlist_m: int = int(os.environ.get("KWOPT_SHORTLIST_M", "5"))
    skip_screen: bool = os.environ.get("KWOPT_SKIP_SCREEN", "0") == "1"  # credit-rich: forecast all
    target_mape: float = float(os.environ.get("KWOPT_TARGET_MAPE", "0"))
    no_improve_patience: int = int(os.environ.get("KWOPT_PATIENCE", "3"))

    # --- Cache ---
    db_path: str = os.environ.get("KWOPT_DB", "kwopt_cache.sqlite")

    # --- Proposer ---
    proposer: str = os.environ.get("KWOPT_PROPOSER", "static")  # "static" | "llm"
    llm_model: str = os.environ.get("KWOPT_LLM_MODEL", "claude-sonnet-4-6")

    def require_token(self) -> str:
        if not self.api_token:
            raise RuntimeError("Set SYBILION_API_TOKEN in the environment.")
        return self.api_token


SETTINGS = Settings()
