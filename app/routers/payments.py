from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.schemas import PaymentCheckoutOut

router = APIRouter(prefix="/payments", tags=["payments"])


class WebhookPayload(BaseModel):
    payment_id: int
    status: str = Field(pattern="^(success|failed)$")
    signature: str = ""


@router.post("/bookings/{booking_id}/checkout", response_model=PaymentCheckoutOut)
def checkout_booking(
    booking_id: int,
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

    existing = (
        db.query(Payment)
        .filter(
            Payment.booking_id == booking.id,
            Payment.status == PaymentStatus.pending,
        )
        .first()
    )
    if existing:
        return PaymentCheckoutOut(
            payment_id=existing.id,
            booking_id=booking.id,
            amount_vnd=existing.amount_vnd,
            provider=existing.provider,
            mock_mode=settings.mock_payments,
            message_vi="Tiếp tục thanh toán giao dịch đang mở.",
        )

    pay = Payment(
        booking_id=booking.id,
        provider="mock",
        status=PaymentStatus.pending,
        amount_vnd=booking.amount_vnd,
    )
    db.add(pay)
    db.commit()
    db.refresh(pay)

    return PaymentCheckoutOut(
        payment_id=pay.id,
        booking_id=booking.id,
        amount_vnd=pay.amount_vnd,
        provider=pay.provider,
        mock_mode=settings.mock_payments,
        message_vi="MVP: dùng nút 'Xác nhận thanh toán thử' để mô phỏng Momo/ZaloPay.",
    )


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

    pay.status = PaymentStatus.completed
    pay.paid_at = datetime.now(timezone.utc)
    pay.external_ref = "mock-success"
    booking.status = BookingStatus.confirmed
    db.commit()

    return PaymentCheckoutOut(
        payment_id=pay.id,
        booking_id=booking.id,
        amount_vnd=pay.amount_vnd,
        provider=pay.provider,
        mock_mode=True,
        message_vi="Thanh toán thử thành công. Buổi học đã được xác nhận.",
    )


@router.post("/webhook")
def payment_webhook(body: WebhookPayload, db: Session = Depends(get_db)):
    """
    Stub cho Momo/ZaloPay/VNPAY về sau: verify chữ ký, idempotent update.
    MVP: chỉ chấp nhận payment_id + status trong môi trường dev.
    """
    if not settings.mock_payments:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Cấu hình cổng thanh toán thật chưa bật",
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
