"""Create and read the inspectable 19-page expense-policy source document."""

from __future__ import annotations

import html
from pathlib import Path


DATA_DIR = Path(__file__).with_name("data")

DESTINATION_BANDS = [
    ("Amsterdam", 290, 95), ("Atlanta", 235, 76), ("Austin", 245, 79),
    ("Bangalore", 185, 58), ("Bangkok", 170, 55), ("Barcelona", 275, 89),
    ("Beijing", 225, 70), ("Berlin", 255, 82), ("Boston", 315, 94),
    ("Chicago", 275, 86), ("Dallas", 230, 74), ("Denver", 245, 78),
    ("Dubai", 300, 96), ("Dublin", 285, 91), ("Frankfurt", 270, 86),
    ("Hong Kong", 330, 105), ("Houston", 235, 76), ("London", 345, 108),
    ("Los Angeles", 295, 92), ("Madrid", 250, 80), ("Melbourne", 270, 87),
    ("Mexico City", 185, 60), ("Miami", 265, 85), ("Minneapolis", 220, 72),
    ("Montreal", 230, 74), ("Mumbai", 175, 56), ("Munich", 280, 89),
    ("New York", 360, 112), ("Paris", 330, 104), ("Prague", 210, 68),
    ("San Francisco", 375, 116), ("Sao Paulo", 210, 67), ("Seattle", 305, 96),
    ("Seoul", 250, 80), ("Shanghai", 230, 73), ("Singapore", 310, 99),
    ("Sydney", 300, 95), ("Tokyo", 335, 106), ("Toronto", 260, 83),
    ("Vancouver", 255, 81), ("Vienna", 250, 79), ("Warsaw", 185, 59),
    ("Washington DC", 320, 100), ("Zurich", 365, 114),
]


def _regional_appendix() -> str:
    rows = [
        "## Appendix A — FY2026 destination allowances",
        "",
        "The following limits apply per business night and per eligible travel day. "
        "Hotel limits exclude tax and mandatory hotel fees. Meal limits include food, "
        "non-alcoholic beverages, tax, and tips. A city not listed uses the nearest "
        "geographic band's limit and requires Finance review before reimbursement.",
        "",
        "| Destination | Hotel per night (USD) | Meals per day (USD) |",
        "|---|---:|---:|",
    ]
    rows.extend(f"| {city} | {hotel} | {meals} |" for city, hotel, meals in DESTINATION_BANDS)
    return "\n".join(rows)


def _decision_examples() -> str:
    examples = [
        ("A receipt is USD 24.99", "No receipt threshold is triggered, but business purpose remains required."),
        ("A receipt is USD 25.00", "An itemized receipt is required; a card statement alone is insufficient."),
        ("A claim is filed 75 days later", "Manager reason-for-delay approval is required before Finance can complete review."),
        ("A flight has a nine-hour segment", "Premium economy still needs Vice President pre-approval."),
        ("A client dinner has three attendees", "The total cap is USD 450, and all attendee details are required."),
        ("A hotel has a personal weekend extension", "Only business nights and supported fare differences are eligible."),
        ("A software subscription costs USD 501", "Procurement approval must pre-date the purchase."),
        ("A laptop is split across invoices", "The combined equipment cost determines the purchase-order requirement."),
        ("A foreign receipt lacks conversion evidence", "The claim requires review; Finance cannot infer an exchange rate."),
        ("A manager approves a parking ticket", "Manager approval cannot override an always-prohibited expense."),
    ]
    lines = [
        "## Appendix B — Finance decision examples",
        "",
        "These examples clarify how the rules are applied. They do not create exceptions "
        "to Sections 1 through 8.",
    ]
    for number, (scenario, decision) in enumerate(examples, 1):
        lines.extend(("", f"### Example {number}: {scenario}", decision))
    return "\n".join(lines)


def _destination_guidance() -> str:
    lines = [
        "## Appendix C — destination application guidance",
        "",
        "Use these destination notes together with Sections 2 through 5. A rate above "
        "does not itself approve a nonstandard room, personal expense, missing receipt, "
        "or missing travel authorization. Employees must select a reasonable location "
        "near the business venue and retain an itemized lodging folio.",
    ]
    for city, hotel, meals in DESTINATION_BANDS:
        lines.extend((
            "",
            f"### {city}",
            f"For {city}, the standard single-occupancy lodging ceiling is USD {hotel} per "
            f"business night before tax and mandatory hotel fees. A rate over USD {hotel} "
            "requires an approved exception or documentation that an eligible conference "
            "hotel was the lowest logical option. Finance must not treat a personal room "
            "upgrade as eligible merely because the final amount remains below the ceiling.",
            f"The eligible travel-day meal ceiling for {city} is USD {meals}, including "
            "food, non-alcoholic beverages, tax, and tip. The ceiling does not make a meal "
            "eligible when it was provided by a hotel, airline, or event. Client alcohol and "
            "entertainment require the Section 5 attendee and business-purpose records. "
            "Foreign-currency claims still need original currency and conversion evidence.",
        ))
    return "\n".join(lines)


def load_policy() -> str:
    """Return the complete deterministic policy used to generate the benchmark PDF."""
    core = (DATA_DIR / "expense_policy.md").read_text(encoding="utf-8").strip()
    return "\n\n".join((core, _regional_appendix(), _decision_examples(), _destination_guidance())) + "\n"


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
