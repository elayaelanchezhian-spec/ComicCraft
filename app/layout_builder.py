from pathlib import Path

from app.config import STATIC_DIR
from app.errors import GenerationError
from app.schemas import ComicPanel, OutlinePanel, PanelStory


def build_comic_layout(
    outline: list[OutlinePanel],
    stories: list[PanelStory],
    image_files: list[Path],
) -> list[ComicPanel]:
    if len(outline) != 5 or len(stories) != 5 or len(image_files) != 5:
        raise GenerationError(
            "A comic must have exactly five outlines, stories, and illustrations."
        )

    story_by_number = {story.panel_number: story for story in stories}
    if len(story_by_number) != 5 or set(story_by_number) != {1, 2, 3, 4, 5}:
        raise GenerationError("The generated story panels are missing or duplicated.")

    layout = []
    for panel, image_file in zip(outline, image_files):
        story = story_by_number[panel.panel_number]
        try:
            relative_image = image_file.resolve().relative_to(STATIC_DIR.resolve())
        except ValueError as exc:
            raise GenerationError(
                "A generated illustration was saved outside the static directory."
            ) from exc

        layout.append(
            ComicPanel(
                panel_number=panel.panel_number,
                title=panel.title,
                scene_description=panel.scene_description,
                image_prompt=panel.image_prompt,
                caption=story.caption,
                narration=story.narration,
                dialogue=story.dialogue,
                image_url="/static/" + relative_image.as_posix(),
                image_file=image_file,
            )
        )

    return layout
