from bs4 import BeautifulSoup

from xavier.scrapers.base import looks_like_coupon_code
from xavier.scrapers.cuponomia import CuponomiaScraper
from xavier.scrapers.cupomvalido import CupomValidoScraper


def test_looks_like_coupon_code():
    assert looks_like_coupon_code("MELI20")
    assert looks_like_coupon_code("BLACK10")
    assert not looks_like_coupon_code("OK")  # muito curto
    assert not looks_like_coupon_code("OFF")  # muito curto e sem dígito
    assert looks_like_coupon_code("ABCDEF")  # 6 letras passa


def test_cuponomia_parses_data_attribute():
    html = """
    <html><body>
      <div class="offer" data-coupon-code="MELI20">
        <div class="offer__title">10% off no Mercado Livre</div>
        <div class="offer__discount">10% OFF</div>
      </div>
      <div class="offer" data-coupon-code="BLACK15">
        <h3>Black Friday</h3>
        <span class="discount">15% OFF</span>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    scraper = CuponomiaScraper()
    coupons = list(scraper._parse(soup, "https://example.com"))
    scraper.close()

    codes = {c.code for c in coupons}
    assert "MELI20" in codes
    assert "BLACK15" in codes


def test_cupomvalido_parses_clipboard_attribute():
    html = """
    <html><body>
      <article class="coupon" data-clipboard-text="VOLTAS10">
        <h2 class="coupon-title">10% em volta às aulas</h2>
        <span class="coupon-discount">10% OFF</span>
      </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    scraper = CupomValidoScraper()
    coupons = list(scraper._parse(soup, "https://example.com"))
    scraper.close()

    assert any(c.code == "VOLTAS10" for c in coupons)
