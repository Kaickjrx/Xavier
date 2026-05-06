from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import async_playwright

from .ml_active import PageReadResult, read_active_coupons
from .models import Coupon, CouponStatus, ValidationResult
from .notifier import (
    format_webhook_detailed,
    format_webhook_list,
    post,
)
from .phrases import load_phrases, pick_phrase
from .scrapers import ALL_SCRAPERS
from .state import (
    DEFAULT_STATE_PATH,
    CouponSnapshot,
    MonitorState,
    load_state,
    merge_after_run,
    save_state,
)
from .validator import (
    CaptchaDetected,
    LoginRequired,
    MercadoLivreValidator,
    STORAGE_STATE,
)

log = logging.getLogger(__name__)


@dataclass
class MonitorResult:
    sent_webhooks: bool
    summary: str
    webhook_list: str | None = None
    webhook_detailed: str | None = None


async def run_monitor(
    *,
    webhook_url: str,
    state_path: Path = DEFAULT_STATE_PATH,
    phrases_path: Path = Path("phrases.json"),
    headless: bool = True,
    throttle_seconds: float = 8.0,
    max_candidates: int = 10,
    storage_state_path: Path = STORAGE_STATE,
) -> MonitorResult:
    """Executa uma rodada do monitor de cupons do ML.

    Retorna MonitorResult informando se mandou webhook (ou não, em caso de
    rodada silenciosa por ausência de mudança).

    Em caso de falha (browser/login/captcha) manda 1 webhook de erro curto e
    relança a exceção.
    """
    state = load_state(state_path)
    phrases = load_phrases(phrases_path)

    # ───── 1. Ler /cupons/active ─────
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=headless)
            ctx_kwargs: dict = {"locale": "pt-BR"}
            if storage_state_path.exists():
                ctx_kwargs["storage_state"] = str(storage_state_path)
            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            try:
                read = await read_active_coupons(page)
            finally:
                if storage_state_path.exists():
                    await ctx.storage_state(path=str(storage_state_path))
                await ctx.close()
                await browser.close()
    except Exception as exc:
        _send_error(webhook_url, f"falha ao abrir browser: {exc}")
        raise

    if read.has_captcha:
        _send_error(webhook_url, "captcha em /cupons/active. Resolver manualmente.")
        raise CaptchaDetected()
    if read.needs_login:
        _send_error(webhook_url, "sessão deslogada — login manual necessário.")
        raise LoginRequired()

    current_active = read.coupons
    current_codes = {c.code for c in current_active}

    # ───── 2. Diff vs state ─────
    previous_codes = state.active_codes
    newly_active_now = sorted(current_codes - previous_codes)
    newly_expired = sorted(previous_codes - current_codes)
    log.info("ativos=%d, novos_via_diff=%d, expirados=%d",
             len(current_codes), len(newly_active_now), len(newly_expired))

    # ───── 3. Buscar candidatos novos em fontes externas ─────
    candidates = _collect_candidates(
        max_candidates=max_candidates,
        skip_codes=current_codes | state.recent_dead_set,
    )
    log.info("candidatos coletados de fontes externas: %d", len(candidates))

    # ───── 4. Testar candidatos no ML ─────
    test_results: list[ValidationResult] = []
    if candidates:
        validator = MercadoLivreValidator(
            headless=headless,
            throttle_seconds=throttle_seconds,
            storage_state_path=storage_state_path,
        )
        try:
            test_results = await validator.validate_all(candidates)
        except CaptchaDetected:
            _send_error(webhook_url, "captcha durante teste de cupons.")
            raise
        except LoginRequired:
            _send_error(webhook_url, "login expirou durante teste de cupons.")
            raise

    new_dead_codes = [
        r.coupon.code
        for r in test_results
        if r.status in (CouponStatus.EXPIRED, CouponStatus.INVALID, CouponStatus.REQUIRES_CONDITIONS)
    ]

    # ───── 5. Re-ler /cupons/active para confirmar quem entrou ─────
    if test_results:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=headless)
            ctx = await browser.new_context(
                locale="pt-BR",
                storage_state=str(storage_state_path) if storage_state_path.exists() else None,
            )
            page = await ctx.new_page()
            try:
                reread = await read_active_coupons(page)
            finally:
                await ctx.close()
                await browser.close()
        if reread.coupons:
            current_active = reread.coupons
            current_codes = {c.code for c in current_active}
            newly_active_now = sorted(current_codes - previous_codes)
            newly_expired = sorted(previous_codes - current_codes)

    # ───── 6. Decidir se manda webhooks ─────
    sent_any = False
    webhook_list_text = None
    webhook_detailed_text = None
    used_phrase = None

    if newly_active_now or newly_expired:
        webhook_list_text = format_webhook_list(
            active_codes=[c.code for c in current_active],
            newly_active=newly_active_now,
            newly_expired=newly_expired,
        )
        used_phrase = pick_phrase(phrases, state.recent_phrases)
        webhook_detailed_text = format_webhook_detailed(
            opener_phrase=used_phrase,
            active_with_desc=[(c.code, c.description) for c in current_active],
            announced_codes=state.announced_set,
        )
        # Webhook 2 primeiro, webhook 3 depois — em mensagens separadas.
        post(webhook_url, webhook_list_text)
        post(webhook_url, webhook_detailed_text)
        sent_any = True

    # ───── 7. Atualizar state ─────
    summary = _summarize(
        current_active=current_active,
        newly_active=newly_active_now,
        newly_expired=newly_expired,
        candidates_tested=len(test_results),
        new_dead=len(new_dead_codes),
        sent=sent_any,
    )
    new_state = merge_after_run(
        state,
        current_active=current_active,
        new_dead=new_dead_codes,
        used_phrase=used_phrase,
        result_summary=summary,
    )
    save_state(new_state, state_path)
    log.info(summary)

    return MonitorResult(
        sent_webhooks=sent_any,
        summary=summary,
        webhook_list=webhook_list_text,
        webhook_detailed=webhook_detailed_text,
    )


def _collect_candidates(*, max_candidates: int, skip_codes: set[str]) -> list[Coupon]:
    """Coleta cupons das fontes externas, em ordem de prioridade, até max_candidates."""
    out: list[Coupon] = []
    seen: set[str] = set(skip_codes)
    for cls in sorted(ALL_SCRAPERS, key=lambda c: getattr(c, "priority", 99)):
        if len(out) >= max_candidates:
            break
        try:
            with cls() as scraper:
                found = scraper.fetch()
        except Exception as exc:
            log.warning("scraper %s falhou: %s", cls.name, exc)
            continue
        for c in found:
            if c.code in seen:
                continue
            seen.add(c.code)
            out.append(c)
            if len(out) >= max_candidates:
                break
    return out


def _summarize(
    *,
    current_active: list[CouponSnapshot],
    newly_active: list[str],
    newly_expired: list[str],
    candidates_tested: int,
    new_dead: int,
    sent: bool,
) -> str:
    return (
        f"ativos={len(current_active)} | "
        f"novos={len(newly_active)} | "
        f"expirados={len(newly_expired)} | "
        f"testados={candidates_tested} | "
        f"mortos={new_dead} | "
        f"webhooks={'sim' if sent else 'não'}"
    )


def _send_error(webhook_url: str, reason: str) -> None:
    try:
        post(webhook_url, f"[ml-cupons-monitor] Falha: {reason}")
    except Exception as exc:
        log.error("falha ao enviar webhook de erro: %s", exc)


def run_monitor_sync(**kwargs) -> MonitorResult:
    return asyncio.run(run_monitor(**kwargs))
