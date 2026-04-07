from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Thư mục chứa requirements.txt / Dockerfile (luôn đúng dù cwd khác)
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _default_sqlite_url() -> str:
    return f"sqlite:///{(BACKEND_ROOT / 'dev.db').resolve()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "English MVP API"
    database_url: str = Field(default_factory=_default_sqlite_url)
    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    mock_payments: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Tuỳ chọn: bật khi deploy Vercel (preview + production *.vercel.app), ví dụ
    # ^https://.*\.vercel\.app$
    cors_origin_regex: str = ""

    # URL công khai của API (Render/Railway) — dùng cho IPN/callback: không dấu / cuối
    public_api_url: str = ""
    # URL frontend (Vercel) — redirect sau thanh toán
    frontend_public_url: str = ""

    # VNPay
    vnpay_payment_url: str = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
    vnpay_tmn_code: str = ""
    vnpay_hash_secret: str = ""

    # MoMo Payment Gateway v2
    momo_endpoint: str = "https://test-payment.momo.vn/v2/gateway/api/create"
    momo_partner_code: str = ""
    momo_access_key: str = ""
    momo_secret_key: str = ""
    momo_partner_name: str = "LinguaOne"
    momo_store_id: str = "LinguaOneStore"

    # ZaloPay
    zalopay_create_endpoint: str = "https://sb-openapi.zalopay.vn/v2/create"
    zalopay_app_id: str = ""
    zalopay_key1: str = ""
    zalopay_key2: str = ""
    zalopay_app_user: str = "linguaone_student"

    # VietQR (Napas bank code 6 số + STK) — chỉ tạo ảnh QR, không có webhook tự động
    vietqr_bank_id: str = ""
    vietqr_account_no: str = ""
    vietqr_account_name: str = ""

    # Xác nhận CK thủ công (sau khi đối soát sao kê) — header X-Merchant-Key
    merchant_manual_api_key: str = ""

    @field_validator("database_url", mode="after")
    @classmethod
    def expand_sqlite_relative(cls, v: str) -> str:
        # Cho phép .env: DATABASE_URL=sqlite:///./dev.db — luôn trỏ vào backend/
        if v.startswith("sqlite:///./"):
            tail = v.removeprefix("sqlite:///./")
            return f"sqlite:///{(BACKEND_ROOT / tail).resolve()}"
        return v


settings = Settings()
