"""
PDF Prescription Report Generator.

Renders the structured prescription intelligence report
into a professional, printable PDF.

This module does NOT perform medical reasoning.
It only presents already-generated prescription,
interpretation, and safety information.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

PAGE_WIDTH, PAGE_HEIGHT = A4

MARGIN_LEFT = 16 * mm
MARGIN_RIGHT = 16 * mm
MARGIN_TOP = 16 * mm
MARGIN_BOTTOM = 16 * mm


# ---------------------------------------------------------
# Text helpers
# ---------------------------------------------------------


def _text(
    value: Any,
    default: str = "—",
) -> str:
    """
    Safely convert a value into displayable text.
    """

    if value is None:
        return default

    value = str(value).strip()

    return value if value else default


def _format_confidence(
    value: Any,
) -> str:
    """
    Convert a 0..1 confidence value into a percentage.
    """

    if value is None:
        return "—"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"

    number = max(0.0, min(1.0, number))

    return f"{number * 100:.0f}%"


def _format_status(
    value: Any,
) -> str:
    """
    Convert internal snake_case status into a readable label.
    """

    text = _text(
        value,
        "Unknown",
    )

    return text.replace(
        "_",
        " ",
    ).title()


def _format_duration(
    duration: Any,
) -> str:
    """
    Format duration dictionaries used by the prescription plan.
    """

    if isinstance(duration, dict):
        value = duration.get("value")
        unit = duration.get("unit")

        if value is not None and unit:
            return f"{value:g} {unit}"

        if duration.get("text"):
            return _text(duration["text"])

    return _text(duration)


# ---------------------------------------------------------
# Styles
# ---------------------------------------------------------


def _build_styles():
    """
    Build isolated ReportLab styles.
    """

    styles = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "PrescriptionTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            alignment=TA_LEFT,
            spaceAfter=3 * mm,
        ),
        "subtitle": ParagraphStyle(
            "PrescriptionSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#5B6470"),
            spaceAfter=7 * mm,
        ),
        "section": ParagraphStyle(
            "PrescriptionSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            spaceBefore=5 * mm,
            spaceAfter=3 * mm,
        ),
        "body": ParagraphStyle(
            "PrescriptionBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#20252B"),
        ),
        "small": ParagraphStyle(
            "PrescriptionSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#66707A"),
        ),
        "table_header": ParagraphStyle(
            "PrescriptionTableHeader",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=colors.white,
        ),
        "table_body": ParagraphStyle(
            "PrescriptionTableBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#20252B"),
        ),
        "medicine_title": ParagraphStyle(
            "PrescriptionMedicineTitle",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            spaceAfter=2 * mm,
        ),
        "center": ParagraphStyle(
            "PrescriptionCenter",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
        ),
        "warning": ParagraphStyle(
            "PrescriptionWarning",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#7A4E00"),
        ),
    }


# ---------------------------------------------------------
# Page decoration
# ---------------------------------------------------------


def _draw_page_header_footer(
    canvas,
    document,
):
    """
    Draw a restrained header/footer on every page.
    """

    canvas.saveState()

    width, height = A4

    # Header line
    canvas.setStrokeColor(
        colors.HexColor("#D9DEE5")
    )
    canvas.setLineWidth(0.5)

    canvas.line(
        MARGIN_LEFT,
        height - 11 * mm,
        width - MARGIN_RIGHT,
        height - 11 * mm,
    )

    canvas.setFont(
        "Helvetica-Bold",
        7.5,
    )

    canvas.setFillColor(
        colors.HexColor("#5B6470")
    )

    canvas.drawString(
        MARGIN_LEFT,
        height - 8 * mm,
        "PRESCRIPTION INTELLIGENCE",
    )

    # Footer
    canvas.line(
        MARGIN_LEFT,
        10 * mm,
        width - MARGIN_RIGHT,
        10 * mm,
    )

    canvas.setFont(
        "Helvetica",
        7,
    )

    canvas.setFillColor(
        colors.HexColor("#7A838D")
    )

    canvas.drawString(
        MARGIN_LEFT,
        6.5 * mm,
        "AI-generated decision support • Human verification recommended",
    )

    canvas.drawRightString(
        width - MARGIN_RIGHT,
        6.5 * mm,
        f"Page {document.page}",
    )

    canvas.restoreState()


# ---------------------------------------------------------
# Section helpers
# ---------------------------------------------------------


def _section_title(
    title: str,
    styles: dict,
):
    return Paragraph(
        _text(title),
        styles["section"],
    )


def _key_value_table(
    rows: list[tuple[str, str]],
    styles: dict,
):
    data = []

    for label, value in rows:
        data.append(
            [
                Paragraph(
                    f"<b>{_text(label)}</b>",
                    styles["table_body"],
                ),
                Paragraph(
                    _text(value),
                    styles["table_body"],
                ),
            ]
        )

    table = Table(
        data,
        colWidths=[
            43 * mm,
            135 * mm,
        ],
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#F4F6F8"),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#D9DEE5"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    return table


# ---------------------------------------------------------
# Summary block
# ---------------------------------------------------------


def _summary_block(
    report: dict,
    styles: dict,
):
    summary = report.get(
        "summary",
        {},
    )

    status = report.get(
        "overall_status",
        "unknown",
    )

    safety_status = report.get(
        "safety_status",
        "unknown",
    )

    confidence = report.get(
        "confidence"
    )

    data = [
        [
            Paragraph(
                "<b>Overall status</b>",
                styles["table_body"],
            ),
            Paragraph(
                _format_status(status),
                styles["table_body"],
            ),
            Paragraph(
                "<b>Safety status</b>",
                styles["table_body"],
            ),
            Paragraph(
                _format_status(safety_status),
                styles["table_body"],
            ),
        ],
        [
            Paragraph(
                "<b>Medicines</b>",
                styles["table_body"],
            ),
            Paragraph(
                str(summary.get("medicine_count", 0)),
                styles["table_body"],
            ),
            Paragraph(
                "<b>Confidence</b>",
                styles["table_body"],
            ),
            Paragraph(
                _format_confidence(confidence),
                styles["table_body"],
            ),
        ],
        [
            Paragraph(
                "<b>Safety findings</b>",
                styles["table_body"],
            ),
            Paragraph(
                str(summary.get("issue_count", 0)),
                styles["table_body"],
            ),
            Paragraph(
                "<b>Review required</b>",
                styles["table_body"],
            ),
            Paragraph(
                "Yes"
                if status == "review_required"
                else "No",
                styles["table_body"],
            ),
        ],
    ]

    table = Table(
        data,
        colWidths=[
            32 * mm,
            50 * mm,
            35 * mm,
            61 * mm,
        ],
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#F7F9FB"),
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.7,
                    colors.HexColor("#D4DAE1"),
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#D9DEE5"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    return table


# ---------------------------------------------------------
# Medicine table
# ---------------------------------------------------------


def _medicine_table(
    medicines: list,
    styles: dict,
):
    header = [
        Paragraph("Medicine", styles["table_header"]),
        Paragraph("Strength", styles["table_header"]),
        Paragraph("Dose", styles["table_header"]),
        Paragraph("Route", styles["table_header"]),
        Paragraph("Frequency", styles["table_header"]),
        Paragraph("Duration", styles["table_header"]),
        Paragraph("Confidence", styles["table_header"]),
    ]

    rows = [header]

    for medicine in medicines:
        if not isinstance(medicine, dict):
            continue

        rows.append(
            [
                Paragraph(
                    _text(
                        medicine.get("generic_name")
                        or medicine.get("medicine")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _text(
                        medicine.get("strength")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _text(
                        medicine.get("dose")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _text(
                        medicine.get("route")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _text(
                        medicine.get("frequency")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _format_duration(
                        medicine.get("duration")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _format_confidence(
                        medicine.get("confidence")
                    ),
                    styles["table_body"],
                ),
            ]
        )

    if len(rows) == 1:
        rows.append(
            [
                Paragraph(
                    "No medicines detected",
                    styles["table_body"],
                ),
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )

    table = Table(
        rows,
        colWidths=[
            38 * mm,
            22 * mm,
            21 * mm,
            19 * mm,
            25 * mm,
            25 * mm,
            27 * mm,
        ],
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#263238"),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#D4DAE1"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F8F9FA"),
                    ],
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    return table


# ---------------------------------------------------------
# Safety findings
# ---------------------------------------------------------


def _safety_findings(
    report: dict,
    styles: dict,
):
    flowables = []

    medicines = report.get(
        "medicines",
        [],
    )

    has_findings = False

    for medicine in medicines:
        if not isinstance(medicine, dict):
            continue

        issues = medicine.get(
            "issues",
            [],
        )

        if not issues:
            continue

        has_findings = True

        title = _text(
            medicine.get("medicine"),
            "Unknown medicine",
        )

        medicine_block = [
            Paragraph(
                title,
                styles["medicine_title"],
            )
        ]

        for issue in issues:
            if not isinstance(issue, dict):
                continue

            severity = _text(
                issue.get("severity"),
                "low",
            ).upper()

            issue_title = _text(
                issue.get("title"),
                "Safety finding",
            )

            message = _text(
                issue.get("message"),
                "No additional information provided.",
            )

            medicine_block.append(
                Paragraph(
                    (
                        f"<b>{severity} · "
                        f"{issue_title}</b><br/>"
                        f"{message}"
                    ),
                    styles["body"],
                )
            )

            medicine_block.append(
                Spacer(
                    1,
                    2 * mm,
                )
            )

        flowables.append(
            KeepTogether(medicine_block)
        )

    prescription_issues = report.get(
        "prescription_issues",
        [],
    )

    if prescription_issues:
        has_findings = True

        flowables.append(
            Paragraph(
                "Prescription-level findings",
                styles["medicine_title"],
            )
        )

        for issue in prescription_issues:
            if not isinstance(issue, dict):
                continue

            severity = _text(
                issue.get("severity"),
                "low",
            ).upper()

            flowables.append(
                Paragraph(
                    (
                        f"<b>{severity} · "
                        f"{_text(issue.get('title'))}</b><br/>"
                        f"{_text(issue.get('message'))}"
                    ),
                    styles["body"],
                )
            )

            flowables.append(
                Spacer(
                    1,
                    2 * mm,
                )
            )

    if not has_findings:
        flowables.append(
            Paragraph(
                "✓ No structural prescription safety findings "
                "were detected by the current analysis.",
                styles["body"],
            )
        )

    return flowables


# ---------------------------------------------------------
# OCR section
# ---------------------------------------------------------


def _ocr_section(
    report: dict,
    styles: dict,
):
    prescription = report.get(
        "prescription",
        {},
    )

    metadata = report.get(
        "analysis_metadata",
        {},
    )

    raw_text = prescription.get(
        "raw_text"
    )

    ocr_quality = metadata.get(
        "ocr_quality",
        "unknown",
    )

    text_length = metadata.get(
        "ocr_text_length"
    )

    rows = [
        (
            "OCR quality",
            _format_status(ocr_quality),
        ),
        (
            "Extracted text length",
            _text(text_length),
        ),
    ]

    table = _key_value_table(
        rows,
        styles,
    )

    flowables = [
        table,
        Spacer(1, 3 * mm),
        Paragraph(
            "<b>Extracted prescription text</b>",
            styles["body"],
        ),
        Spacer(1, 1.5 * mm),
        Paragraph(
            _text(
                raw_text,
                "No OCR text available.",
            ).replace(
                "\n",
                "<br/>",
            ),
            styles["small"],
        ),
    ]

    return flowables


# ---------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------


def _disclaimer(styles: dict):
    table = Table(
        [
            [
                Paragraph(
                    (
                        "<b>Important:</b> This report is "
                        "AI-generated decision support. It does not "
                        "diagnose conditions, prescribe medicines, or "
                        "replace review by a qualified healthcare "
                        "professional."
                    ),
                    styles["warning"],
                )
            ]
        ],
        colWidths=[
            PAGE_WIDTH
            - MARGIN_LEFT
            - MARGIN_RIGHT,
        ],
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#FFF8E8"),
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.6,
                    colors.HexColor("#E5C477"),
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
            ]
        )
    )

    return table


# ---------------------------------------------------------
# Main PDF generator
# ---------------------------------------------------------


def generate_prescription_pdf(
    report: dict,
) -> bytes:
    """
    Render a structured prescription report into PDF bytes.

    Parameters
    ----------
    report:
        Output from build_prescription_report().

    Returns
    -------
    bytes
        Complete PDF document.
    """

    if not isinstance(report, dict):
        report = {}

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=MARGIN_RIGHT,
        leftMargin=MARGIN_LEFT,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        title="Prescription Intelligence Report",
        author="Prescription Intelligence",
        subject="AI-powered prescription intelligence report",
    )

    styles = _build_styles()

    prescription = report.get(
        "prescription",
        {},
    )

    if not isinstance(
        prescription,
        dict,
    ):
        prescription = {}

    prescription_id = _text(
        prescription.get(
            "prescription_id"
        ),
        "Not available",
    )

    file_name = _text(
        prescription.get(
            "file_name"
        ),
        "Not available",
    )

    generated_at = _text(
        report.get(
            "generated_at"
        ),
        "Not available",
    )

    story = []

    # Header
    story.append(
        Paragraph(
            "Prescription Intelligence",
            styles["title"],
        )
    )

    story.append(
        Paragraph(
            "AI-powered prescription intelligence and medication safety report",
            styles["subtitle"],
        )
    )

    story.append(
        _key_value_table(
            [
                (
                    "Prescription ID",
                    prescription_id,
                ),
                (
                    "Source file",
                    file_name,
                ),
                (
                    "Generated",
                    generated_at,
                ),
            ],
            styles,
        )
    )

    story.append(
        Spacer(
            1,
            3 * mm,
        )
    )

    # Overall analysis
    story.append(
        _section_title(
            "Overall Analysis",
            styles,
        )
    )

    story.append(
        _summary_block(
            report,
            styles,
        )
    )

    summary = report.get(
        "summary",
        {},
    )

    story.append(
        Spacer(
            1,
            3 * mm,
        )
    )

    story.append(
        Paragraph(
            _text(
                summary.get("message"),
                "No summary available.",
            ),
            styles["body"],
        )
    )

    # Medicines
    story.append(
        _section_title(
            "Medication Summary",
            styles,
        )
    )

    story.append(
        _medicine_table(
            report.get(
                "medicines",
                [],
            ),
            styles,
        )
    )

    # Safety
    story.append(
        _section_title(
            "Safety Analysis",
            styles,
        )
    )

    story.extend(
        _safety_findings(
            report,
            styles,
        )
    )

    # OCR
    story.append(
        _section_title(
            "OCR & Extraction",
            styles,
        )
    )

    story.extend(
        _ocr_section(
            report,
            styles,
        )
    )

    # Disclaimer
    story.append(
        Spacer(
            1,
            6 * mm,
        )
    )

    story.append(
        _disclaimer(
            styles,
        )
    )

    document.build(
        story,
        onFirstPage=_draw_page_header_footer,
        onLaterPages=_draw_page_header_footer,
    )

    return buffer.getvalue()