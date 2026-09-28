"""Loads the stable policy document used as the explicit Gemini cache content."""

from pathlib import Path


DATA_DIR = Path(__file__).with_name("data")

# These published internal travel bands deliberately make the POC policy a realistic
# long-lived document, rather than padding it with repeated filler text.
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
    """Detailed annual guidance is policy content, not artificial cache padding."""
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
    """Return the complete, immutable policy cached for each benchmark run."""
    core = (DATA_DIR / "expense_policy.md").read_text(encoding="utf-8").strip()
    return "\n\n".join((core, _regional_appendix(), _decision_examples(), _destination_guidance())) + "\n"
