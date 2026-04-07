"""Hoàn tất giao dịch: cập nhật Payment + Booking."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Payment, PaymentStatus


def finalize_payment(
    db: Session,
    pay: Payment,
    external_ref: str,
    *,
    vnpay_amount_units: int | None = None,
) -> bool:
    """
    vnpay_amount_units: giá trị vnp_Amount từ VNPay (đã nhân 100); phải khớp booking.
    """
    if pay.status != PaymentStatus.pending:
        return pay.status == PaymentStatus.completed

    booking = db.query(Booking).filter(Booking.id == pay.booking_id).first()
    if not booking:
        return False

    if vnpay_amount_units is not None:
        if int(vnpay_amount_units) != pay.amount_vnd * 100:
            return False

    pay.status = PaymentStatus.completed
    pay.paid_at = datetime.now(timezone.utc)
    pay.external_ref = (external_ref or "")[:250]
    booking.status = BookingStatus.confirmed
    db.commit()
    return True
