from __future__ import annotations

import json
import logging
from typing import Iterable

import httpx

from .models import CouponStatus, ValidationResult

log = logging.getLogger(__name__)

STATUS_LABELS_PT: dict[CouponStatus, str] = {
    CouponStatus.ACTIVE: "Ativo",
    CouponStatus.EXPIRED: "Expirado",
    CouponStatus.INVALID: "Inválido",
    CouponStatus.REQUIRES_CONDITIONS: "Requer condições",
    CouponStatus.UNKNOWN: "Desconhecido",
    CouponStatus.ERROR: "Erro",
}


def format_line(result: ValidationResult) -> str:
    """Formato: CODIGO | DESCRICAO | Status"""
    code = result.coupon.code
    desc = (
        result.coupon.discount
        or result.coupon.description
        or "-"
    ).strip()
    desc = " ".join(desc.split())  # normaliza espaços
    status = STATUS_LABELS_PT.get(result.status, result.status.value.capitalize())
    return f"{code} | {desc} | {status}"


def format_summary(results: Iterable[ValidationResult]) -> str:
    return "\n".join(format_line(r) for r in results)


# ───────── Formato dos webhooks do monitor ─────────

FOOTER = (
    "Ative o cupom no link pelo app: https://meli.la/25EE8mV\n\n"
    "🔗 Convide um amigo(a) para o grupo: "
    "https://chat.whatsapp.com/IfUMKqvZBee1CkPUtR89nd"
)


def format_webhook_list(
    *,
    active_codes: list[str],
    newly_active: list[str],
    newly_expired: list[str],
) -> str:
    """Webhook 2 — formato lista."""
    parts: list[str] = ["CUPONS ativos:"]
    parts.append(" | ".join(active_codes) if active_codes else "(nenhum)")
    if newly_active:
        n = len(newly_active)
        parts.append(f"São {n} novo{'s' if n != 1 else ''}.")
    if newly_expired:
        parts.append("")
        parts.append("CUPONS expirados:")
        parts.append(" | ".join(newly_expired))
    return "\n".join(parts)


def format_webhook_detailed(
    *,
    opener_phrase: str,
    active_with_desc: list[tuple[str, str | None]],
    announced_codes: set[str],
) -> str:
    """Webhook 3 — formato detalhado.

    active_with_desc: [(code, description_or_None), ...] na ordem que devem aparecer.
    announced_codes: códigos já anunciados antes (não recebem marcador NOVO).
    """
    lines: list[str] = [opener_phrase, ""]
    for code, desc in active_with_desc:
        desc_text = (desc or "").strip() or "—"
        marker = "" if code in announced_codes else " - (NOVO)"
        lines.append(f"🎟️ *{code}* - {desc_text}{marker}")
    lines.append("")
    lines.append(FOOTER)
    return "\n".join(lines)


def post(url: str, text: str, timeout: float = 10.0) -> int:
    """Posta `{"text": ...}` em um webhook (Google Chat compatível). Retorna status."""
    log.info("POST webhook (%d chars)", len(text))
    resp = httpx.post(url, json={"text": text}, timeout=timeout)
    resp.raise_for_status()
    return resp.status_code


def send_webhook(
    url: str,
    results: list[ValidationResult],
    *,
    include_payload: bool = True,
    timeout: float = 10.0,
) -> None:
    """Posta um resumo + payload completo em um webhook genérico (JSON)."""
    body = {
        "text": format_summary(results),
        "summary": format_summary(results),
        "total": len(results),
        "by_status": _count_by_status(results),
    }
    if include_payload:
        body["results"] = [r.model_dump(mode="json") for r in results]

    log.info("enviando %d resultados para webhook %s", len(results), url)
    resp = httpx.post(url, json=body, timeout=timeout)
    resp.raise_for_status()
    log.info("webhook respondeu %s", resp.status_code)


def _count_by_status(results: list[ValidationResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    return counts


def dry_run(results: list[ValidationResult]) -> str:
    """Retorna o JSON que seria enviado, útil para teste sem URL."""
    body = {
        "text": format_summary(results),
        "total": len(results),
        "by_status": _count_by_status(results),
        "results": [r.model_dump(mode="json") for r in results],
    }
    return json.dumps(body, ensure_ascii=False, indent=2)
