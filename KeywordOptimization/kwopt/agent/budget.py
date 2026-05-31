"""Resource guard. With unlimited credit the scarce resources are WALL-CLOCK and Sybilion's
concurrent-job cap — not euros. This guards run count, concurrency, and optional wall-time.
"""
from __future__ import annotations

import time


class Budget:
    def __init__(
        self,
        max_forecasts: int = 1000,
        max_concurrency: int = 4,
        max_wall_seconds: float | None = None,
        target_mape: float = 0.0,
        patience: int = 3,
    ):
        self.max_forecasts = max_forecasts
        self.max_concurrency = max_concurrency
        self.max_wall_seconds = max_wall_seconds
        self.target_mape = target_mape
        self.patience = patience
        self.spent_forecasts = 0
        self.spent_cents = 0           # tracked for info only
        self.best_mape = float("inf")
        self._no_improve = 0
        self._t0 = time.time()

    def remaining_forecasts(self) -> int:
        return max(self.max_forecasts - self.spent_forecasts, 0)

    def can_forecast(self) -> bool:
        if self.remaining_forecasts() <= 0:
            return False
        if self.max_wall_seconds and (time.time() - self._t0) > self.max_wall_seconds:
            return False
        return True

    def record_forecast(self, eur_cents: int, mape: float) -> None:
        self.spent_forecasts += 1
        self.spent_cents += int(eur_cents)
        if mape < self.best_mape - 1e-9:
            self.best_mape = mape
            self._no_improve = 0
        else:
            self._no_improve += 1

    def should_stop(self) -> bool:
        if not self.can_forecast():
            return True
        if self.target_mape and self.best_mape <= self.target_mape:
            return True
        if self._no_improve >= self.patience:
            return True
        return False

    def summary(self) -> dict:
        return {
            "forecasts": self.spent_forecasts,
            "eur": round(self.spent_cents / 100, 2),
            "wall_s": round(time.time() - self._t0, 1),
            "best_mape": None if self.best_mape == float("inf") else round(self.best_mape, 3),
        }
