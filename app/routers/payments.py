from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import (
    Booking,
    BookingStatus,
    Payment,
    PaymentStatus,
    User,
    UserRole,
)
from app.payment_providers import completion, momo, vietqr, vnpay, zalopay
from app.schemas import (
    PaymentCheckoutIn,
    PaymentCheckoutOut,
    PaymentProviderItem,
    PaymentProvidersOut,
    VnpayClientVerifyOut,
)

router = APIRouter(prefix="/payments", tags=["payments"])


def _api_base(request: Request) -> str:
    if settings.public_api_url.strip():
        return settings.public_api_url.strip().rstrip("/")
    return str(request.base_url).rstrip("/")


def _frontend_base() -> str:
    return settings.frontend_public_url.strip().rstrip("/")


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


def _finalize(db: Session, pay: Payment, ref: str, *, vnpay_amount_units: int | None = None) -> None:
    completion.finalize_payment(db, pay, ref, vnpay_amount_units=vnpay_amount_units)


def _momo_order_id(payment_id: int) -> str:
    return f"MOMO{payment_id}"


def _parse_el_id(txn_ref: str) -> int | None:
    m = re.match(r"^EL(\d+)$", txn_ref.strip())
    return int(m.group(1)) if m else None


def _parse_momo_id(order_id: str) -> int | None:
    m = re.match(r"^MOMO(\d+)$", str(order_id).strip())
    return int(m.group(1)) if m else None


class WebhookPayload(BaseModel):
    payment_id: int
    status: str = Field(pattern="^(success|failed)$")
    signature: str = ""


def _enabled_providers() -> list[PaymentProviderItem]:
    out: list[PaymentProviderItem] = []
    if settings.mock_payments:
        out.append(
            PaymentProviderItem(
                id="mock",
                label="Thử nghiệm (xác nhận tức thì)",
                kind="mock",
                enabled=True,
            )
        )
    vnp_ok = bool(settings.vnpay_tmn_code and settings.vnpay_hash_secret)
    out.append(
        PaymentProviderItem(
            id="vnpay",
            label="VNPay (thẻ ATM/QR)",
            kind="redirect",
            enabled=vnp_ok,
        )
    )
    momo_ok = bool(
        settings.momo_partner_code
        and settings.momo_access_key
        and settings.momo_secret_key
    )
    out.append(
        PaymentProviderItem(
            id="momo",
            label="Ví MoMo",
            kind="redirect",
            enabled=momo_ok,
        )
    )
    zlp_ok = bool(settings.zalopay_app_id and settings.zalopay_key1 and settings.zalopay_key2)
    out.append(
        PaymentProviderItem(
            id="zalopay",
            label="ZaloPay",
            kind="redirect",
            enabled=zlp_ok,
        )
    )
    vqr_ok = bool(settings.vietqr_bank_id and settings.vietqr_account_no)
    out.append(
        PaymentProviderItem(
            id="bank_qr",
            label="Chuyển khoản qua QR (VietQR)",
            kind="qr",
            enabled=vqr_ok,
        )
    )
    return out


@router.get("/providers", response_model=PaymentProvidersOut)
def payment_providers():
    return PaymentProvidersOut(providers=_enabled_providers())


def _checkout_payload(
    *,
    pay: Payment,
    booking: Booking,
    request: Request,
    message_vi: str | None = None,
) -> PaymentCheckoutOut:
    redirect_url: str | None = None
    qr_image_url: str | None = None
    msg = message_vi or ""
    api_b = _api_base(request)
    front = _frontend_base()

    if pay.provider == "mock":
        msg = msg or (
            "Dùng nút «Xác nhận thanh toán thử» trên app (chỉ môi trường dev)."
        )
    elif pay.provider == "vnpay":
        if not (settings.vnpay_tmn_code and settings.vnpay_hash_secret):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "VNPay chưa cấu hình")
        if not front:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Thiết lập FRONTEND_PUBLIC_URL để redirect sau VNPay.",
            )
        ipn = f"{api_b}/payments/ipn/vnpay"
        txn = vnpay.txn_ref_for_payment(pay.id)
        redirect_url = vnpay.build_payment_url(
            settings.vnpay_payment_url,
            settings.vnpay_tmn_code,
            settings.vnpay_hash_secret,
            f"{front}/payment/callback",
            ipn,
            pay.amount_vnd,
            txn,
            f"Thanh toan buoi hoc #{booking.id}",
            _client_ip(request),
        )
        msg = msg or "Đang chuyển đến trang thanh toán VNPay."
    elif pay.provider == "momo":
        if not (
            settings.momo_partner_code
            and settings.momo_access_key
            and settings.momo_secret_key
        ):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "MoMo chưa cấu hình")
        if not front:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Thiết lập FRONTEND_PUBLIC_URL cho MoMo redirect.",
            )
        oid = _momo_order_id(pay.id)
        rid = f"{uuid.uuid4()}"
        try:
            res = momo.create_payment(
                endpoint=settings.momo_endpoint,
                partner_code=settings.momo_partner_code,
                partner_name=settings.momo_partner_name,
                store_id=settings.momo_store_id,
                access_key=settings.momo_access_key,
                secret_key=settings.momo_secret_key,
                order_id=oid,
                request_id=rid,
                amount_vnd=pay.amount_vnd,
                order_info=f"Buoi hoc #{booking.id}",
                redirect_url=f"{front}/bookings",
                ipn_url=f"{api_b}/payments/ipn/momo",
                extra_data="",
            )
        except Exception as e:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"MoMo không phản hồi: {e!s}",
            ) from e
        if int(res.get("resultCode", -1)) != 0:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                res.get("message") or "MoMo tạo giao dịch thất bại",
            )
        redirect_url = res.get("payUrl")
        msg = msg or "Đang mở ví MoMo / trình duyệt thanh toán."
    elif pay.provider == "zalopay":
        if not (settings.zalopay_app_id and settings.zalopay_key1 and settings.zalopay_key2):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ZaloPay chưa cấu hình")
        if not front:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Thiết lập FRONTEND_PUBLIC_URL cho ZaloPay.",
            )
        try:
            res = zalopay.create_order(
                endpoint=settings.zalopay_create_endpoint,
                app_id=settings.zalopay_app_id,
                key1=settings.zalopay_key1,
                app_user=settings.zalopay_app_user,
                payment_id=pay.id,
                amount_vnd=pay.amount_vnd,
                description=f"Lịch học #{booking.id}",
                callback_url=f"{api_b}/payments/ipn/zalopay",
                redirect_url=f"{front}/bookings",
            )
        except Exception as e:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"ZaloPay không phản hồi: {e!s}",
            ) from e
        if res.get("return_code") != 1:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                res.get("return_message") or "ZaloPay tạo đơn thất bại",
            )
        redirect_url = res.get("order_url")
        msg = msg or "Đang chuyển đến ZaloPay."
    elif pay.provider == "bank_qr":
        if not (settings.vietqr_bank_id and settings.vietqr_account_no):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "VietQR chưa cấu hình")
        memo = f"EL{pay.id} Lich{booking.id}"
        qr_image_url = vietqr.build_vietqr_image_url(
            bank_id=settings.vietqr_bank_id,
            account_no=settings.vietqr_account_no,
            account_name=settings.vietqr_account_name or "THU HUONG",
            amount_vnd=pay.amount_vnd,
            description=memo[:140],
        )
        msg = (
            msg
            or "Quét QR để chuyển khoản. Sau khi nhận tiền, merchant xác nhận trong dashboard "
            "(API confirm-manual hoặc đối soát)."
        )

    mock_mode = bool(settings.mock_payments and pay.provider == "mock")
    return PaymentCheckoutOut(
        payment_id=pay.id,
        booking_id=booking.id,
        amount_vnd=pay.amount_vnd,
        provider=pay.provider,
        mock_mode=mock_mode,
        message_vi=msg,
        redirect_url=redirect_url,
        qr_image_url=qr_image_url,
    )


@router.post("/bookings/{booking_id}/checkout", response_model=PaymentCheckoutOut)
def checkout_booking(
    booking_id: int,
    body: PaymentCheckoutIn,
    request: Request,
    current: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    if current.role != UserRole.student:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ học viên thanh toán",
        )

    booking = (
        db.query(Booking)
        .filter(Booking.id == booking_id, Booking.student_id == current.id)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy buổi học",
        )
    if booking.status != BookingStatus.pending_payment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Buổi học không chờ thanh toán",
        )

    if not settings.mock_payments and body.provider == "mock":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Tắt mock_payments — chọn cổng thật.",
        )

    prov_map = {p.id: p for p in _enabled_providers()}
    chosen = prov_map.get(body.provider)
    if not chosen or not chosen.enabled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Cổng thanh toán «{body.provider}» chưa bật hoặc chưa cấu hình.",
        )

    existing = (
        db.query(Payment)
        .filter(
            Payment.booking_id == booking.id,
            Payment.status == PaymentStatus.pending,
        )
        .first()
    )
    if existing and existing.provider != body.provider:
        db.delete(existing)
        db.commit()
        existing = None

    if existing:
        return _checkout_payload(pay=existing, booking=booking, request=request)

    pay = Payment(
        booking_id=booking.id,
        provider=body.provider,
        status=PaymentStatus.pending,
        amount_vnd=booking.amount_vnd,
    )
    db.add(pay)
    db.commit()
    db.refresh(pay)

    return _checkout_payload(pay=pay, booking=booking, request=request)


@router.post("/{payment_id}/confirm-mock", response_model=PaymentCheckoutOut)
def confirm_mock(
    payment_id: int,
    current: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    if not settings.mock_payments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chế độ mock thanh toán đang tắt",
        )

    pay = db.query(Payment).filter(Payment.id == payment_id).first()
    if not pay:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy giao dịch",
        )
    booking = db.query(Booking).filter(Booking.id == pay.booking_id).first()
    if not booking or booking.student_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền với giao dịch này",
        )
    if pay.status != PaymentStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Giao dịch đã xử lý",
        )

    _finalize(db, pay, "mock-success")

    return PaymentCheckoutOut(
        payment_id=pay.id,
        booking_id=booking.id,
        amount_vnd=pay.amount_vnd,
        provider=pay.provider,
        mock_mode=True,
        message_vi="Thanh toán thử thành công. Buổi học đã được xác nhận.",
    )


@router.post("/ops/confirm-bank-transfer/{payment_id}", response_model=PaymentCheckoutOut)
def ops_confirm_bank_transfer(
    payment_id: int,
    db: Session = Depends(get_db),
    x_merchant_key: Annotated[str | None, Header()] = None,
):
    """
    Sau khi đối soát sao kê (VietQR / ngân hàng). Gọi từ backend nội bộ / dashboard,
    header X-Merchant-Key = MERCHANT_MANUAL_API_KEY — không dùng JWT học viên.
    """
    key = settings.merchant_manual_api_key.strip()
    if not key or x_merchant_key != key:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Không hợp lệ")
    pay = db.query(Payment).filter(Payment.id == payment_id).first()
    if not pay or pay.provider != "bank_qr":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Giao dịch không hợp lệ")
    booking = db.query(Booking).filter(Booking.id == pay.booking_id).first()
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Booking không tồn tại")
    if pay.status != PaymentStatus.pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Đã xử lý")

    _finalize(db, pay, f"manual-{int(time.time())}")

    return PaymentCheckoutOut(
        payment_id=pay.id,
        booking_id=booking.id,
        amount_vnd=pay.amount_vnd,
        provider=pay.provider,
        mock_mode=False,
        message_vi="Đã xác nhận thanh toán chuyển khoản.",
    )


@router.api_route("/ipn/vnpay", methods=["GET", "POST"])
def vnpay_ipn(request: Request, db: Session = Depends(get_db)):
    if not settings.vnpay_hash_secret:
        return JSONResponse({"RspCode": "97", "Message": "Fail"}, status_code=200)

    params = dict(request.query_params)

    if not vnpay.verify_callback(params, settings.vnpay_hash_secret):
        return JSONResponse({"RspCode": "97", "Message": "Invalid signature"}, status_code=200)

    txn = params.get("vnp_TxnRef", "")
    pid = _parse_el_id(txn)
    if pid is None:
        return JSONResponse({"RspCode": "01", "Message": "Order not found"}, status_code=200)

    pay = db.query(Payment).filter(Payment.id == pid).first()
    if not pay:
        return JSONResponse({"RspCode": "01", "Message": "Order not found"}, status_code=200)

    code = params.get("vnp_ResponseCode") or params.get("vnp_TransactionStatus")
    if code == "00":
        amt_raw = int(params.get("vnp_Amount", "0"))
        ok = completion.finalize_payment(
            db,
            pay,
            params.get("vnp_TransactionNo") or "vnpay",
            vnpay_amount_units=amt_raw,
        )
        if ok:
            return JSONResponse({"RspCode": "00", "Message": "Confirmed"})
        return JSONResponse({"RspCode": "04", "Message": "Denied"}, status_code=200)
    return JSONResponse({"RspCode": "00", "Message": "Acknowledged"})


@router.get("/return/vnpay")
def vnpay_return(request: Request):
    """Tương thích cấu hình cũ (Return URL trỏ thẳng API): chuyển về SPA /payment/callback kèm query."""
    front = _frontend_base() or "/"
    q = request.query_params
    if not q:
        return RedirectResponse(f"{front}/payment/callback", status_code=302)
    return RedirectResponse(
        f"{front}/payment/callback?{q}",
        status_code=302,
    )


def _vnpay_response_message_user(code: str | None) -> str:
    if not code:
        return "Không có mã phản hồi từ VNPay."
    m = {
        "00": "Giao dịch thành công.",
        "07": "Trừ tiền thành công, giao dịch bị nghi ngờ (cần kiểm tra thêm).",
        "09": "Thẻ chưa đăng ký dịch vụ InternetBanking.",
        "10": "Xác thực thông tin thẻ/tài khoản không đúng.",
        "11": "Hết hạn chờ thanh toán.",
        "12": "Thẻ/Tài khoản bị khóa.",
        "24": "Khách hàng hủy giao dịch.",
        "51": "Tài khoản không đủ số dư.",
        "65": "Vượt quá hạn mức giao dịch trong ngày.",
        "75": "Ngân hàng thanh toán đang bảo trì.",
        "79": "Nhập sai mật khẩu thanh toán quá số lần quy định.",
    }
    return m.get(code, f"VNPay trả mã «{code}». Xem lịch sử hoặc thử lại.")


@router.post("/verify/vnpay-client", response_model=VnpayClientVerifyOut)
def verify_vnpay_client(
    params: Annotated[dict[str, str], Body(...)],
    db: Session = Depends(get_db),
):
    """
    SPA /payment/callback gửi toàn bộ query VNPay (JSON object) — server kiểm HMAC và cập nhật booking.
    Không cần JWT (user quay lại từ cổng thanh toán).
    """
    if not settings.vnpay_hash_secret.strip():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VNPay chưa cấu hình (VNPAY_HASH_SECRET).",
        )

    if not vnpay.verify_callback(params, settings.vnpay_hash_secret):
        return VnpayClientVerifyOut(
            signature_valid=False,
            response_code=params.get("vnp_ResponseCode"),
            message_vi="Không xác thực được chữ ký VNPay. Không sửa URL sau khi thanh toán.",
        )

    code = params.get("vnp_ResponseCode") or params.get("vnp_TransactionStatus")
    txn = params.get("vnp_TxnRef", "")
    pid = _parse_el_id(txn)

    if code != "00":
        return VnpayClientVerifyOut(
            signature_valid=True,
            response_code=code,
            message_vi=_vnpay_response_message_user(code),
            booking_confirmed=False,
        )

    if pid is None:
        return VnpayClientVerifyOut(
            signature_valid=True,
            response_code=code,
            message_vi="Mã giao dịch không hợp lệ.",
            booking_confirmed=False,
        )

    pay = db.query(Payment).filter(Payment.id == pid).first()
    if not pay:
        return VnpayClientVerifyOut(
            signature_valid=True,
            response_code=code,
            message_vi="Không tìm thấy đơn thanh toán trên hệ thống.",
            booking_confirmed=False,
        )

    try:
        amt_raw = int(params.get("vnp_Amount", "0"))
    except ValueError:
        amt_raw = 0

    before = pay.status
    finalized_ok = completion.finalize_payment(
        db,
        pay,
        params.get("vnp_TransactionNo") or "vnpay-spa",
        vnpay_amount_units=amt_raw,
    )
    db.refresh(pay)
    if pay.status == PaymentStatus.completed:
        msg = (
            "Thanh toán thành công. Buổi học đã được xác nhận."
            if before == PaymentStatus.pending
            else "Giao dịch đã hoàn tất trước đó."
        )
        return VnpayClientVerifyOut(
            signature_valid=True,
            response_code=code,
            message_vi=msg,
            booking_confirmed=True,
        )
    msg = "Không khớp số tiền hoặc không thể hoàn tất giao dịch."
    if not finalized_ok:
        msg = "Số tiền VNPay không khớp với đơn đặt lịch."
    return VnpayClientVerifyOut(
        signature_valid=True,
        response_code=code,
        message_vi=msg,
        booking_confirmed=False,
    )


@router.post("/ipn/momo")
async def momo_ipn(request: Request, db: Session = Depends(get_db)):
    if not settings.momo_secret_key:
        return JSONResponse({"resultCode": 97, "message": "Not configured"}, status_code=200)
    body: dict[str, Any] = await request.json()

    ok = momo.verify_ipn_signature(
        access_key=str(body.get("accessKey", "")),
        amount=str(body.get("amount", "")),
        extra_data=str(body.get("extraData", "")),
        message=str(body.get("message", "")),
        order_id=str(body.get("orderId", "")),
        order_info=str(body.get("orderInfo", "")),
        order_type=str(body.get("orderType", "")),
        partner_code=str(body.get("partnerCode", "")),
        pay_type=str(body.get("payType", "")),
        request_id=str(body.get("requestId", "")),
        response_time=str(body.get("responseTime", "")),
        result_code=str(body.get("resultCode", "")),
        trans_id=str(body.get("transId", "")),
        secret_key=settings.momo_secret_key,
        signature=str(body.get("signature", "")),
    )
    if not ok:
        return JSONResponse({"resultCode": 97, "message": "Bad signature"}, status_code=200)

    pid = _parse_momo_id(str(body.get("orderId", "")))
    if pid is None:
        return JSONResponse({"resultCode": 12, "message": "Bad order"}, status_code=200)

    pay = db.query(Payment).filter(Payment.id == pid).first()
    if not pay:
        return JSONResponse({"resultCode": 12, "message": "Not found"}, status_code=200)

    if str(body.get("resultCode")) == "0":
        try:
            amt = int(body.get("amount", 0))
        except (TypeError, ValueError):
            amt = 0
        if amt == pay.amount_vnd:
            _finalize(db, pay, str(body.get("transId", "momo")))
    return JSONResponse({"resultCode": 0, "message": "Success"})


@router.post("/ipn/zalopay")
async def zalopay_ipn(request: Request, db: Session = Depends(get_db)):
    if not settings.zalopay_key2:
        return JSONResponse({"return_code": 1, "return_message": "skip"})
    body = await request.json()
    parsed = zalopay.parse_callback_body(body, settings.zalopay_key2)
    if not parsed:
        return JSONResponse({"return_code": -1, "return_message": "invalid"})

    try:
        zp_st = int(parsed.get("zp_trans_status", 0))
    except (TypeError, ValueError):
        zp_st = 0
    if zp_st != 1:
        return JSONResponse({"return_code": 1, "return_message": "pending"})

    embed = parsed.get("embed_data")
    pid: int | None = None
    if isinstance(embed, str):
        try:
            ed = json.loads(embed)
            pid = int(ed.get("payment_id", 0)) or None
        except (json.JSONDecodeError, TypeError, ValueError):
            pid = None
    elif isinstance(embed, dict):
        try:
            pid = int(embed.get("payment_id", 0)) or None
        except (TypeError, ValueError):
            pid = None

    if pid is None:
        return JSONResponse({"return_code": -1, "return_message": "no id"})

    pay = db.query(Payment).filter(Payment.id == pid).first()
    if not pay or pay.provider != "zalopay":
        return JSONResponse({"return_code": -1, "return_message": "bad pay"})

    try:
        amt = int(parsed.get("amount", 0) or 0)
    except (TypeError, ValueError):
        amt = 0
    if amt != pay.amount_vnd:
        return JSONResponse({"return_code": -1, "return_message": "amount"})

    _finalize(db, pay, str(parsed.get("zp_trans_id") or "zalopay"))
    return JSONResponse({"return_code": 1, "return_message": "success"})


@router.post("/webhook")
def payment_webhook_stub(body: WebhookPayload, db: Session = Depends(get_db)):
    """Stub dev: mô phỏng webhook cổng khi MOCK_PAYMENTS=true."""
    if not settings.mock_payments:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Chỉ dùng khi mock_payments=true (dev).",
        )
    pay = db.query(Payment).filter(Payment.id == body.payment_id).first()
    if not pay:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="payment_id không tồn tại",
        )
    booking = db.query(Booking).filter(Booking.id == pay.booking_id).first()
    if not booking:
        raise HTTPException(status_code=500, detail="Dữ liệu không nhất quán")

    if body.status == "success" and pay.status == PaymentStatus.pending:
        pay.status = PaymentStatus.completed
        pay.paid_at = datetime.now(timezone.utc)
        pay.external_ref = "webhook-stub"
        booking.status = BookingStatus.confirmed
    elif body.status == "failed":
        pay.status = PaymentStatus.failed
    db.commit()
    return {"ok": True}