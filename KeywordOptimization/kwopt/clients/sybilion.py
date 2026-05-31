"""Sybilion REST client. The ONLY place that talks to the API.

Grounded in the real run + docs:
- POST /api/v1/drivers   : synchronous, cheap screening (importance + direction)
- POST /api/v1/forecasts : async; returns 202 {job_id, poll_url}
- GET  /api/v1/forecasts/{id} : poll until status == completed
- GET  .../artifacts/{name}   : stream one of the 5 artifacts
- GET  /api/v1/me        : balance check
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import requests

from ..config import Settings, SETTINGS
from ..schemas import Filters, Metadata, TargetSpec


class SybilionError(RuntimeError):
    pass


class SybilionClient:
    def __init__(self, settings: Settings = SETTINGS):
        self.s = settings
        self._token = settings.require_token()

    # ---- low level ----
    def _headers(self, request_id: Optional[str] = None) -> dict:
        h = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        if request_id:
            h["X-Request-ID"] = request_id
        return h

    def _url(self, path: str) -> str:
        return f"{self.s.api_base}{path}"

    # ---- account ----
    def me(self) -> dict:
        r = requests.get(self._url("/api/v1/me"), headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    # ---- drivers (SYNC, cheap screening) ----
    def drivers(
        self,
        meta: Metadata,
        *,
        recency: float,
        filters: Filters,
        series: Optional[dict[str, float]] = None,
        request_id: Optional[str] = None,
    ) -> dict:
        body: dict[str, Any] = {
            "version": "v1",
            "recency_factor": recency,
            "timeseries_metadata": meta.to_payload(),
            "filters": filters.to_payload(),
        }
        if series:
            body["timeseries"] = series
        rid = request_id or str(uuid.uuid4())
        r = requests.post(
            self._url("/api/v1/drivers"),
            headers=self._headers(rid),
            json=body,
            timeout=120,
        )
        if r.status_code == 402:
            raise SybilionError("insufficient credits for /drivers")
        if r.status_code == 503:
            raise SybilionError("drivers feature not enabled for this account")
        r.raise_for_status()
        return r.json()

    # ---- forecasts (ASYNC, expensive) ----
    def submit_forecast(self, body: dict) -> str:
        r = requests.post(self._url("/api/v1/forecasts"), headers=self._headers(), json=body, timeout=120)
        r.raise_for_status()
        payload = r.json()
        for key in ("job_id", "id", "forecast_id"):
            if payload.get(key):
                return str(payload[key])
        raise SybilionError(f"no job id in submit response: {json.dumps(payload)[:500]}")

    def _status_payload(self, raw: dict) -> dict:
        if isinstance(raw.get("data"), dict) and "status" in raw["data"]:
            return raw["data"]
        return raw

    def poll(self, job_id: str) -> dict:
        """Block until the job settles; return the final job payload."""
        url = self._url(f"/api/v1/forecasts/{job_id}")
        deadline = time.time() + self.s.max_wait_minutes * 60
        last = None
        while True:
            r = requests.get(url, headers=self._headers(), timeout=120)
            r.raise_for_status()
            job = self._status_payload(r.json())
            status = str(job.get("status", "unknown")).lower()
            if status != last:
                print(f"  [job {job_id[:8]}] {status}")
                last = status
            if status in {"completed", "complete", "succeeded", "success"}:
                return job
            if status in {"failed", "canceled", "cancelled", "error"}:
                raise SybilionError(f"forecast {job_id} ended as {status}: {job.get('pipeline_error')}")
            if time.time() > deadline:
                raise TimeoutError(f"forecast {job_id} timed out after {self.s.max_wait_minutes} min")
            time.sleep(self.s.poll_seconds)

    def get_artifact(self, job_id: str, name: str) -> dict:
        url = self._url(f"/api/v1/forecasts/{job_id}/artifacts/{name}")
        r = requests.get(url, headers=self._headers(), timeout=120)
        r.raise_for_status()
        return r.json()

    def wait_forecast(self, body: dict, want: tuple[str, ...] = ("backtest_metrics.json", "external_signals.json", "forecast.json")) -> dict:
        """Submit -> poll -> fetch the artifacts we score on. Returns {job, artifacts, eur_cents}."""
        job_id = self.submit_forecast(body)
        job = self.poll(job_id)
        available = {a["name"] for a in job.get("artifacts", [])}
        artifacts = {name: self.get_artifact(job_id, name) for name in want if name in available}
        return {
            "job_id": job_id,
            "job": job,
            "artifacts": artifacts,
            "eur_cents": int(job.get("eur_cents_final", 0)),
        }


def build_forecast_body(target: TargetSpec, keywords: list[str]) -> dict:
    """Forecast request body (reuses the shape proven in the real run: soft_horizon, strictly_positive)."""
    meta = Metadata(title=target.title, description=target.description, keywords=keywords)
    return {
        "pipeline_version": "v1",
        "frequency": "monthly",
        "soft_horizon": target.horizon,
        "recency_factor": target.recency_factor,
        "backtest": True,
        "strictly_positive": target.strictly_positive,
        "timeseries_metadata": meta.to_payload(),
        "filters": target.filters.to_payload(),
        "timeseries": target.timeseries,
    }
