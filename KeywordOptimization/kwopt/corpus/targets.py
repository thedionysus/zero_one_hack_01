"""Load a DIVERSE set of targets from a manifest (sheet 5: diversity => generalization).

manifest.json:
[
  {"target_id":"robot_imports_us","title":"...","description":"...","csv":"robot_imports_sybilion.csv"},
  {"target_id":"sunscreen_de","title":"...","description":"...","csv":"sunscreen_de.csv",
   "filters":{"limit":1000,"regions":[3]}}
]
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..config import SETTINGS
from ..schemas import Filters, TargetSpec


def _read_csv(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    with path.open() as f:
        for row in csv.DictReader(f):
            d = str(row["date"]).strip()[:10]
            out[d[:8] + "01"] = float(row["value"])
    return dict(sorted(out.items()))


def load_manifest(path: Path) -> list[TargetSpec]:
    base = path.parent
    items = json.loads(path.read_text())
    targets = []
    for it in items:
        f = it.get("filters", {})
        targets.append(TargetSpec(
            target_id=it["target_id"], title=it["title"], description=it.get("description", ""),
            timeseries=_read_csv(base / it["csv"]),
            filters=Filters(regions=f.get("regions", []), categories=f.get("categories", []),
                            limit=f.get("limit", SETTINGS.driver_limit)),
            recency_factor=it.get("recency_factor", SETTINGS.recency_factor),
            horizon=it.get("horizon", SETTINGS.horizon),
            strictly_positive=it.get("strictly_positive", SETTINGS.strictly_positive),
        ))
    return targets
