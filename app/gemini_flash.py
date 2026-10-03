from google import genai
from google.genai import errors, types

from app.config import get_settings
from app.errors import ConfigurationError, GenerationError
from app.schemas import OutlinePanel, OutlineResponse, PromptRequest


def generate_outline(request: PromptRequest) -> list[OutlinePanel]:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ConfigurationError(
            "Gemini is not configured. Set GEMINI_API_KEY in your .env file."
        )

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""
Create a concise, coherent five-panel comic outline from the creator's brief.
The same named protagonist and visual design must remain consistent in every panel.
The five panels should form a complete story with a beginning, a turning point,
and a satisfying ending. Keep image prompts visual and do not ask the image model
to render readable words or lettering.

Creator brief:
Story idea: {request.story_prompt}
Main character: {request.character_name}
Setting: {request.setting}
Tone: {request.tone}
Art style: {request.art_style}
""".strip()

    try:
        response = client.models.generate_content(
            model=settings.outline_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OutlineResponse,
                temperature=0.8,
            ),
        )
        if not response.text:
            raise GenerationError("Gemini returned an empty comic outline.")
        result = OutlineResponse.model_validate_json(response.text)
    except errors.APIError as exc:
        raise GenerationError(f"Gemini outline generation failed: {exc}") from exc
    except ValueError as exc:
        raise GenerationError(f"Gemini returned an invalid outline: {exc}") from exc

    return result.panels
