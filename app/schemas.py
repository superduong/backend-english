from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BookingStatus, PaymentStatus, UserRole


def _validate_email(v: str) -> str:
    v = v.strip().lower()
    if "@" not in v:
        raise ValueError("Email không hợp lệ")
    local, _, domain = v.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("Email không hợp lệ")
    return v


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=1, max_length=255)

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        return _validate_email(v)


class UserLogin(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        return _validate_email(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TeacherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    display_name: str
    bio: str
    hourly_rate_vnd: int
    is_available: bool


class BookingCreate(BaseModel):
    teacher_profile_id: int
    start_at: datetime
    note: str = ""


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    teacher_profile_id: int
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    amount_vnd: int
    note: str
    created_at: datetime


PaymentProviderId = Literal["mock", "vnpay", "momo", "zalopay", "bank_qr"]


class PaymentCheckoutIn(BaseModel):
    provider: PaymentProviderId = "mock"


class PaymentProviderItem(BaseModel):
    id: PaymentProviderId
    label: str
    kind: Literal["mock", "redirect", "qr"]
    enabled: bool


class PaymentProvidersOut(BaseModel):
    providers: list[PaymentProviderItem]


class PaymentCheckoutOut(BaseModel):
    payment_id: int
    booking_id: int
    amount_vnd: int
    provider: str
    mock_mode: bool
    message_vi: str
    redirect_url: str | None = None
    qr_image_url: str | None = None


class VnpayClientVerifyOut(BaseModel):
    """Kết quả xác thực query VNPay gửi từ SPA /payment/callback."""

    signature_valid: bool
    response_code: str | None = None
    message_vi: str
    booking_confirmed: bool = False


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    provider: str
    status: PaymentStatus
    amount_vnd: int
    created_at: datetime
    paid_at: datetime | None
