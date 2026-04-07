from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


def _engine_kwargs():
    url = settings.database_url
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # Neon / managed Postgres: idle connections get closed; pre-ping + recycle avoids
    # "SSL connection has been closed unexpectedly" on the next query.
    return {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }


engine = create_engine(settings.database_url, **_engine_kwargs())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
