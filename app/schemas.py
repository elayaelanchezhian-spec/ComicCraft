from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Tone = Literal["light-hearted", "dramatic", "poetic", "funny"]
ArtStyle = Literal["anime", "pixel art", "comic book", "realistic"]


class PromptRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    story_prompt: str = Field(min_length=10, max_length=1000)
    character_name: str = Field(min_length=1, max_length=80)
    setting: str = Field(min_length=1, max_length=120)
    tone: Tone
    art_style: ArtStyle


class OutlinePanel(BaseModel):
    panel_number: int = Field(ge=1, le=5)
    title: str = Field(min_length=1, max_length=120)
    scene_description: str = Field(min_length=1, max_length=700)
    image_prompt: str = Field(min_length=1, max_length=1000)


class OutlineResponse(BaseModel):
    panels: list[OutlinePanel]

    @field_validator("panels")
    @classmethod
    def require_five_ordered_panels(
        cls, panels: list[OutlinePanel]
    ) -> list[OutlinePanel]:
        if len(panels) != 5 or [panel.panel_number for panel in panels] != [
            1,
            2,
            3,
            4,
            5,
        ]:
            raise ValueError("The outline must contain exactly five ordered panels.")
        return panels


class PanelStory(BaseModel):
    panel_number: int = Field(ge=1, le=5)
    caption: str = Field(min_length=1, max_length=300)
    narration: str = Field(min_length=1, max_length=800)
    dialogue: str = Field(default="", max_length=500)


class StoryResponse(BaseModel):
    panels: list[PanelStory]

    @field_validator("panels")
    @classmethod
    def require_five_ordered_panels(
        cls, panels: list[PanelStory]
    ) -> list[PanelStory]:
        if len(panels) != 5 or [panel.panel_number for panel in panels] != [
            1,
            2,
            3,
            4,
            5,
        ]:
            raise ValueError("The story must contain exactly five ordered panels.")
        return panels


class ComicPanel(BaseModel):
    panel_number: int
    title: str
    scene_description: str
    image_prompt: str
    caption: str
    narration: str
    dialogue: str
    image_url: str
    image_file: Path = Field(exclude=True, repr=False)


class ComicResponse(BaseModel):
    comic_id: str
    panels: list[ComicPanel]
    pdf_url: str
