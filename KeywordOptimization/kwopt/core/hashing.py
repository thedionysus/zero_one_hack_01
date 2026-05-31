"""Order-invariant keyword hashing. Permutations of the same set => same key (whiteboard sheet 6).

The key also folds in recency + filters, because they change the result and would otherwise
cause false cache hits.
"""
from __future__ import annotations

import hashlib
import json
import re

from ..schemas import Filters


def normalize_keyword(k: str) -> str:
    return re.sub(r"\s+", " ", k.strip().lower())


def normalize_keywords(keywords: list[str]) -> list[str]:
    seen, out = set(), []
    for k in keywords:
        n = normalize_keyword(k)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return sorted(out)


def canonical_key(target_id: str, keywords: list[str], recency: float, filters: Filters) -> str:
    payload = {
        "t": target_id,
        "k": normalize_keywords(keywords),
        "r": round(float(recency), 4),
        "f": {"regions": sorted(filters.regions), "categories": sorted(filters.categories), "limit": filters.limit},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
