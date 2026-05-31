"""Export the engine's own (context -> best_keywords) pairs. These are BOTH the few-shot corpus
for ExperienceProposer and the training set for an eventual local fine-tune.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..cache.store import Store
from ..corpus.targets import load_manifest


def export_pairs(store: Store, manifest_path: Path | None, out_path: Path) -> list[dict]:
    meta = {}
    if manifest_path and manifest_path.exists():
        for t in load_manifest(manifest_path):
            meta[t.target_id] = {"title": t.title, "description": t.description}
    pairs = []
    for b in store.all_best():
        m = meta.get(b["target_id"], {})
        pairs.append({
            "target_id": b["target_id"],
            "title": m.get("title", b["target_id"]),
            "description": m.get("description", ""),
            "keywords": b["keywords"],
            "mape_12m": b["mape_12m"],
        })
    out_path.write_text(json.dumps(pairs, indent=2))
    return pairs
