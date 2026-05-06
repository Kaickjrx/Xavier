from __future__ import annotations

import logging
import re
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from ..models import Coupon
from .base import Scraper, looks_like_coupon_code

log = logging.getLogger(__name__)


class CupomValidoScraper(Scraper):
    name = "cupomvalido"
    base_url = "https://www.cupomvalido.com.br"
    listing_path = "/cupom-de-desconto/mercado-livre/"

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
        # Estrutura típica: cards .coupon, código em .coupon-code ou data-clipboard-text
        cards = soup.select(".coupon, .cupom, article")
        seen: set[str] = set()

        for card in cards:
            code = self._extract_code(card)
            if not code or code in seen:
                continue
            seen.add(code)
            yield Coupon(
                code=code,
                description=self._first_text(card, [".coupon-title", ".cupom-title", "h2", "h3"]),
                discount=self._first_text(card, [".coupon-discount", ".desconto", ".discount"]),
                source=self.name,
                source_url=page_url,
            )

        if not seen:
            for code in self._fallback_codes(soup):
                if code in seen:
                    continue
                seen.add(code)
                yield Coupon(code=code, source=self.name, source_url=page_url)

    @staticmethod
    def _extract_code(card: Tag) -> str | None:
        for attr in ("data-clipboard-text", "data-coupon-code", "data-code"):
            v = card.get(attr)
            if v:
                code = v.strip().upper()
                if looks_like_coupon_code(code):
                    return code

        for sel in [".coupon-code", ".cupom-codigo", ".code"]:
            el = card.select_one(sel)
            if el:
                code = el.get_text(strip=True).upper()
                if looks_like_coupon_code(code):
                    return code
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
        for match in re.finditer(r"[Cc][óo]digo[:\s]+([A-Z0-9]{4,20})", text):
            code = match.group(1).upper()
            if looks_like_coupon_code(code):
                yield code
