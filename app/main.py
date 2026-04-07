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

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
# CORS: allow_credentials=True is invalid with allow_origins=["*"] — browsers get OPTIONS 400.
credential_origins = bool(origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
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
