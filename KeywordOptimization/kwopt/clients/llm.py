"""Optional LLM backend for keyword proposal. Import-guarded: the engine runs without it.

Wire any provider here. Contract: given context + history, return a list[str] of <=20 keywords.
"""
from __future__ import annotations

import json
import re
from typing import Optional

PROMPT = """You propose KEYWORDS that steer a forecasting API's external-driver search.
Target series:
  title: {title}
  description: {description}

Rules:
- Return STRICT JSON only: {{"keywords": ["...", ...]}}. No prose.
- At most 20 keywords, each under 255 characters, each a distinct macro/industry/demand signal.
- Prefer terms that surface drivers the model actually USES (manufacturing, industrial production,
  energy, equities, demand) over near-duplicates.

Past attempts (lower MAPE is better; null = not yet scored):
{history}

Propose ONE new keyword set likely to lower MAPE versus the best past attempt.
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


class LLMProposer:
    def __init__(self, model: str):
        self.model = model
        try:
            import anthropic  # noqa
            self._client = anthropic.Anthropic()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "LLM proposer requires the 'anthropic' package and ANTHROPIC_API_KEY. "
                f"Install it or use --proposer static. ({exc})"
            )

    def propose(self, title: str, description: str, history: list[dict]) -> Optional[list[str]]:
        hist = json.dumps(history[-20:], indent=2) if history else "(none yet)"
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=512,
            temperature=0.6,  # meeting spec (sheet 5): T = 0.6
            messages=[{"role": "user", "content": PROMPT.format(title=title, description=description, history=hist)}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            kws = _extract_json(text).get("keywords", [])
            return [str(k).strip() for k in kws if str(k).strip()][:20]
        except Exception:
            return None
