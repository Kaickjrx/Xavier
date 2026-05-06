from xavier.ml_active import _is_seller_code, _looks_like_code, _parse_active_text


def test_seller_code_detection():
    assert _is_seller_code("Mt20241004145121")
    assert _is_seller_code("Mt123456789")
    assert not _is_seller_code("MELI20")
    assert not _is_seller_code("Mt12345")  # poucos dígitos


def test_looks_like_code():
    assert _looks_like_code("MELI20")
    assert _looks_like_code("BLACKFRI10")
    assert _looks_like_code("DESCONTOS")  # 9 letras
    assert not _looks_like_code("OK")
    assert not _looks_like_code("12345")  # só dígitos


def test_parse_active_text_picks_codes_and_descriptions():
    sample = """
    MELI20
    10% off em eletrônicos
    Em produtos selecionados
    BLACK15
    Black Friday — frete grátis
    Mt20241004145121
    Vendedor random
    DESCONTOS
    Em produtos selecionados
    """
    coupons = _parse_active_text(sample)
    codes = [c.code for c in coupons]
    assert "MELI20" in codes
    assert "BLACK15" in codes
    assert "DESCONTOS" in codes
    # Vendedor individual descartado
    assert "Mt20241004145121" not in codes


def test_parse_active_text_dedupes():
    sample = "MELI20\ndesc\nMELI20\ndesc"
    coupons = _parse_active_text(sample)
    assert len([c for c in coupons if c.code == "MELI20"]) == 1
