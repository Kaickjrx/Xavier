from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

import httpx

from ..models import Coupon

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 Xavier/0.1"
)

# Cupons do ML costumam ser alfanuméricos em caixa alta, 4–20 chars.
COUPON_CODE_RE = re.compile(r"\b[A-Z0-9]{4,20}\b")


class Scraper(ABC):
    name: str
    base_url: str

    def __init__(self, client: httpx.Client | None = None, timeout: float = 15.0) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
        )

    def get(self, url: str) -> str:
        log.debug("GET %s", url)
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.text

    @abstractmethod
    def fetch(self) -> list[Coupon]:
        """Retorna a lista de cupons encontrados na fonte."""

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def looks_like_coupon_code(text: str) -> bool:
    """Heurística: descarta palavras comuns que parecem códigos."""
    text = text.strip()
    if not COUPON_CODE_RE.fullmatch(text):
        return False
    # Tem que ter ao menos 1 dígito OU mistura visível, evitando palavras tipo "OFERTA"
    has_digit = any(ch.isdigit() for ch in text)
    return has_digit or len(text) >= 6
