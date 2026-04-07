"""VNPay Payment Gateway — sandbox/prod URL + HMAC SHA512 theo tài liệu VNPay."""

from __future__ import annotations

import hashlib
import hmac
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _quote_key_val(k: str, v: str | int) -> str:
    return f"{urllib.parse.quote_plus(str(k))}={urllib.parse.quote_plus(str(v))}"


def build_sign_data(params: dict[str, str | int]) -> str:
    filtered = {
        k: v
        for k, v in params.items()
        if k.startswith("vnp_")
        and k not in ("vnp_SecureHash", "vnp_SecureHashType")
        and v is not None
        and str(v) != ""
    }
    return "&".join(
        _quote_key_val(k, str(v)) for k, v in sorted(filtered.items(), key=lambda x: x[0])
    )


def sign_request(params: dict[str, str | int], hash_secret: str) -> str:
    sign_data = build_sign_data(params)
    return hmac.new(
        hash_secret.encode("utf-8"),
        sign_data.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()


def build_payment_url(
    payment_base_url: str,
    tmn_code: str,
    hash_secret: str,
    return_url: str,
    ipn_url: str,
    amount_vnd: int,
    txn_ref: str,
    order_info: str,
    client_ip: str,
) -> str:
    now = datetime.now(_VN)
    params: dict[str, str | int] = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_TmnCode": tmn_code,
        "vnp_Locale": "vn",
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": order_info[:255],
        "vnp_OrderType": "other",
        "vnp_Amount": str(amount_vnd * 100),
        "vnp_ReturnUrl": return_url,
        "vnp_IpnUrl": ipn_url,
        "vnp_CreateDate": now.strftime("%Y%m%d%H%M%S"),
        "vnp_ExpireDate": (now + timedelta(minutes=15)).strftime("%Y%m%d%H%M%S"),
        "vnp_IpAddr": client_ip or "127.0.0.1",
    }
    params["vnp_SecureHash"] = sign_request(params, hash_secret)
    q = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    sep = "&" if "?" in payment_base_url else "?"
    return f"{payment_base_url}{sep}{q}"


def verify_callback(params: dict[str, str], hash_secret: str) -> bool:
    """Xác thực query trả về / IPN (có vnp_SecureHash)."""
    recv = params.get("vnp_SecureHash", "")
    if not recv:
        return False
    calc = sign_request({k: v for k, v in params.items()}, hash_secret)
    return hmac.compare_digest(calc.lower(), recv.lower()) or hmac.compare_digest(
        calc.upper(), recv.upper()
    )


def txn_ref_for_payment(payment_id: int) -> str:
    """Mã giao dịch gửi VNPay (duy nhất mỗi lần tạo payment row)."""
    return f"EL{payment_id}"
