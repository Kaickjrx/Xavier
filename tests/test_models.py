from datetime import datetime, timedelta

from xavier.models import Coupon, CouponStatus, ValidationResult
from xavier.storage import deduplicate


def test_coupon_defaults():
    c = Coupon(code="MELI20", source="cuponomia")
    assert c.code == "MELI20"
    assert c.collected_at is not None
    assert c.expires_at is None


def test_validation_result_roundtrip():
    c = Coupon(code="MELI20", source="cuponomia")
    r = ValidationResult(coupon=c, status=CouponStatus.ACTIVE, message="ok")
    payload = r.model_dump(mode="json")
    restored = ValidationResult.model_validate(payload)
    assert restored.status == CouponStatus.ACTIVE
    assert restored.coupon.code == "MELI20"


def test_dedup_keeps_most_recent():
    older = Coupon(
        code="MELI10",
        source="a",
        collected_at=datetime.utcnow() - timedelta(days=1),
    )
    newer = Coupon(code="meli10", source="b", collected_at=datetime.utcnow())
    out = deduplicate([older, newer])
    assert len(out) == 1
    assert out[0].source == "b"
