import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import SignedSessionMiddleware, get_session_secret, initialize_auth_database
from app.config import EXPORTS_DIR, PANELS_DIR, STATIC_DIR
from app.routes import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    PANELS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    initialize_auth_database()
    yield


app = FastAPI(
    title="ComicCraft",
    description="Create illustrated five-panel comics with Gemini and Stable Diffusion.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    SignedSessionMiddleware,
    secret_key=get_session_secret(),
    cookie_name="comiccraft_session",
    max_age=60 * 60 * 24 * 14,
    secure=os.getenv("COOKIE_SECURE", "false").strip().lower() == "true",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)
