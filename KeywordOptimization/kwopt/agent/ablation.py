"""Keyword attribution via ablation on the CHEAP /drivers endpoint.

Drop a keyword (or cluster), re-screen, watch S move:
  drops a lot  -> keep   |   ~no change -> prune   |   improves -> remove (noise)
"""
from __future__ import annotations

from ..core.scoring import classify_driver, parse_candidates, screen_candidates
from ..schemas import Filters, Metadata, TargetSpec


def ablate(client, target: TargetSpec, keywords: list[str], lam_w: float, lam_c: float,
           group_by_cluster: bool = True) -> list[dict]:
    """Return per-removal delta-S, cheaply (one /drivers call per removal). No forecasts."""
    def screen(kws: list[str]) -> float:
        payload = client.drivers(
            Metadata(target.title, target.description, kws),
            recency=target.recency_factor, filters=target.filters,
            series=target.timeseries,
        )
        return screen_candidates(parse_candidates(payload), lam_c).score

    base = screen(keywords)
    results = []

    if group_by_cluster:
        clusters = sorted({classify_driver(k) for k in keywords})
        for cl in clusters:
            pruned = [k for k in keywords if classify_driver(k) != cl]
            if not pruned or len(pruned) == len(keywords):
                continue
            s = screen(pruned)
            results.append({"removed": f"cluster:{cl}", "delta_S": s - base, "verdict": _verdict(s - base)})
    else:
        for i, k in enumerate(keywords):
            pruned = keywords[:i] + keywords[i + 1:]
            s = screen(pruned)
            results.append({"removed": k, "delta_S": s - base, "verdict": _verdict(s - base)})

    return sorted(results, key=lambda r: r["delta_S"])  # most damaging removals first


def _verdict(delta_s: float, eps: float = 1.0) -> str:
    # delta_S = S(without) - S(with). Negative => removing hurt => keyword was valuable.
    if delta_s < -eps:
        return "keep (earned drivers)"
    if delta_s > eps:
        return "remove (noise)"
    return "prune (dead weight)"
