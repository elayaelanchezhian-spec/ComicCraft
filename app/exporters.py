import re
import unicodedata
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

from app.config import EXPORTS_DIR
from app.errors import GenerationError
from app.schemas import ComicPanel


def _pdf_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("latin-1", errors="replace").decode("latin-1")


def save_pdf(layout: list[ComicPanel], comic_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", comic_id):
        raise GenerationError("The comic identifier is invalid.")
    if len(layout) != 5:
        raise GenerationError("A comic PDF must contain exactly five panels.")

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORTS_DIR / f"{comic_id}.pdf"
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)

    for panel in layout:
        if not panel.image_file.is_file():
            raise GenerationError(
                f"The illustration for panel {panel.panel_number} is missing."
            )

        pdf.add_page()
        pdf.set_font("Helvetica", style="B", size=18)
        pdf.multi_cell(
            0,
            10,
            _pdf_text(f"Panel {panel.panel_number}: {panel.title}"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(2)

        image_y = pdf.get_y()
        max_width, max_height = pdf.epw, 112.0
        with Image.open(panel.image_file) as image:
            image_width, image_height = image.size
        scale = min(max_width / image_width, max_height / image_height)
        rendered_width = image_width * scale
        rendered_height = image_height * scale
        pdf.image(
            str(panel.image_file),
            x=pdf.l_margin + (max_width - rendered_width) / 2,
            y=image_y,
            w=rendered_width,
            h=rendered_height,
        )
        pdf.set_xy(pdf.l_margin, image_y + rendered_height + 6)

        pdf.set_font("Helvetica", style="I", size=10)
        pdf.multi_cell(
            0,
            6,
            _pdf_text(panel.scene_description),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.ln(2)
        pdf.set_font("Helvetica", style="B", size=10)
        pdf.multi_cell(
            0,
            6,
            _pdf_text(panel.caption),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(
            0,
            7,
            _pdf_text(panel.narration),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        if panel.dialogue:
            pdf.set_font("Helvetica", style="I", size=11)
            pdf.multi_cell(
                0,
                7,
                _pdf_text(f'“{panel.dialogue}”'),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

    pdf.output(str(output_path))
    return output_path
