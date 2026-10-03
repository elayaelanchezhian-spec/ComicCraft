# ComicCraft

ComicCraft turns a short creative brief into a five-panel comic: Gemini creates
a structured outline and story, Stable Diffusion illustrates each panel, and
the app assembles a downloadable PDF. The application uses FastAPI, Jinja2, and
a responsive HTML/CSS frontend.

## Requirements

- Python 3.11 or newer
- A Google Gemini API key
- A Hugging Face access token with inference access, or a machine set up for
  local Diffusers image generation

## Run locally

From the project root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

In VS Code, open this folder and select `.venv\Scripts\python.exe` with
**Python: Select Interpreter** from the Command Palette. Use the integrated
PowerShell terminal for the commands below.

Add `GEMINI_API_KEY` and `HF_API_KEY` to `.env`. The default
`IMAGE_PROVIDER=hf_inference` calls Hugging Face's hosted inference router; use
a token permitted to access the configured image model. Then start the server:

```powershell
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> for the web app and
<http://127.0.0.1:8000/docs> for interactive API documentation.

### Accounts and sessions

Create an account from the home page before generating comics. User records are
stored in `data/comiccraft.sqlite3`; passwords are salted and hashed, and the
signed HTTP-only session uses a local secret in `data/.session_secret`. The
`data/` directory is ignored by Git. For a deployed HTTPS instance, set a
private `SESSION_SECRET` in the environment and `COOKIE_SECURE=true` before
starting the app. The development default keeps cookies usable over local HTTP.

### Local Diffusers image generation

To generate images locally, change `IMAGE_PROVIDER=diffusers` in `.env`, install
the optional image dependencies, and install a PyTorch build suited to your
hardware:

```powershell
pip install -e ".[images]"
```

The first local generation downloads the selected Stable Diffusion model and
may require several gigabytes of disk space and substantial RAM/VRAM. The model
ID, inference steps, and request timeout are configurable in `.env`.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `GEMINI_API_KEY` | Yes | — | Authenticates Gemini outline and story requests |
| `GEMINI_OUTLINE_MODEL` | No | `gemini-2.5-flash` | Model for structured five-panel outlines |
| `GEMINI_STORY_MODEL` | No | `gemini-2.5-pro` | Model for panel narration and dialogue |
| `IMAGE_PROVIDER` | No | `hf_inference` | `hf_inference` or local `diffusers` |
| `HF_API_KEY` | Hosted only | — | Hugging Face hosted image-inference token |
| `STABLE_DIFFUSION_MODEL` | No | `runwayml/stable-diffusion-v1-5` | Image model ID |
| `IMAGE_STEPS` | No | `25` | Diffusers inference steps |
| `IMAGE_TIMEOUT` | No | `180` | Hosted image request timeout in seconds |

Missing or rejected provider credentials are reported as actionable errors;
the app does not return placeholder or fabricated AI output.

## Routes

- `GET /` — comic creation form
- `POST /generate` — form-based comic generation and HTML preview
- `POST /generate-comic/json` — JSON comic generation API
- `GET /exports/{filename}` — download a generated PDF
- `GET /export-success` — export confirmation page
- `POST /test-image` — generate one illustration from a form-encoded prompt
- `GET /docs` — interactive OpenAPI documentation

Example JSON request:

```json
{
  "story_prompt": "A brave fox discovers a hidden garden beneath an old forest.",
  "character_name": "Mika",
  "setting": "An enchanted forest",
  "tone": "light-hearted",
  "art_style": "comic book"
}
```

The JSON response contains the comic ID, five panel objects, and a `pdf_url`.
The local image file paths are not exposed in the API response.

## Tests

Install the test extra and run:

```powershell
python -m pytest
```

The JSON generation and image-test routes also require the signed session cookie
created by signing in through the web app.
