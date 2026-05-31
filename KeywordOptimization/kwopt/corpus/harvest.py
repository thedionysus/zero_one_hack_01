"""Run the optimizer across a diverse target set and accumulate the engine's own best results.

This is the experience the engine later 'uses itself' from (ExperienceProposer / distillation).
"""
from __future__ import annotations

from pathlib import Path

from ..agent.orchestrator import optimize
from ..agent.proposer import StaticProposer
from ..clients.sybilion import SybilionClient
from ..cache.store import Store
from ..config import Settings
from .targets import load_manifest


def harvest(manifest_path: Path, seeds: dict[str, list[str]], cfg: Settings, rounds: int = 2) -> list[dict]:
    client = SybilionClient()
    store = Store(cfg.db_path)
    out = []
    for target in load_manifest(manifest_path):
        print(f"\n### target: {target.target_id}")
        proposer = StaticProposer(seeds)
        res = optimize(target, proposer, client, store, cfg, rounds=rounds)
        out.append({
            "target_id": target.target_id, "title": target.title, "description": target.description,
            "best_keywords": res.best_keywords, "best_mape": res.best_mape,
            "baseline_mape": res.baseline_mape, "lift_pp": res.lift_pp,
        })
        print(f"  best MAPE={res.best_mape} (baseline {res.baseline_mape}, lift {res.lift_pp})")
    return out
