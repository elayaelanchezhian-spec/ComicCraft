import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from app.errors import ConfigurationError


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
PANELS_DIR = STATIC_DIR / "panels"
EXPORTS_DIR = STATIC_DIR / "exports"
TEMPLATES_DIR = BASE_DIR / "templates"

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    hf_api_key: str | None
    outline_model: str
    story_model: str
    image_model: str
    image_provider: str
    image_steps: int
    image_timeout: float


@lru_cache
def get_settings() -> Settings:
    provider = os.getenv("IMAGE_PROVIDER", "hf_inference").strip().lower()
    if provider not in {"hf_inference", "diffusers"}:
        raise ConfigurationError(
            "IMAGE_PROVIDER must be 'hf_inference' or 'diffusers'."
        )

    try:
        image_steps = int(os.getenv("IMAGE_STEPS", "25"))
        image_timeout = float(os.getenv("IMAGE_TIMEOUT", "180"))
    except ValueError as exc:
        raise ConfigurationError(
            "IMAGE_STEPS and IMAGE_TIMEOUT must be valid numbers."
        ) from exc

    if image_steps < 1 or image_timeout <= 0:
        raise ConfigurationError(
            "IMAGE_STEPS and IMAGE_TIMEOUT must be greater than zero."
        )

    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        hf_api_key=os.getenv("HF_API_KEY") or None,
        outline_model=os.getenv("GEMINI_OUTLINE_MODEL", "gemini-2.5-flash"),
        story_model=os.getenv("GEMINI_STORY_MODEL", "gemini-2.5-pro"),
        image_model=os.getenv(
            "STABLE_DIFFUSION_MODEL", "runwayml/stable-diffusion-v1-5"
        ),
        image_provider=provider,
        image_steps=image_steps,
        image_timeout=image_timeout,
    )
