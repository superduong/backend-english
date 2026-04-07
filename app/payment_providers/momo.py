"""MoMo Payment Gateway API v2 /create (captureWallet).

Tài liệu: https://developers.momo.vn/
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx


def _sign_raw(secret_key: str, raw: str) -> str:
    return hmac.new(
        secret_key.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_signature(
    access_key: str,
    amount: int,
    extra_data: str,
    ipn_url: str,
    order_id: str,
    order_info: str,
    partner_code: str,
    redirect_url: str,
    request_id: str,
    request_type: str,
    secret_key: str,
) -> str:
    raw = (
        f"accessKey={access_key}"
        f"&amount={amount}"
        f"&extraData={extra_data}"
        f"&ipnUrl={ipn_url}"
        f"&orderId={order_id}"
        f"&orderInfo={order_info}"
        f"&partnerCode={partner_code}"
        f"&redirectUrl={redirect_url}"
        f"&requestId={request_id}"
        f"&requestType={request_type}"
    )
    return _sign_raw(secret_key, raw)


def create_payment(
    *,
    endpoint: str,
    partner_code: str,
    partner_name: str,
    store_id: str,
    access_key: str,
    secret_key: str,
    order_id: str,
    request_id: str,
    amount_vnd: int,
    order_info: str,
    redirect_url: str,
    ipn_url: str,
    lang: str = "vi",
    request_type: str = "captureWallet",
    extra_data: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    amount = int(amount_vnd)
    sig = build_signature(
        access_key=access_key,
        amount=amount,
        extra_data=extra_data,
        ipn_url=ipn_url,
        order_id=order_id,
        order_info=order_info,
        partner_code=partner_code,
        redirect_url=redirect_url,
        request_id=request_id,
        request_type=request_type,
        secret_key=secret_key,
    )
    body = {
        "partnerCode": partner_code,
        "partnerName": partner_name,
        "storeId": store_id,
        "requestId": request_id,
        "amount": amount,
        "orderId": order_id,
        "orderInfo": order_info,
        "redirectUrl": redirect_url,
        "ipnUrl": ipn_url,
        "lang": lang,
        "extraData": extra_data,
        "requestType": request_type,
        "accessKey": access_key,
        "signature": sig,
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(endpoint, json=body)
        r.raise_for_status()
        return r.json()


def verify_ipn_signature(
    *,
    access_key: str,
    amount: str,
    extra_data: str,
    message: str,
    order_id: str,
    order_info: str,
    order_type: str,
    partner_code: str,
    pay_type: str,
    request_id: str,
    response_time: str,
    result_code: str,
    trans_id: str,
    secret_key: str,
    signature: str,
) -> bool:
    raw = (
        f"accessKey={access_key}"
        f"&amount={amount}"
        f"&extraData={extra_data}"
        f"&message={message}"
        f"&orderId={order_id}"
        f"&orderInfo={order_info}"
        f"&orderType={order_type}"
        f"&partnerCode={partner_code}"
        f"&payType={pay_type}"
        f"&requestId={request_id}"
        f"&responseTime={response_time}"
        f"&resultCode={result_code}"
        f"&transId={trans_id}"
    )
    calc = _sign_raw(secret_key, raw)
    return hmac.compare_digest(calc, signature)
