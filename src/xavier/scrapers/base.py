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
    # Quanto menor, maior prioridade (1 = melhor fonte).
    priority: int = 99

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


# Marcadores que indicam que o cupom ainda está fresco na fonte.
FRESH_MARKERS = (
    "verificado hoje",
    "atualizado hoje",
    "validado hoje",
    "há poucos minutos",
    "há minutos",
    "há 1 hora",
    "há 2 horas",
    "há algumas horas",
)
# Marcadores que indicam fonte velha — descarta.
STALE_MARKERS = (
    "verificado há 3 dias",
    "verificado há 4 dias",
    "verificado há 5 dias",
    "verificado há 6 dias",
    "verificado há 7 dias",
    "verificado há 1 semana",
    "verificado há 2 semanas",
    "expirado",
    "vencido",
    "cupom expirado",
)


def is_fresh(card_text: str) -> bool:
    """Heurística para regra anti-desperdício do feedback memory.

    Aceita se houver marcador de fresco. Rejeita se houver marcador de stale.
    Na ausência dos dois, aceita por default (a validação no ML é a fonte da verdade).
    """
    lower = card_text.lower()
    if any(m in lower for m in STALE_MARKERS):
        return False
    if any(m in lower for m in FRESH_MARKERS):
        return True
    return True
