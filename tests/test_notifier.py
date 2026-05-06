from xavier.models import Coupon, CouponStatus, ValidationResult
from xavier.notifier import format_line, format_summary


def _result(code: str, status: CouponStatus, discount: str | None = None,
            description: str | None = None) -> ValidationResult:
    return ValidationResult(
        coupon=Coupon(code=code, source="t", discount=discount, description=description),
        status=status,
    )


def test_format_line_uses_pipe_separator():
    line = format_line(_result("MELI20", CouponStatus.ACTIVE, discount="10% OFF"))
    parts = [p.strip() for p in line.split("|")]
    assert parts == ["MELI20", "10% OFF", "Ativo"]


def test_format_line_falls_back_to_description():
    line = format_line(
        _result("X1", CouponStatus.INVALID, discount=None, description="Frete grátis")
    )
    parts = [p.strip() for p in line.split("|")]
    assert parts == ["X1", "Frete grátis", "Inválido"]


def test_format_line_dash_when_no_text():
    line = format_line(_result("X2", CouponStatus.EXPIRED))
    parts = [p.strip() for p in line.split("|")]
    assert parts == ["X2", "-", "Expirado"]


def test_summary_one_line_per_result():
    results = [
        _result("A1", CouponStatus.ACTIVE, discount="10%"),
        _result("B2", CouponStatus.EXPIRED),
        _result("C3", CouponStatus.INVALID, discount="R$ 20"),
    ]
    summary = format_summary(results)
    assert summary.count("\n") == 2
    assert "A1 | 10% | Ativo" in summary
    assert "B2 | - | Expirado" in summary
    assert "C3 | R$ 20 | Inválido" in summary
