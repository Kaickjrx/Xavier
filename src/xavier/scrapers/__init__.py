from __future__ import annotations

from .base import Scraper
from .adorocupom import AdoroCupomScraper
from .cupomvalido import CupomValidoScraper
from .cuponomia import CuponomiaScraper
from .meliuz import MeliuzScraper
from .promobit import PromobitScraper
from .valeplus import ValePlusScraper

# Ordem de prioridade vinda do feedback memory.
ALL_SCRAPERS: list[type[Scraper]] = [
    AdoroCupomScraper,
    ValePlusScraper,
    PromobitScraper,
    MeliuzScraper,
    CuponomiaScraper,
    CupomValidoScraper,
]

__all__ = [
    "Scraper",
    "AdoroCupomScraper",
    "CupomValidoScraper",
    "CuponomiaScraper",
    "MeliuzScraper",
    "PromobitScraper",
    "ValePlusScraper",
    "ALL_SCRAPERS",
]
