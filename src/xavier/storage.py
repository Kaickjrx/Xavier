from __future__ import annotations

import json
from pathlib import Path

from .models import Coupon, ValidationResult


def save_coupons(coupons: list[Coupon], path: Path) -> None:
    path.write_text(
        json.dumps(
            [c.model_dump(mode="json") for c in coupons],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def load_coupons(path: Path) -> list[Coupon]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Coupon.model_validate(item) for item in raw]


def save_results(results: list[ValidationResult], path: Path) -> None:
    path.write_text(
        json.dumps(
            [r.model_dump(mode="json") for r in results],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def deduplicate(coupons: list[Coupon]) -> list[Coupon]:
    """Mantém um cupom por código (o mais recente vence)."""
    by_code: dict[str, Coupon] = {}
    for c in coupons:
        existing = by_code.get(c.code.upper())
        if existing is None or c.collected_at > existing.collected_at:
            by_code[c.code.upper()] = c
    return list(by_code.values())
