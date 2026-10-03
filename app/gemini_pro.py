from google import genai
from google.genai import errors, types

from app.config import get_settings
from app.errors import ConfigurationError, GenerationError
from app.schemas import OutlinePanel, PanelStory, PromptRequest, StoryResponse


def generate_story(
    request: PromptRequest, outline: list[OutlinePanel]
) -> list[PanelStory]:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ConfigurationError(
            "Gemini is not configured. Set GEMINI_API_KEY in your .env file."
        )

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""
Write the narration and character dialogue for this five-panel comic. Preserve
the outline's events and panel order. Keep each panel's narration concise enough
to fit on a printed comic page. Make the requested tone clear, and give the main
character a consistent voice. Captions should be short ambient or scene-setting
text; narration should describe the action; dialogue should contain only spoken
words (an empty string is fine when nobody speaks).

Creator brief:
Story idea: {request.story_prompt}
Main character: {request.character_name}
Setting: {request.setting}
Tone: {request.tone}
Art style: {request.art_style}

Panel outline:
{[panel.model_dump() for panel in outline]}
""".strip()

    try:
        response = client.models.generate_content(
            model=settings.story_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=StoryResponse,
                temperature=0.9,
            ),
        )
        if not response.text:
            raise GenerationError("Gemini returned an empty comic story.")
        result = StoryResponse.model_validate_json(response.text)
    except errors.APIError as exc:
        raise GenerationError(f"Gemini story generation failed: {exc}") from exc
    except ValueError as exc:
        raise GenerationError(f"Gemini returned an invalid story: {exc}") from exc

    return result.panels
