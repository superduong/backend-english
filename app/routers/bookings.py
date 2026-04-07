from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Booking, BookingStatus, TeacherProfile, User, UserRole
from app.schemas import BookingCreate, BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])

LESSON_MINUTES = 60


def _overlap_clause(teacher_profile_id: int, start: datetime, end: datetime):
    return and_(
        Booking.teacher_profile_id == teacher_profile_id,
        Booking.status != BookingStatus.cancelled,
        Booking.start_at < end,
        Booking.end_at > start,
    )


@router.post("", response_model=BookingOut)
def create_booking(
    body: BookingCreate,
    current: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    if current.role != UserRole.student:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ học viên được đặt lịch",
        )

    teacher = (
        db.query(TeacherProfile)
        .filter(
            TeacherProfile.id == body.teacher_profile_id,
            TeacherProfile.is_available.is_(True),
        )
        .first()
    )
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Giáo viên không khả dụng",
        )

    start = body.start_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = start + timedelta(minutes=LESSON_MINUTES)

    now = datetime.now(timezone.utc)
    if start < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thời gian buổi học phải trong tương lai",
        )

    conflict = (
        db.query(Booking)
        .filter(_overlap_clause(teacher.id, start, end))
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Giáo viên đã có lịch trong khung giờ này",
        )

    amount = teacher.hourly_rate_vnd
    booking = Booking(
        student_id=current.id,
        teacher_profile_id=teacher.id,
        start_at=start,
        end_at=end,
        status=BookingStatus.pending_payment,
        amount_vnd=amount,
        note=body.note or "",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/mine", response_model=list[BookingOut])
def my_bookings(
    current: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    q = db.query(Booking).filter(Booking.student_id == current.id)
    return q.order_by(Booking.start_at.desc()).all()
