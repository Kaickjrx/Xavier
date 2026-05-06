from __future__ import annotations

import logging
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from ..models import Coupon
from .base import Scraper, looks_like_coupon_code

log = logging.getLogger(__name__)


class CuponomiaScraper(Scraper):
    name = "cuponomia"
    base_url = "https://www.cuponomia.com.br"
    listing_path = "/loja/mercado-livre"

    def fetch(self) -> list[Coupon]:
        url = f"{self.base_url}{self.listing_path}"
        try:
            html = self.get(url)
        except Exception as exc:
            log.warning("[%s] falha ao carregar %s: %s", self.name, url, exc)
            return []

        soup = BeautifulSoup(html, "lxml")
        return list(self._parse(soup, url))

    def _parse(self, soup: BeautifulSoup, page_url: str) -> Iterable[Coupon]:
        # Cuponomia renderiza cards com data attributes; também caímos em fallback genérico.
        cards = soup.select("[data-coupon-code], .offer-code, .offer__code")
        seen: set[str] = set()

        for card in cards:
            code = self._extract_code(card)
            if not code or code in seen:
                continue
            seen.add(code)
            yield Coupon(
                code=code,
                description=self._first_text(card, [".offer__title", ".offer-title", "h3", "h4"]),
                discount=self._first_text(card, [".offer__discount", ".discount", ".badge"]),
                source=self.name,
                source_url=page_url,
            )

        # Fallback: varre o HTML inteiro procurando padrões "Código: XXXXX"
        if not seen:
            for code in self._fallback_codes(soup):
                if code in seen:
                    continue
                seen.add(code)
                yield Coupon(code=code, source=self.name, source_url=page_url)

    @staticmethod
    def _extract_code(card: Tag) -> str | None:
        code = card.get("data-coupon-code") or card.get("data-code")
        if code:
            code = code.strip().upper()
            return code if looks_like_coupon_code(code) else None

        text = card.get_text(" ", strip=True)
        for token in text.split():
            t = token.strip().upper()
            if looks_like_coupon_code(t):
                return t
        return None

    @staticmethod
    def _first_text(card: Tag, selectors: list[str]) -> str | None:
        for sel in selectors:
            el = card.select_one(sel)
            if el and el.get_text(strip=True):
                return el.get_text(" ", strip=True)
        return None

    @staticmethod
    def _fallback_codes(soup: BeautifulSoup) -> Iterable[str]:
        text = soup.get_text(" ", strip=True)
        # Procura por sequências tipo "Código MELI20"
        import re

        for match in re.finditer(r"[Cc][óo]digo[:\s]+([A-Z0-9]{4,20})", text):
            code = match.group(1).upper()
            if looks_like_coupon_code(code):
                yield code
