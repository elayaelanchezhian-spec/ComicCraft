import io
import threading
from pathlib import Path

import httpx
from PIL import Image, UnidentifiedImageError

from app.config import PANELS_DIR, get_settings
from app.errors import ConfigurationError, GenerationError


_pipeline = None
_pipeline_lock = threading.Lock()


def _diffusers_image(prompt: str) -> Image.Image:
    global _pipeline

    with _pipeline_lock:
        if _pipeline is None:
            try:
                import torch
                from diffusers import StableDiffusionPipeline
            except ImportError as exc:
                raise ConfigurationError(
                    "The local Diffusers provider is selected but its optional "
                    "packages are missing. Install the 'images' project extra."
                ) from exc

            settings = get_settings()
            try:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                dtype = torch.float16 if device == "cuda" else torch.float32
                _pipeline = StableDiffusionPipeline.from_pretrained(
                    settings.image_model, torch_dtype=dtype
                )
                _pipeline.to(device)
            except (OSError, RuntimeError, ValueError) as exc:
                raise GenerationError(
                    f"Could not load Stable Diffusion model "
                    f"'{settings.image_model}': {exc}"
                ) from exc

        try:
            image = _pipeline(
                prompt,
                num_inference_steps=get_settings().image_steps,
                guidance_scale=7.5,
            ).images[0]
        except (OSError, RuntimeError, ValueError) as exc:
            raise GenerationError(f"Local illustration generation failed: {exc}") from exc

    return image


def _inference_image(prompt: str) -> Image.Image:
    settings = get_settings()
    if not settings.hf_api_key:
        raise ConfigurationError(
            "Hugging Face image generation is not configured. Set HF_API_KEY, "
            "or select IMAGE_PROVIDER=diffusers and install the image extra."
        )

    url = f"https://router.huggingface.co/hf-inference/models/{settings.image_model}"
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.hf_api_key}"},
            json={"inputs": prompt, "options": {"wait_for_model": True}},
            timeout=settings.image_timeout,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300].strip()
        raise GenerationError(
            f"Hugging Face image generation returned HTTP "
            f"{exc.response.status_code}: {detail or 'no further details'}"
        ) from exc
    except httpx.RequestError as exc:
        raise GenerationError(f"Hugging Face image request failed: {exc}") from exc

    try:
        image = Image.open(io.BytesIO(response.content))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise GenerationError(
            "Hugging Face did not return a valid image. Check that the selected "
            "model is available for inference."
        ) from exc

    return image


def generate_image(prompt: str, comic_id: str, panel_number: int) -> Path:
    """Generate one panel illustration and return its local static-file path."""
    settings = get_settings()
    if settings.image_provider == "diffusers":
        image = _diffusers_image(prompt)
    else:
        image = _inference_image(prompt)

    PANELS_DIR.mkdir(parents=True, exist_ok=True)
    image_path = PANELS_DIR / f"{comic_id}-{panel_number}.png"
    try:
        image.convert("RGB").save(image_path, format="PNG", optimize=True)
    except OSError as exc:
        raise GenerationError(f"Could not save the generated illustration: {exc}") from exc
    return image_path
