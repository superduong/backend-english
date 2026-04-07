from sqlalchemy.orm import Session

from app.models import TeacherProfile, User, UserRole
from app.security import hash_password


def ensure_seed_data(db: Session) -> None:
    """Demo teachers for Vietnam MVP."""
    if db.query(TeacherProfile).first():
        return

    demo_teachers = [
        {
            "email": "cognitoan@giaovien.demo",
            "password": "demo123456",
            "full_name": "Cô Ngọc Anh",
            "display_name": "Cô Ngọc Anh — IELTS Speaking",
            "bio": "8 năm kinh nghiệm, accent Anh-Anh. Lịch linh hoạt buổi tối.",
            "hourly_rate_vnd": 350_000,
        },
        {
            "email": "thayminh@giaovien.demo",
            "password": "demo123456",
            "full_name": "Thầy Minh",
            "display_name": "Thầy Minh — Giao tiếp công việc",
            "bio": "Tiếng Anh thương mại, phỏng vấn xin việc.",
            "hourly_rate_vnd": 280_000,
        },
        {
            "email": "sarajo@giaovien.demo",
            "password": "demo123456",
            "full_name": "Sarah Johnson",
            "display_name": "Sarah — Native speaker",
            "bio": "Người Anh, tập trung phát âm và natural fluency.",
            "hourly_rate_vnd": 500_000,
        },
    ]

    for row in demo_teachers:
        u = User(
            email=row["email"],
            hashed_password=hash_password(row["password"]),
            full_name=row["full_name"],
            role=UserRole.teacher,
        )
        db.add(u)
        db.flush()
        db.add(
            TeacherProfile(
                user_id=u.id,
                display_name=row["display_name"],
                bio=row["bio"],
                hourly_rate_vnd=row["hourly_rate_vnd"],
                is_available=True,
            )
        )
    db.commit()
