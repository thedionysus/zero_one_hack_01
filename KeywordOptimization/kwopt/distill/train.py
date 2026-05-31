"""Fine-tune a small local model on exported pairs (Mac Studio). PLACEHOLDER.

The immediate, working 'distillation' is retrieval/few-shot via agent.proposer.ExperienceProposer,
which already lets the engine use its own results to propose for new targets with zero API cost.
A true local fine-tune (LLaMA-class) on {title,description} -> {"keywords":[...]} drops in here later,
exposing the same propose() interface so nothing downstream changes.
"""
from __future__ import annotations

from pathlib import Path


def train(pairs_path: Path, model_out: Path) -> None:  # pragma: no cover
    raise NotImplementedError(
        "Fine-tune not built yet. Use ExperienceProposer (retrieval few-shot) until enough diverse "
        "pairs are harvested, then implement local fine-tuning here."
    )
