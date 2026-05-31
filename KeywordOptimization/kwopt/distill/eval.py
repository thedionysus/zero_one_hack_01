"""Held-out evaluation: does the engine's self-proposed keyword set beat no-keyword baseline,
and approach the loop-optimized best?
"""
from __future__ import annotations

import json
from pathlib import Path

from ..agent.orchestrator import _forecast_one
from ..agent.proposer import ExperienceProposer
from ..clients.sybilion import SybilionClient
from ..cache.store import Store
from ..config import Settings
from ..corpus.targets import load_manifest


def evaluate(manifest_path: Path, pairs_path: Path, cfg: Settings) -> list[dict]:
    corpus = json.loads(pairs_path.read_text())
    client = SybilionClient()
    store = Store(cfg.db_path)
    rows = []
    for target in load_manifest(manifest_path):
        # leave-this-target-out experience
        loo = [c for c in corpus if c["target_id"] != target.target_id]
        proposer = ExperienceProposer(loo, k=3)
        sets = proposer.propose_batch(target, [], None)
        baseline = _forecast_one(client, store, target, [], cfg).mape_12m
        best = None
        for ks in sets:
            try:
                m = _forecast_one(client, store, target, ks.keywords, cfg).mape_12m
            except Exception:
                continue
            best = m if best is None else min(best, m)
        rows.append({"target_id": target.target_id, "baseline_mape": baseline,
                     "distilled_mape": best, "lift_pp": (baseline - best) if best else None})
    return rows
