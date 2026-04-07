from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TeacherProfile
from app.schemas import TeacherOut

router = APIRouter(prefix="/teachers", tags=["teachers"])


@router.get("", response_model=list[TeacherOut])
def list_teachers(db: Session = Depends(get_db)):
    return (
        db.query(TeacherProfile)
        .filter(TeacherProfile.is_available.is_(True))
        .order_by(TeacherProfile.id)
        .all()
    )


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    t = (
        db.query(TeacherProfile)
        .filter(
            TeacherProfile.id == teacher_id,
            TeacherProfile.is_available.is_(True),
        )
        .first()
    )
    if not t:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy giáo viên",
        )
    return t
