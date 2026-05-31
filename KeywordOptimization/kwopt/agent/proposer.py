"""Keyword proposers.

StaticProposer  — runs offline (no LLM key). Yields seed sets, then ablation mutations of the
                  current best (drop a cluster, drop one keyword). Good for Phase 1/2.
LLMProposerAdapter — wraps clients.llm.LLMProposer to fit the same interface.

Interface:  propose_batch(target, history, best_keywords) -> list[KeywordSet]
"""
from __future__ import annotations

from typing import Optional

from ..core.scoring import classify_driver  # reuse cluster idea via keyword text
from ..schemas import KeywordSet, TargetSpec


def _keyword_cluster(k: str) -> str:
    return classify_driver(k)  # cheap cluster tag from the keyword text itself


class StaticProposer:
    def __init__(self, seeds: dict[str, list[str]]):
        # seeds: {set_name: [keywords...]}
        self.seeds = seeds
        self._emitted_seeds = False

    def propose_batch(self, target: TargetSpec, history: list[dict],
                      best_keywords: Optional[list[str]]) -> list[KeywordSet]:
        # Round 1: emit all seed sets.
        if not self._emitted_seeds:
            self._emitted_seeds = True
            return [KeywordSet(list(v), origin="seed") for v in self.seeds.values()]

        # Later rounds: ablate the current best.
        if not best_keywords:
            return []
        out: list[KeywordSet] = []

        # (a) drop each cluster as a group
        clusters = sorted({_keyword_cluster(k) for k in best_keywords})
        for cl in clusters:
            pruned = [k for k in best_keywords if _keyword_cluster(k) != cl]
            if 0 < len(pruned) < len(best_keywords):
                out.append(KeywordSet(pruned, origin="mutation"))

        # (b) drop each keyword individually
        for i in range(len(best_keywords)):
            pruned = best_keywords[:i] + best_keywords[i + 1:]
            if pruned:
                out.append(KeywordSet(pruned, origin="mutation"))
        return out


class LLMProposerAdapter:
    def __init__(self, backend):
        self.backend = backend

    def propose_batch(self, target: TargetSpec, history: list[dict],
                      best_keywords: Optional[list[str]]) -> list[KeywordSet]:
        kws = self.backend.propose(target.title, target.description, history)
        return [KeywordSet(kws, origin="llm")] if kws else []


def _tokens(text: str) -> set[str]:
    return {w for w in text.lower().replace(",", " ").split() if len(w) > 2}


class ExperienceProposer:
    """The engine 'uses itself': for a new target, retrieve the most similar PAST targets the
    engine already optimized and propose their best keyword sets (and a merged union).

    `corpus` = [{target_id, title, description, keywords (best), mape_12m}] exported from prior runs.
    This is the immediate, runnable form of distillation (retrieval/few-shot from own results);
    a fine-tuned local model can later replace this with the same interface.
    """
    def __init__(self, corpus: list[dict], k: int = 3, fallback: Optional[object] = None):
        self.corpus = [c for c in corpus if c.get("keywords")]
        self.k = k
        self.fallback = fallback
        self._done = False

    def _rank(self, target: TargetSpec) -> list[dict]:
        q = _tokens(f"{target.title} {target.description}")
        scored = []
        for c in self.corpus:
            ct = _tokens(f"{c.get('title','')} {c.get('description','')}")
            sim = len(q & ct) / (len(q | ct) or 1)   # Jaccard
            scored.append((sim, c))
        return [c for _s, c in sorted(scored, key=lambda t: t[0], reverse=True)]

    def propose_batch(self, target: TargetSpec, history: list[dict],
                      best_keywords: Optional[list[str]]) -> list[KeywordSet]:
        if self._done:
            # later rounds: hand off to fallback (e.g. ablation/LLM) to refine
            return self.fallback.propose_batch(target, history, best_keywords) if self.fallback else []
        self._done = True
        nearest = self._rank(target)[: self.k]
        out = [KeywordSet(c["keywords"], origin="experience") for c in nearest]
        # merged union of nearest neighbours' keywords, capped at 20
        merged: list[str] = []
        for c in nearest:
            for kw in c["keywords"]:
                if kw not in merged and len(merged) < 20:
                    merged.append(kw)
        if merged:
            out.append(KeywordSet(merged, origin="experience-merge"))
        return out
