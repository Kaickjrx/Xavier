from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class CouponStatus(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"
    REQUIRES_CONDITIONS = "requires_conditions"
    ERROR = "error"


class Coupon(BaseModel):
    code: str = Field(..., description="Código do cupom (ex.: MELI10)")
    description: Optional[str] = None
    discount: Optional[str] = Field(None, description="Texto livre do desconto (ex.: '10% OFF', 'R$ 20')")
    minimum_purchase: Optional[str] = None
    expires_at: Optional[datetime] = None
    source: str = Field(..., description="Identificador da fonte (ex.: 'cuponomia')")
    source_url: Optional[HttpUrl] = None
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class ValidationResult(BaseModel):
    coupon: Coupon
    status: CouponStatus
    message: Optional[str] = None
    validated_at: datetime = Field(default_factory=datetime.utcnow)
