"""VietQR / Napas — ảnh QR chuyển khoản qua img.vietqr.io (không cần secret).

Nội dung chuyển khoản nên chứa mã payment để đối soát (khi không có webhook ngân hàng).
"""

from __future__ import annotations

import urllib.parse


def build_vietqr_image_url(
    *,
    bank_id: str,
    account_no: str,
    account_name: str,
    amount_vnd: int,
    description: str,
    template: str = "compact2",
) -> str:
    """
    bank_id: mã Napas 6 số (VD Vietcombank 970436, MB 970422, Momo 971025,...).
    template: compact | compact2 | qr_only | ...
    """
    base = f"https://img.vietqr.io/image/{bank_id}-{account_no}-{template}.png"
    q: dict[str, str] = {
        "amount": str(amount_vnd),
        "addInfo": description[:140],
        "accountName": account_name[:70],
    }
    return f"{base}?{urllib.parse.urlencode(q)}"
