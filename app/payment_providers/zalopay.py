"""ZaloPay đặt đơn — Quickstart Merchant Server.

Tài liệu: https://docs.zalopay.vn/docs/developers/quickstart
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any

import httpx

_VN_UTC_OFFSET = timezone.utc  # ZaloPay dùng app_time ms; múi giờ trong app_trans_id chỉ label


def build_mac_create(
    app_id: str,
    app_trans_id: str,
    app_user: str,
    amount: int,
    app_time: int,
    embed_data: str,
    item: str,
    key1: str,
) -> str:
    data = (
        f"{app_id}|{app_trans_id}|{app_user}|{amount}|{app_time}|{embed_data}|{item}"
    )
    return hmac.new(key1.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


def create_order(
    *,
    endpoint: str,
    app_id: str,
    key1: str,
    app_user: str,
    payment_id: int,
    amount_vnd: int,
    description: str,
    callback_url: str,
    redirect_url: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    app_time = int(time.time() * 1000)
    yy_mm_dd = datetime.now(_VN_UTC_OFFSET).strftime("%y%m%d")
    app_trans_id = f"{yy_mm_dd}_{app_id}_{payment_id}_{app_time}"

    embed_data = json.dumps(
        {"redirecturl": redirect_url, "payment_id": payment_id},
        separators=(",", ":"),
    )
    item = json.dumps(
        [
            {
                "itemid": "booking",
                "itemname": description[:400],
                "itemprice": amount_vnd,
                "itemquantity": 1,
            }
        ],
        separators=(",", ":"),
    )
    mac = build_mac_create(
        app_id, app_trans_id, app_user, int(amount_vnd), app_time, embed_data, item, key1
    )
    body = {
        "app_id": int(app_id) if app_id.isdigit() else app_id,
        "app_trans_id": app_trans_id,
        "app_user": app_user,
        "app_time": app_time,
        "item": item,
        "embed_data": embed_data,
        "amount": int(amount_vnd),
        "description": description[:255],
        "bank_code": "",
        "mac": mac,
        "callback_url": callback_url,
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(endpoint, json=body)
        r.raise_for_status()
        return r.json()


def verify_callback_mac(data: str, req_mac: str, key2: str) -> bool:
    """MAC = HMAC-SHA256(data, key2) — `data` là chuỗi trong field `data` của callback."""
    calc = hmac.new(key2.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc, req_mac)


def parse_callback_body(body: dict[str, Any], key2: str) -> dict[str, Any] | None:
    """Giải callback POST JSON {'data': base64, 'mac': ...}."""
    raw_data = body.get("data")
    req_mac = body.get("mac")
    if not isinstance(raw_data, str) or not isinstance(req_mac, str):
        return None
    if not verify_callback_mac(raw_data, req_mac, key2):
        return None
    try:
        decoded = base64.b64decode(raw_data)
        return json.loads(decoded)
    except (json.JSONDecodeError, ValueError):
        return None


