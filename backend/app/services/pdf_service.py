import io
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .provider import ServiceError

FONT_DIR = Path(__file__).resolve().parents[1] / "fonts"
pdfmetrics.registerFont(
    TTFont("Care", os.getenv("PDF_FONT_PATH", str(FONT_DIR / "DejaVuSans.ttf")))
)
pdfmetrics.registerFont(
    TTFont("CareBold", os.getenv("PDF_BOLD_FONT_PATH", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
)
pdfmetrics.registerFontFamily(
    "Care", normal="Care", bold="CareBold", italic="Care", boldItalic="CareBold"
)
FALLBACK_FONTS = []
for path in sorted(FONT_DIR.glob("Noto*-Regular.ttf")):
    name = path.stem
    pdfmetrics.registerFont(TTFont(name, str(path)))
    FALLBACK_FONTS.append(name)
FOOTER = "AI assisted draft. Final prescription requires physician approval."


def multilingual_markup(text, default="Care"):
    """Embed supported scripts with shaping; never silently export missing-glyph boxes."""
    runs = []
    active, buffer = default, ""
    for char in str(text or "Not provided"):
        if char == "\n":
            if buffer:
                runs.append(f'<font name="{active}">{escape(buffer)}</font>')
            runs.append("<br/>")
            buffer = ""
            active = default
            continue
        if char in "\t\r":
            char = " "
        if unicodedata.category(char) == "Cc":
            continue
        selected = (
            active
            if (char.isspace() or ord(char) in pdfmetrics.getFont(active).face.charWidths)
            else next(
                (
                    name
                    for name in [default, *FALLBACK_FONTS]
                    if ord(char) in pdfmetrics.getFont(name).face.charWidths
                ),
                None,
            )
        )
        if selected is None:
            raise ServiceError(
                "PDF",
                f"The PDF font does not support character U+{ord(char):04X}. Use a supported spelling or install a suitable PDF font. The original record is still saved.",
                422,
            )
        if selected != active:
            if buffer:
                runs.append(f'<font name="{active}">{escape(buffer)}</font>')
                # Keep a script/font transition outside a shaped word.
                if not buffer[-1].isspace() and not char.isspace():
                    runs.append(" ")
            active, buffer = selected, ""
        buffer += char
    if buffer:
        runs.append(f'<font name="{active}">{escape(buffer)}</font>')
    return "".join(runs)


def generate_prescription_pdf(snapshot):
    """Return an immutable, clearly labeled clinical assistance draft, never a signed Rx."""
    output = io.BytesIO()
    ink, green = colors.HexColor("#183431"), colors.HexColor("#177C65")
    styles = {
        "body": ParagraphStyle(
            "body",
            fontName="Care",
            fontSize=9,
            leading=14,
            textColor=ink,
            spaceAfter=5,
            splitLongWords=True,
        ),
        "small": ParagraphStyle(
            "small", fontName="Care", fontSize=8, leading=12, textColor=colors.HexColor("#61726A")
        ),
        "id": ParagraphStyle("id", fontName="Care", fontSize=7, leading=11, textColor=ink),
        "h": ParagraphStyle(
            "h",
            fontName="CareBold",
            fontSize=11,
            leading=16,
            textColor=green,
            spaceBefore=13,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "title": ParagraphStyle(
            "title", fontName="CareBold", fontSize=20, leading=26, textColor=green
        ),
    }

    def p(text, style="body"):
        markup = multilingual_markup(text, styles[style].fontName)
        selected = (
            ParagraphStyle("shaped", parent=styles[style], shaping=True)
            if '<font name="Noto' in markup
            else styles[style]
        )
        return Paragraph(markup, selected)

    patient, report = snapshot["patient"], snapshot["report"]
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=56,
        title="Care - Clinical Assistance Draft",
        author="Care Intake",
    )
    story = [
        p("CARE AI HEALTHCARE", "title"),
        p("CLINICAL ASSISTANCE / PRESCRIPTION DRAFT", "h"),
        p("DRAFT - PHYSICIAN APPROVAL REQUIRED", "small"),
        Spacer(1, 12),
    ]
    generated = datetime.fromtimestamp(snapshot["created_at"], timezone.utc).strftime(
        "%d %b %Y, %H:%M:%S UTC"
    )
    identity = [
        [
            p("Patient"),
            p(patient["name"]),
            p("Age / Gender"),
            p(f"{patient['age']} / {patient['gender']}"),
        ],
        [
            p("Patient ID"),
            p(snapshot["patient_id"], "id"),
            p("Generated"),
            p(generated, "small"),
        ],
        [p("Draft ID"), p(snapshot["id"], "id"), p("Status"), p("AI-assisted draft")],
    ]
    table = Table(identity, colWidths=[66, 190, 75, 180], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F6F2")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#DDE9E0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(table)
    sections = [
        ("Clinical summary", report["summary"]),
        (
            "Symptoms and duration (patient reported)",
            f"{patient.get('symptoms') or 'Not provided'}\nDuration: {patient.get('duration') or 'Not provided'}",
        ),
        ("Medical history (patient reported)", patient.get("medical_history")),
        (
            "Allergies and current medicines (patient reported)",
            f"Allergies: {patient.get('allergies') or 'Not confirmed'}\nCurrent medicines: {patient.get('current_medicines') or 'Not confirmed'}\nAdditional medicine/allergy history: {patient.get('additional_details', {}).get('drug_and_allergy_history') or 'Not provided'}",
        ),
        ("AI assessment - unconfirmed", report["symptoms_analysis"]),
        (
            "Possible concerns for physician review",
            "\n".join(report["possible_conditions"])
            or "No concerns listed; this does not rule out illness.",
        ),
        (
            "Suggested review priority - not a validated risk score",
            report["severity"].replace("_", " "),
        ),
        (
            "Suggested management - doctor approval required",
            "No medicines or dosages are prescribed by this system. A physician must assess the patient and determine management.",
        ),
        (
            "Investigations for physician consideration",
            "\n".join(report["recommended_tests"]) or "None suggested; physician to decide.",
        ),
        ("General precautions", "\n".join(report["precautions"]) or "Physician guidance required."),
        (
            "Missing information",
            "\n".join(report.get("missing_details", [])) or "Clinician must verify completeness.",
        ),
        ("Doctor review notes", report["doctor_notes"]),
    ]
    for title, text in sections:
        story.extend([p(title, "h"), p(text)])
    if snapshot.get("human_summary"):
        story.append(p("User / reviewer amendments (separate from AI output)", "h"))
        for label, value in snapshot["human_summary"].items():
            story.extend([p(label, "h"), p(value)])
    if snapshot.get("review"):
        story.extend(
            [
                p("Recorded review", "h"),
                p(snapshot["review"].get("doctor_notes") or snapshot["review"].get("decision")),
                p(
                    "Review recorded by an authenticated account. This draft is not digitally signed.",
                    "small",
                ),
            ]
        )
    story.extend([Spacer(1, 16), p(FOOTER, "small")])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#DDE9E0"))
        canvas.line(42, 43, A4[0] - 42, 43)
        canvas.setFont("Care", 7)
        canvas.setFillColor(colors.HexColor("#61726A"))
        canvas.drawString(42, 30, FOOTER)
        canvas.drawRightString(A4[0] - 42, 18, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
