"""Generate submit_forecast payloads + a manifest skeleton for the bake-off.

Writes one payload JSON per (fertilizer, variant) cell and an empty manifest
the operator fills in as jobs are submitted. Pure stdlib; no network calls.
"""
import json
import os

from lib import forecast_scoring as fs

PROCESSED = "data/processed/dataset1"
BAKEOFF = "data/forecast_exploration/bakeoff"
LAST_REAL_DATE = "2026-03-01"
REFERENCE_JOBS = {
    "mop_drivers_D3_backtest_false": "1517c8d1-3ddf-479c-aaf5-e062fba00fa6",
    "wti_D4_reference": "b6127f17-e68e-4efe-ad7a-86fa292d9027",
    "urea_runA_sh6": "59b5874f-a40f-465c-b903-b33c5a17dcb1",
}


def load_series(slug):
    with open(os.path.join(PROCESSED, f"{slug}.json")) as fh:
        return json.load(fh)


def main():
    payloads_dir = os.path.join(BAKEOFF, "payloads")
    os.makedirs(payloads_dir, exist_ok=True)
    cells = {}
    for slug in fs.FERTILIZERS:
        series = load_series(slug)
        cells[slug] = {}
        for variant in fs.VARIANTS:
            payload = fs.build_cell_payload(slug, series, variant)
            path = os.path.join(payloads_dir, f"{slug}__{variant}.json")
            with open(path, "w") as fh:
                json.dump(payload, fh)
            cells[slug][variant] = {"job_id": None, "status": "pending",
                                    "eur_cost": None, "reused": False}
    manifest = {
        "config": {"soft_horizon": 12, "backtest": True,
                   "accept_stale_latest_data": True,
                   "recency_factor": {"ON": 0.0, "MID": 0.3, "OFF": None}},
        "last_real_date": LAST_REAL_DATE,
        "reference_jobs": REFERENCE_JOBS,
        "cells": cells,
    }
    with open(os.path.join(BAKEOFF, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Wrote {len(fs.FERTILIZERS) * len(fs.VARIANTS)} payloads + manifest skeleton")


if __name__ == "__main__":
    main()
