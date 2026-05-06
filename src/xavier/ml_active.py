from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .state import CouponSnapshot

log = logging.getLogger(__name__)

ACTIVE_URL = "https://www.mercadolivre.com.br/cupons/active"

# Vendedor individual: "Mt" + dígitos longos. Ignorar.
SELLER_CODE_RE = re.compile(r"^Mt\d{6,}$")
# Códigos válidos de cupom: alfanumérico maiúsculo, 4-20 chars, ao menos 1 dígito ou ≥6 letras.
CODE_RE = re.compile(r"^[A-Z0-9]{4,20}$")

# Títulos sem badge que ainda contam como cupom (ex.: "Em produtos selecionados — DESCONTOS").
KNOWN_NO_BADGE_TITLES = {"DESCONTOS"}


@dataclass
class PageReadResult:
    coupons: list[CouponSnapshot]
    needs_login: bool = False
    has_captcha: bool = False


def _is_seller_code(text: str) -> bool:
    return bool(SELLER_CODE_RE.match(text.strip()))


def _looks_like_code(text: str) -> bool:
    t = text.strip()
    if not CODE_RE.match(t):
        return False
    if t.isdigit():
        return False
    has_digit = any(c.isdigit() for c in t)
    return has_digit or len(t) >= 6


async def read_active_coupons(page: Page) -> PageReadResult:
    """Navega para /cupons/active e devolve a lista de cupons ativos.

    Não tenta extrair seletores específicos do DOM (que mudam) — varre o texto
    visível em busca de tokens que pareçam código de cupom + descrição próxima.
    O parser ignora vendedores individuais (Mt12345...) e respeita títulos
    explícitos como "DESCONTOS".
    """
    try:
        await page.goto(ACTIVE_URL, wait_until="domcontentloaded", timeout=20000)
    except PlaywrightTimeout:
        log.warning("timeout navegando para %s", ACTIVE_URL)

    if "registration" in page.url or "login" in page.url:
        return PageReadResult(coupons=[], needs_login=True)

    content = await page.content()
    if "captcha" in content.lower() or "verifique que você é humano" in content.lower():
        return PageReadResult(coupons=[], has_captcha=True)

    text = await page.evaluate("() => document.body.innerText")
    return PageReadResult(coupons=_parse_active_text(text))


def _parse_active_text(text: str) -> list[CouponSnapshot]:
    """Heurística: cada cupom aparece como linha de código + linha de descrição.

    Estrutura típica observada (ML pt-BR):
      <CODIGO>
      <descrição curta>
      Em produtos ...   ← às vezes
      Válido até DD/MM  ← às vezes

    Para cupons sem badge mas com título conhecido (ex.: DESCONTOS),
    o título aparece sozinho — tratamos como "code = título".
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out: list[CouponSnapshot] = []
    seen: set[str] = set()

    i = 0
    while i < len(lines):
        line = lines[i]

        if _is_seller_code(line):
            i += 1
            continue

        is_known_title = line in KNOWN_NO_BADGE_TITLES
        is_code = _looks_like_code(line)

        if is_code or is_known_title:
            code = line
            description = None
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                if (
                    not _looks_like_code(nxt)
                    and not _is_seller_code(nxt)
                    and nxt not in KNOWN_NO_BADGE_TITLES
                    and len(nxt) <= 200
                ):
                    description = nxt
            if code not in seen:
                seen.add(code)
                out.append(CouponSnapshot(code=code, description=description))
            i += 2 if description else 1
            continue

        i += 1

    return out
