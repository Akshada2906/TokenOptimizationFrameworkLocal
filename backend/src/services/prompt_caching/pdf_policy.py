"""Create and read the inspectable 19-page expense-policy source document."""

from __future__ import annotations

import html
from pathlib import Path

from src.services.prompt_caching.policy_loader import load_policy


TARGET_POLICY_PAGES = 18  # plus a cover page = 19-page source PDF


def _page_chunks(text: str, target_pages: int = TARGET_POLICY_PAGES) -> list[list[str]]:
    """Split policy lines into readable, deliberately paginated PDF pages."""
    lines = [line for line in text.splitlines() if line.strip()]
    target_words = max(1, sum(len(line.split()) for line in lines) // target_pages)
    chunks: list[list[str]] = [[]]
    words = 0
    for line in lines:
        line_words = len(line.split())
        if len(chunks) < target_pages and words >= target_words and line.startswith("##"):
            chunks.append([])
            words = 0
        chunks[-1].append(line)
        words += line_words
    # Ensure the final planned pages exist even if a future policy revision has fewer headings.
    while len(chunks) < target_pages:
        largest = max(range(len(chunks)), key=lambda index: len(chunks[index]))
        source = chunks[largest]
        midpoint = max(1, len(source) // 2)
        chunks[largest:largest + 1] = [source[:midpoint], source[midpoint:]]
    return chunks


def generate_expense_policy_pdf(output_path: Path) -> Path:
    """Generate a selectable-text PDF from the policy used by the benchmark."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RuntimeError("PDF support is missing. Run: uv pip install -r backend/requirements.txt") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("PolicyTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=22, leading=28)
    subtitle = ParagraphStyle("PolicySubtitle", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=11, leading=15)
    heading = ParagraphStyle("PolicyHeading", parent=styles["Heading2"], fontSize=13, leading=16, spaceBefore=5, spaceAfter=6)
    body = ParagraphStyle("PolicyBody", parent=styles["BodyText"], fontSize=9.3, leading=12.5, spaceAfter=5)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#8a8a8a"))
        canvas.line(0.7 * inch, 0.52 * inch, LETTER[0] - 0.7 * inch, 0.52 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.7 * inch, 0.34 * inch, "Northstar Technologies — Internal Finance Policy")
        canvas.drawRightString(LETTER[0] - 0.7 * inch, 0.34 * inch, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(output_path), pagesize=LETTER, rightMargin=0.7 * inch, leftMargin=0.7 * inch,
        topMargin=0.68 * inch, bottomMargin=0.72 * inch,
    )
    story = [
        Spacer(1, 2.0 * inch),
        Paragraph("Northstar Technologies", title),
        Spacer(1, 0.2 * inch),
        Paragraph("Expense and Travel Policy", title),
        Spacer(1, 0.35 * inch),
        Paragraph("FY2026.3 · Finance Operations · Prompt-Caching POC Source Document", subtitle),
        Spacer(1, 0.3 * inch),
        Paragraph(
            "This is a synthetic internal policy document created for a controlled expense-policy "
            "classification and Gemini prompt-caching benchmark. It contains selectable text and "
            "is intentionally structured as a 19-page document: one cover page plus 18 policy pages.",
            subtitle,
        ),
        PageBreak(),
    ]
    for page_number, lines in enumerate(_page_chunks(load_policy()), 1):
        for line in lines:
            escaped = html.escape(line)
            if line.startswith("#"):
                escaped = escaped.lstrip("# ")
                story.append(Paragraph(escaped, heading))
            else:
                story.append(Paragraph(escaped, body))
        if page_number < TARGET_POLICY_PAGES:
            story.append(PageBreak())
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path


def extract_policy_pdf(pdf_path: Path) -> tuple[str, int]:
    """Extract selectable text and page count; scanned PDFs intentionally fail clearly."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF support is missing. Run: uv pip install -r backend/requirements.txt") from exc
    reader = PdfReader(str(pdf_path))
    text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    if len(text) < 1_000:
        raise RuntimeError(
            "The PDF has too little extractable text. Use a selectable-text PDF or add an OCR step before caching."
        )
    return text, len(reader.pages)
