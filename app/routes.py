import logging
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.auth import authenticate_user, create_user, get_user
from app.config import EXPORTS_DIR, PANELS_DIR, TEMPLATES_DIR
from app.errors import ComicCraftError
from app.exporters import save_pdf
from app.gemini_flash import generate_outline
from app.gemini_pro import generate_story
from app.image_generator import generate_image
from app.layout_builder import build_comic_layout
from app.schemas import ArtStyle, ComicResponse, PromptRequest, Tone


logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
EMAIL_PATTERN = re.compile(r"[^@\s]{1,64}@[^@\s.]+(?:\.[^@\s.]+)+")


def _session_user(request: Request):
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        return None
    user = get_user(user_id)
    if user is None:
        request.session.clear()
    return user


def _login_redirect(request: Request):
    if _session_user(request) is not None:
        return None
    return RedirectResponse(url="/login", status_code=303)


def _generate_comic(request_data: PromptRequest):
    comic_id = uuid4().hex
    image_files = []
    pdf_path = None
    try:
        outline = generate_outline(request_data)
        stories = generate_story(request_data, outline)
        for panel in outline:
            image_files.append(
                generate_image(panel.image_prompt, comic_id, panel.panel_number)
            )
        layout = build_comic_layout(outline, stories, image_files)
        pdf_path = EXPORTS_DIR / f"{comic_id}.pdf"
        save_pdf(layout, comic_id)
        return comic_id, layout, pdf_path
    except Exception:
        for image_file in image_files:
            image_file.unlink(missing_ok=True)
        if pdf_path is not None:
            pdf_path.unlink(missing_ok=True)
        raise


def _generation_error(request: Request, exc: ComicCraftError):
    logger.warning("Comic generation failed: %s", exc)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"error": str(exc), "auth_user": _session_user(request)},
        status_code=exc.status_code,
    )


@router.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"error": None, "auth_user": _session_user(request)},
    )


@router.get("/login", response_class=HTMLResponse, name="login")
def login(request: Request):
    if _session_user(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None}
    )


@router.post("/login", response_class=HTMLResponse, name="login_submit")
def login_submit(
    request: Request,
    email: str = Form(..., max_length=254),
    password: str = Form(..., min_length=1, max_length=128),
):
    if not EMAIL_PATTERN.fullmatch(email.strip()):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Enter a valid email address."},
            status_code=400,
        )

    user = authenticate_user(email, password)
    if user is None:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Email or password is incorrect."},
            status_code=401,
        )

    request.session.clear()
    request.session["user_id"] = user["id"]
    return RedirectResponse(url="/", status_code=303)


@router.get("/register", response_class=HTMLResponse, name="register")
def register(request: Request):
    if _session_user(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request=request, name="register.html", context={"error": None}
    )


@router.post("/register", response_class=HTMLResponse, name="register_submit")
def register_submit(
    request: Request,
    email: str = Form(..., max_length=254),
    password: str = Form(..., min_length=1, max_length=128),
    confirm_password: str = Form(..., min_length=1, max_length=128),
):
    error = None
    if not EMAIL_PATTERN.fullmatch(email.strip()):
        error = "Enter a valid email address."
    elif len(password) < 12:
        error = "Use a password with at least 12 characters."
    elif password != confirm_password:
        error = "The passwords do not match."

    if error:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": error},
            status_code=400,
        )

    try:
        user_id = create_user(email, password)
    except sqlite3.IntegrityError:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "An account with that email already exists."},
            status_code=409,
        )

    request.session.clear()
    request.session["user_id"] = user_id
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout", name="logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.post("/generate", response_class=HTMLResponse, name="generate")
def generate(
    request: Request,
    story_prompt: str = Form(..., min_length=10, max_length=1000),
    character_name: str = Form(..., min_length=1, max_length=80),
    setting: str = Form(..., min_length=1, max_length=120),
    tone: Tone = Form(...),
    art_style: ArtStyle = Form(...),
):
    login_response = _login_redirect(request)
    if login_response is not None:
        return login_response

    try:
        prompt = PromptRequest(
            story_prompt=story_prompt,
            character_name=character_name,
            setting=setting,
            tone=tone,
            art_style=art_style,
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": str(exc), "auth_user": _session_user(request)},
            status_code=422,
        )

    try:
        comic_id, layout, _ = _generate_comic(prompt)
    except ComicCraftError as exc:
        return _generation_error(request, exc)

    return templates.TemplateResponse(
        request=request,
        name="comic_preview.html",
        context={
            "comic_id": comic_id,
            "layout": layout,
            "pdf_url": f"/exports/{comic_id}.pdf",
        },
    )


@router.post("/test-image", name="test_image")
def test_image(
    request: Request, prompt: str = Form(..., min_length=3, max_length=1000)
):
    if _session_user(request) is None:
        raise HTTPException(status_code=401, detail="Sign in before generating images.")
    try:
        image_path = generate_image(prompt, uuid4().hex, 1)
    except ComicCraftError as exc:
        logger.warning("Test image generation failed: %s", exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return {
        "image_url": f"/static/panels/{image_path.name}",
        "filename": image_path.name,
    }


@router.post(
    "/generate-comic/json", response_model=ComicResponse, name="generate_comic_json"
)
def generate_comic_json(request: Request, prompt: PromptRequest):
    if _session_user(request) is None:
        raise HTTPException(status_code=401, detail="Sign in before generating a comic.")
    try:
        comic_id, layout, _ = _generate_comic(prompt)
    except ComicCraftError as exc:
        logger.warning("JSON comic generation failed: %s", exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return ComicResponse(
        comic_id=comic_id,
        panels=layout,
        pdf_url=f"/exports/{comic_id}.pdf",
    )


@router.get("/exports/{filename}", name="download_export")
def download_export(filename: str):
    if Path(filename).name != filename or not filename.endswith(".pdf"):
        raise HTTPException(status_code=404, detail="Comic PDF not found.")

    comic_id = filename[:-4]
    if len(comic_id) != 32 or any(char not in "0123456789abcdef" for char in comic_id):
        raise HTTPException(status_code=404, detail="Comic PDF not found.")

    pdf_path = EXPORTS_DIR / filename
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="Comic PDF not found.")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
    )


@router.get("/export-success", response_class=HTMLResponse, name="export_success")
def export_success(request: Request, downloaded: bool = False):
    return templates.TemplateResponse(
        request=request,
        name="export_success.html",
        context={"downloaded": downloaded},
    )
