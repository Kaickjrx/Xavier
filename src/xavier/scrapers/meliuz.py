from __future__ import annotations

import logging
import re
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from ..models import Coupon
from .base import Scraper, is_fresh, looks_like_coupon_code

log = logging.getLogger(__name__)


class MeliuzScraper(Scraper):
    name = "meliuz"
    base_url = "https://www.meliuz.com.br"
    listing_path = "/cupons-de-desconto/mercado-livre/"
    priority = 4

    def fetch(self) -> list[Coupon]:
        url = f"{self.base_url}{self.listing_path}"
        try:
            html = self.get(url)
        except Exception as exc:
            log.warning("[%s] %s: %s", self.name, url, exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        return list(self._parse(soup, url))

    def _parse(self, soup: BeautifulSoup, page_url: str) -> Iterable[Coupon]:
        cards = soup.select("article, .coupon, .offer, [class*='coupon']")
        seen: set[str] = set()
        for card in cards:
            text = card.get_text(" ", strip=True)
            if not is_fresh(text):
                continue
            code = self._extract_code(card)
            if not code or code in seen:
                continue
            seen.add(code)
            yield Coupon(
                code=code,
                description=self._first_text(card, ["h2", "h3", ".title"]),
                discount=self._first_text(card, [".discount", ".badge", ".percentage"]),
                source=self.name,
                source_url=page_url,
            )

    @staticmethod
    def _extract_code(card: Tag) -> str | None:
        for attr in ("data-coupon-code", "data-clipboard-text", "data-code"):
            v = card.get(attr)
            if v and looks_like_coupon_code(v.strip().upper()):
                return v.strip().upper()
        for sel in [".coupon-code", ".code", "[class*='code']"]:
            el = card.select_one(sel)
            if el:
                t = el.get_text(strip=True).upper()
                if looks_like_coupon_code(t):
                    return t
        for m in re.finditer(r"\b[A-Z0-9]{5,15}\b", card.get_text(" ", strip=True)):
            if looks_like_coupon_code(m.group(0)):
                return m.group(0)
        return None

    @staticmethod
    def _first_text(card: Tag, selectors: list[str]) -> str | None:
        for sel in selectors:
            el = card.select_one(sel)
            if el and el.get_text(strip=True):
                return el.get_text(" ", strip=True)
        return None
