"""Enforce Sybilion's documented input limits before any API call."""
from __future__ import annotations


class ValidationError(ValueError):
    pass


def validate_keywords(keywords: list[str]) -> list[str]:
    if len(keywords) > 20:
        raise ValidationError(f"keywords: {len(keywords)} > 20 max")
    clean = []
    for k in keywords:
        k = str(k).strip()
        if not k:
            raise ValidationError("keywords: empty item not allowed")
        if len(k.encode("utf-8")) > 255:
            raise ValidationError(f"keyword too long (>255 bytes): {k[:40]}...")
        clean.append(k)
    return clean


def validate_title(title: str) -> None:
    n = len(title.encode("utf-8"))
    if n < 20 or n > 511:
        raise ValidationError(f"title must be 20-511 bytes, got {n}")


def validate_description(description: str) -> None:
    if len(description.encode("utf-8")) > 2048:
        raise ValidationError("description > 2048 bytes")
