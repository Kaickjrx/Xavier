from __future__ import annotations

from .base import Scraper
from .cuponomia import CuponomiaScraper
from .cupomvalido import CupomValidoScraper

ALL_SCRAPERS: list[type[Scraper]] = [CuponomiaScraper, CupomValidoScraper]

__all__ = ["Scraper", "CuponomiaScraper", "CupomValidoScraper", "ALL_SCRAPERS"]
