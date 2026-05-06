from __future__ import annotations

import asyncio
import logging
import random
import re
from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

from .models import Coupon, CouponStatus, ValidationResult

log = logging.getLogger(__name__)

ML_HOST = "https://www.mercadolivre.com.br"
# Página dedicada de cupons (Cupons > Inserir cupom).
COUPONS_URL = f"{ML_HOST}/cupons"
STORAGE_STATE = Path(".playwright-state/storage_state.json")


class CaptchaDetected(Exception):
    """Disparado quando o ML pede captcha; o monitor aborta a rodada."""


class LoginRequired(Exception):
    """Disparado quando a sessão expirou e modo headless não pode logar."""


class MercadoLivreValidator:
    """Valida cupons na página Cupons > Inserir cupom do Mercado Livre.

    Fluxo:
      1. Abre https://www.mercadolivre.com.br/cupons (faz login na 1ª vez)
      2. Para cada cupom: clica em "Inserir cupom", digita o código devagar,
         submete e lê a mensagem de retorno.
      3. Throttle generoso entre tentativas + jitter para evitar bloqueio.
    """

    def __init__(
        self,
        headless: bool = False,
        throttle_seconds: float = 12.0,
        throttle_jitter: float = 4.0,
        storage_state_path: Path = STORAGE_STATE,
        coupons_url: str = COUPONS_URL,
        max_dead_per_source: int = 5,
    ) -> None:
        self.headless = headless
        self.throttle_seconds = throttle_seconds
        self.throttle_jitter = throttle_jitter
        self.storage_state_path = storage_state_path
        self.coupons_url = coupons_url
        self.max_dead_per_source = max_dead_per_source

    async def validate_all(self, coupons: list[Coupon]) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        # Contagem de inválidos/expirados por fonte → abandono após N falhas.
        dead_per_source: dict[str, int] = {}
        abandoned: set[str] = set()

        async with async_playwright() as pw:
            context = await self._open_context(pw)
            page = await context.new_page()

            try:
                login_state = await self._ensure_logged_in(page)
                if login_state == "captcha":
                    raise CaptchaDetected("Captcha na página de cupons do ML.")
                if login_state == "needs_login":
                    raise LoginRequired("Sessão deslogada — login manual necessário.")

                for i, coupon in enumerate(coupons, start=1):
                    if coupon.source in abandoned:
                        log.info("[%d/%d] pulando %s (fonte %s abandonada nesta rodada)",
                                 i, len(coupons), coupon.code, coupon.source)
                        continue

                    log.info("[%d/%d] validando %s (fonte=%s)",
                             i, len(coupons), coupon.code, coupon.source)
                    try:
                        result = await self._apply_coupon(page, coupon)
                    except CaptchaDetected:
                        raise
                    except Exception as exc:
                        log.exception("erro ao validar %s", coupon.code)
                        result = ValidationResult(
                            coupon=coupon,
                            status=CouponStatus.ERROR,
                            message=str(exc),
                        )
                    results.append(result)
                    log.info("  → %s (%s)", result.status.value, result.message or "")

                    if result.status in (CouponStatus.EXPIRED, CouponStatus.INVALID):
                        dead_per_source[coupon.source] = dead_per_source.get(coupon.source, 0) + 1
                        if dead_per_source[coupon.source] >= self.max_dead_per_source:
                            log.warning("abandonando fonte %s após %d falhas",
                                        coupon.source, dead_per_source[coupon.source])
                            abandoned.add(coupon.source)

                    if i < len(coupons):
                        await self._sleep_with_jitter()
            finally:
                await context.storage_state(path=str(self.storage_state_path))
                await context.close()

        return results

    async def _open_context(self, pw: Playwright) -> BrowserContext:
        browser = await pw.chromium.launch(headless=self.headless)
        kwargs: dict = {
            "locale": "pt-BR",
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        }
        if self.storage_state_path.exists():
            kwargs["storage_state"] = str(self.storage_state_path)
        else:
            self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        return await browser.new_context(**kwargs)

    async def _ensure_logged_in(self, page: Page) -> str:
        """Retorna 'ok' | 'needs_login' | 'captcha'.

        Em modo interativo (não-headless) tenta login manual.
        Em modo headless, devolve 'needs_login' sem prompt.
        """
        await page.goto(self.coupons_url, wait_until="domcontentloaded")
        if await self._has_captcha(page):
            return "captcha"

        if "registration" in page.url or "login" in page.url:
            if self.headless:
                return "needs_login"
            print(
                "\n⚠ Faça login no Mercado Livre na janela aberta. "
                "Depois de logado, pressione Enter aqui para continuar."
            )
            await asyncio.get_event_loop().run_in_executor(None, input)
            await page.goto(self.coupons_url, wait_until="domcontentloaded")
            if "registration" in page.url or "login" in page.url:
                return "needs_login"
            if await self._has_captcha(page):
                return "captcha"
        return "ok"

    @staticmethod
    async def _has_captcha(page: Page) -> bool:
        html = (await page.content()).lower()
        return (
            "captcha" in html
            or "verifique que você é humano" in html
            or "/security-challenge" in page.url
        )

    async def _apply_coupon(self, page: Page, coupon: Coupon) -> ValidationResult:
        # Sempre recarrega a página de cupons antes de cada tentativa para garantir
        # estado limpo (mensagens anteriores não vazam para a próxima validação).
        await page.goto(self.coupons_url, wait_until="domcontentloaded")
        await self._small_pause()

        # Encontra o disparador "Inserir cupom" (botão/link/aba).
        trigger = page.locator(
            "button:has-text('Inserir cupom'), "
            "a:has-text('Inserir cupom'), "
            "button:has-text('Inserir'), "
            "[data-testid*='insert-coupon' i], "
            "[data-testid*='add-coupon' i]"
        ).first

        if await trigger.count() > 0:
            try:
                await trigger.scroll_into_view_if_needed(timeout=3000)
                await self._small_pause(0.3, 0.8)
                await trigger.click(timeout=4000)
                await self._small_pause()
            except PlaywrightTimeout:
                pass

        # Localiza o input do cupom.
        input_field = page.locator(
            "input[name*='coupon' i], "
            "input[placeholder*='cupom' i], "
            "input[id*='coupon' i], "
            "input[aria-label*='cupom' i]"
        ).first

        if await input_field.count() == 0:
            return ValidationResult(
                coupon=coupon,
                status=CouponStatus.ERROR,
                message=(
                    "Campo de cupom não encontrado em /cupons. "
                    "Layout pode ter mudado — ajuste os seletores em validator.py."
                ),
            )

        await input_field.click()
        await input_field.fill("")
        # Digita devagar, caractere por caractere, simulando humano.
        await input_field.type(coupon.code, delay=random.randint(80, 180))
        await self._small_pause(0.5, 1.2)

        submit = page.locator(
            "button:has-text('Aplicar'), "
            "button:has-text('Validar'), "
            "button:has-text('Adicionar'), "
            "button[type='submit']"
        ).first
        if await submit.count() > 0:
            await submit.click()
        else:
            await input_field.press("Enter")

        # Aguarda a UI estabilizar para ler a mensagem.
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass
        await self._small_pause(1.0, 2.0)

        return self._classify_response(coupon, await page.content())

    async def _sleep_with_jitter(self) -> None:
        jitter = random.uniform(-self.throttle_jitter / 2, self.throttle_jitter / 2)
        wait = max(2.0, self.throttle_seconds + jitter)
        log.debug("aguardando %.1fs antes do próximo cupom", wait)
        await asyncio.sleep(wait)

    @staticmethod
    async def _small_pause(low: float = 0.4, high: float = 1.0) -> None:
        await asyncio.sleep(random.uniform(low, high))

    @staticmethod
    def _classify_response(coupon: Coupon, html: str) -> ValidationResult:
        text = re.sub(r"\s+", " ", html).lower()

        # Detecção de bloqueio antes de tudo.
        if any(
            m in text
            for m in (
                "muitas tentativas",
                "tente novamente mais tarde",
                "acesso bloqueado",
                "captcha",
            )
        ):
            return ValidationResult(
                coupon=coupon,
                status=CouponStatus.ERROR,
                message="Possível bloqueio/rate-limit do Mercado Livre. Pause e aumente o throttle.",
            )

        active = [
            "cupom aplicado",
            "cupom adicionado",
            "cupom ativo",
            "desconto aplicado",
            "guardado com sucesso",
            "cupom guardado",
        ]
        expired = ["expirado", "vencido", "fora do prazo", "expirou"]
        invalid = [
            "inválido",
            "invalido",
            "não encontrado",
            "nao encontrado",
            "não é válido",
            "nao e valido",
            "código incorreto",
            "codigo incorreto",
        ]
        conditions = [
            "não atende",
            "valor mínimo",
            "valor minimo",
            "não elegível",
            "nao elegivel",
            "categoria",
            "vendedor específico",
            "produto específico",
            "primeira compra",
        ]

        for m in active:
            if m in text:
                return ValidationResult(coupon=coupon, status=CouponStatus.ACTIVE, message=m)
        for m in expired:
            if m in text:
                return ValidationResult(coupon=coupon, status=CouponStatus.EXPIRED, message=m)
        for m in conditions:
            if m in text:
                return ValidationResult(
                    coupon=coupon, status=CouponStatus.REQUIRES_CONDITIONS, message=m
                )
        for m in invalid:
            if m in text:
                return ValidationResult(coupon=coupon, status=CouponStatus.INVALID, message=m)

        return ValidationResult(
            coupon=coupon,
            status=CouponStatus.UNKNOWN,
            message="Mensagem do ML não contém marcadores conhecidos. Inspecione manualmente.",
        )
