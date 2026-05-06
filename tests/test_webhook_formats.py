from xavier.notifier import (
    FOOTER,
    format_webhook_detailed,
    format_webhook_list,
)


def test_webhook_list_with_active_and_news():
    text = format_webhook_list(
        active_codes=["A1", "B2", "C3"],
        newly_active=["B2", "C3"],
        newly_expired=[],
    )
    assert text.startswith("CUPONS ativos:")
    assert "A1 | B2 | C3" in text
    assert "São 2 novos." in text
    assert "expirados" not in text.lower()


def test_webhook_list_with_only_expired():
    text = format_webhook_list(
        active_codes=["A1"],
        newly_active=[],
        newly_expired=["X9", "Y8"],
    )
    assert "São" not in text  # nada novo
    assert "CUPONS expirados:" in text
    assert "X9 | Y8" in text


def test_webhook_list_singular_novo():
    text = format_webhook_list(
        active_codes=["A1", "Z9"],
        newly_active=["Z9"],
        newly_expired=[],
    )
    assert "São 1 novo." in text


def test_webhook_list_no_active():
    text = format_webhook_list(
        active_codes=[],
        newly_active=[],
        newly_expired=["DEAD1"],
    )
    assert "(nenhum)" in text
    assert "DEAD1" in text


def test_webhook_detailed_marks_only_unannounced_as_novo():
    text = format_webhook_detailed(
        opener_phrase="*ROLOU CUPOM* 🚀",
        active_with_desc=[
            ("OLD1", "Cupom antigo"),
            ("NEW9", "Cupom novo"),
        ],
        announced_codes={"OLD1"},  # OLD1 já foi anunciado
    )
    lines = text.splitlines()
    assert lines[0] == "*ROLOU CUPOM* 🚀"
    assert lines[1] == ""
    assert "🎟️ *OLD1* - Cupom antigo" in text
    assert "🎟️ *NEW9* - Cupom novo - (NOVO)" in text
    # Footer fixo na ordem certa
    assert text.endswith(FOOTER)


def test_webhook_detailed_dash_when_no_description():
    text = format_webhook_detailed(
        opener_phrase="*PEGA AÍ*",
        active_with_desc=[("X1", None), ("X2", "")],
        announced_codes=set(),
    )
    assert "🎟️ *X1* - — - (NOVO)" in text
    assert "🎟️ *X2* - — - (NOVO)" in text
