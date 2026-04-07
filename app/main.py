from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.routers import auth, bookings, payments, teachers
from app.seed import ensure_seed_data


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_seed_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

def _parse_cors_origins(raw: str) -> list[str]:
    # Origin không có path; thừa "/" cuối trong env làm lệch so với header trình duyệt → OPTIONS 400.
    out: list[str] = []
    for part in raw.split(","):
        o = part.strip().rstrip("/")
        if o:
            out.append(o)
    return out


origins = _parse_cors_origins(settings.cors_origins)
regex = (settings.cors_origin_regex or "").strip() or None
# allow_credentials=True với allow_origins=["*"] là invalid — Starlette trả 400 preflight.
allow_origins_list: list[str] = ["*"]
if origins:
    allow_origins_list = origins
elif regex:
    allow_origins_list = []
credential_origins = bool(origins) or bool(regex)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins_list,
    allow_origin_regex=regex,
    allow_credentials=credential_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(teachers.router)
app.include_router(bookings.router)
app.include_router(payments.router)


@app.get("/health")
def health():
    return {"status": "ok"}
