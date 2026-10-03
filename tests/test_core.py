from uuid import uuid4

import pytest
from PIL import Image

from app.exporters import save_pdf
from app.errors import GenerationError
from app.layout_builder import build_comic_layout
from app.schemas import OutlinePanel, OutlineResponse, PanelStory, PromptRequest


def test_account_registration_login_and_logout(tmp_path, monkeypatch):
    import sqlite3

    import app.auth as auth
    from fastapi.testclient import TestClient

    from app.main import app

    database_path = tmp_path / "users.sqlite3"
    monkeypatch.setattr(auth, "DATABASE_PATH", database_path)
    password = "comiccraft-test-password"
    prompt_payload = {
        "story_prompt": "A fox finds a door beneath an old tree.",
        "character_name": "Mika",
        "setting": "An old forest",
        "tone": "light-hearted",
        "art_style": "comic book",
    }

    with TestClient(app) as client:
        assert client.get("/login").status_code == 200
        assert client.get("/register").status_code == 200
        assert client.post("/generate-comic/json", json=prompt_payload).status_code == 401

        short_password = client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "password": "short",
                "confirm_password": "short",
            },
        )
        assert short_password.status_code == 400

        registration = client.post(
            "/register",
            data={
                "email": "Reader@Example.com",
                "password": password,
                "confirm_password": password,
            },
            follow_redirects=False,
        )
        assert registration.status_code == 303
        assert "reader@example.com" in client.get("/").text

        duplicate = client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "password": password,
                "confirm_password": password,
            },
        )
        assert duplicate.status_code == 409

        assert client.post("/logout", follow_redirects=False).status_code == 303
        bad_login = client.post(
            "/login",
            data={"email": "reader@example.com", "password": "wrong-password"},
        )
        assert bad_login.status_code == 401
        good_login = client.post(
            "/login",
            data={"email": "reader@example.com", "password": password},
            follow_redirects=False,
        )
        assert good_login.status_code == 303
        assert client.get("/").status_code == 200

    with sqlite3.connect(database_path) as connection:
        stored_password = connection.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            ("reader@example.com",),
        ).fetchone()[0]
    assert password not in stored_password


def test_prompt_rejects_short_story_idea():
    with pytest.raises(ValueError):
        PromptRequest(
            story_prompt="Too short",
            character_name="Mika",
            setting="Forest",
            tone="funny",
            art_style="anime",
        )


def test_outline_requires_five_ordered_panels():
    with pytest.raises(ValueError):
        OutlineResponse(
            panels=[
                OutlinePanel(
                    panel_number=1,
                    title="Beginning",
                    scene_description="A fox enters the forest.",
                    image_prompt="A fox in a forest",
                )
            ]
        )


def test_layout_matches_story_to_panel_and_hides_local_image_path():
    from app.config import STATIC_DIR

    panel_dir = STATIC_DIR / "panels"
    panel_dir.mkdir(parents=True, exist_ok=True)
    image_files = []
    outline = []
    stories = []

    for number in range(1, 6):
        image_file = panel_dir / f"test-{uuid4().hex}.png"
        Image.new("RGB", (64, 64), color="white").save(image_file)
        image_files.append(image_file)
        outline.append(
            OutlinePanel(
                panel_number=number,
                title=f"Panel {number}",
                scene_description=f"Scene {number}",
                image_prompt=f"Image {number}",
            )
        )
        stories.append(
            PanelStory(
                panel_number=number,
                caption=f"Caption {number}",
                narration=f"Narration {number}",
                dialogue="",
            )
        )

    layout = build_comic_layout(outline, list(reversed(stories)), image_files)
    assert [panel.caption for panel in layout] == [
        f"Caption {number}" for number in range(1, 6)
    ]
    assert layout[0].image_url.startswith("/static/panels/")
    assert "image_file" not in layout[0].model_dump()

    for image_file in image_files:
        image_file.unlink()


def test_pdf_export_contains_five_panels():
    from app.config import EXPORTS_DIR

    comic_id = uuid4().hex
    panel_dir = EXPORTS_DIR.parent / "panels"
    panel_dir.mkdir(parents=True, exist_ok=True)
    image_files = []
    outline = []
    stories = []
    for number in range(1, 6):
        image_file = panel_dir / f"{comic_id}-{number}.png"
        Image.new("RGB", (96, 64), color="white").save(image_file)
        image_files.append(image_file)
        outline.append(
            OutlinePanel(
                panel_number=number,
                title=f"Panel {number}",
                scene_description=f"Scene {number}",
                image_prompt=f"Image {number}",
            )
        )
        stories.append(
            PanelStory(
                panel_number=number,
                caption=f"Caption {number}",
                narration=f"Narration {number}",
            )
        )

    layout = build_comic_layout(outline, stories, image_files)
    pdf_path = save_pdf(layout, comic_id)
    assert pdf_path.is_file()
    assert pdf_path.read_bytes().startswith(b"%PDF")

    pdf_path.unlink()
    for image_file in image_files:
        image_file.unlink()


def test_failed_generation_removes_images_created_so_far(tmp_path, monkeypatch):
    import app.routes as routes

    prompt = PromptRequest(
        story_prompt="A fox finds a door beneath an old tree.",
        character_name="Mika",
        setting="An old forest",
        tone="light-hearted",
        art_style="comic book",
    )
    outline = [
        OutlinePanel(
            panel_number=number,
            title=f"Panel {number}",
            scene_description=f"Scene {number}",
            image_prompt=f"Image {number}",
        )
        for number in range(1, 6)
    ]
    image_path = tmp_path / "partial.png"
    image_path.write_bytes(b"image")
    generated_count = 0

    monkeypatch.setattr(routes, "generate_outline", lambda _: outline)
    monkeypatch.setattr(routes, "generate_story", lambda *_: [])

    def generate_image(*_):
        nonlocal generated_count
        generated_count += 1
        if generated_count == 2:
            raise GenerationError("Image generation failed")
        return image_path

    monkeypatch.setattr(routes, "generate_image", generate_image)

    with pytest.raises(GenerationError, match="Image generation failed"):
        routes._generate_comic(prompt)

    assert not image_path.exists()
