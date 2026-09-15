"""
PDF Prescription Report Generator.

Renders the structured prescription intelligence report
into a professional, printable PDF.

This module does NOT perform medical reasoning.
It only presents already-generated prescription,
interpretation, safety, OCR, and pharmacist-review data.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
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
    Convert a 0..1 or percentage-style confidence value
    into a percentage.
    """

    if value is None:
        return "—"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"

    if number > 1:
        number = number / 100.0

    number = max(
        0.0,
        min(1.0, number),
    )

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


def _format_review_status(
    value: Any,
) -> str:
    """
    Convert review status into a compact uppercase label.
    """

    text = _text(
        value,
        "PENDING",
    )

    return text.replace(
        "_",
        " ",
    ).upper()


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
            try:
                numeric_value = float(value)

                if numeric_value.is_integer():
                    value_text = str(
                        int(numeric_value)
                    )
                else:
                    value_text = str(
                        numeric_value
                    )

            except (TypeError, ValueError):
                value_text = str(value)

            return f"{value_text} {unit}"

        if duration.get("text"):
            return _text(
                duration["text"]
            )

    return _text(duration)


def _format_datetime(
    value: Any,
) -> str:
    """
    Convert a datetime or ISO timestamp into a readable
    UTC timestamp.
    """

    if value is None:
        return "—"

    try:
        from datetime import datetime, timezone

        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()

            if not text:
                return "—"

            dt = datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00",
                )
            )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        dt = dt.astimezone(timezone.utc)

        return dt.strftime(
            "%d %b %Y, %I:%M %p UTC"
        )

    except (
        TypeError,
        ValueError,
    ):
        return _text(value)


def _escape_paragraph_text(
    value: Any,
) -> str:
    """
    Escape text that will be inserted into ReportLab
    Paragraph markup.
    """

    text = _text(
        value,
        "",
    )

    return (
        text.replace(
            "&",
            "&amp;",
        )
        .replace(
            "<",
            "&lt;",
        )
        .replace(
            ">",
            "&gt;",
        )
    )


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
            textColor=colors.HexColor("#17211D"),
            spaceAfter=3 * mm,
        ),

        "subtitle": ParagraphStyle(
            "PrescriptionSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#526158"),
            spaceAfter=7 * mm,
        ),

        "section": ParagraphStyle(
            "PrescriptionSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#17211D"),
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
            textColor=colors.HexColor("#17211D"),
            spaceAfter=2 * mm,
        ),

        "warning": ParagraphStyle(
            "PrescriptionWarning",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=12,
            textColor=colors.HexColor("#7A4E00"),
        ),

        "review": ParagraphStyle(
            "PrescriptionReview",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#20252B"),
        ),

        "audit": ParagraphStyle(
            "PrescriptionAudit",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#526158"),
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

    canvas.setStrokeColor(
        colors.HexColor("#D9E2DC")
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
        colors.HexColor("#526158")
    )

    canvas.drawString(
        MARGIN_LEFT,
        height - 8 * mm,
        "PRESCRIPTION INTELLIGENCE",
    )

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
                    f"<b>{_escape_paragraph_text(label)}</b>",
                    styles["table_body"],
                ),
                Paragraph(
                    _escape_paragraph_text(value),
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
                    colors.HexColor("#F4F7F5"),
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#DFE6E1"),
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

    confidence = report.get("confidence")

    if confidence is None:
        summary_confidence = summary.get("confidence")

        if summary_confidence is not None:
            confidence = summary_confidence

    review = report.get(
        "review",
        {},
    )

    if not isinstance(
        review,
        dict,
    ):
        review = {}

    review_status = _format_review_status(
        review.get(
            "review_status",
            "pending",
        )
    )

    data = [
        [
            Paragraph(
                "<b>Medicines detected</b>",
                styles["table_body"],
            ),
            Paragraph(
                str(
                    summary.get(
                        "medicine_count",
                        0,
                    )
                ),
                styles["table_body"],
            ),
            Paragraph(
                "<b>Intelligence confidence</b>",
                styles["table_body"],
            ),
            Paragraph(
                _format_confidence(
                    confidence
                ),
                styles["table_body"],
            ),
        ],
        [
            Paragraph(
                "<b>Safety findings</b>",
                styles["table_body"],
            ),
            Paragraph(
                str(
                    summary.get(
                        "issue_count",
                        0,
                    )
                ),
                styles["table_body"],
            ),
            Paragraph(
                "<b>Review status</b>",
                styles["table_body"],
            ),
            Paragraph(
                review_status,
                styles["table_body"],
            ),
        ],
    ]

    table = Table(
        data,
        colWidths=[
            40 * mm,
            42 * mm,
            42 * mm,
            54 * mm,
        ],
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#F7FAF8"),
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.7,
                    colors.HexColor("#D4DED7"),
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    colors.HexColor("#DFE6E1"),
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
                    _escape_paragraph_text(
                        medicine.get("generic_name")
                        or medicine.get("medicine")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _escape_paragraph_text(
                        medicine.get("strength")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _escape_paragraph_text(
                        medicine.get("dose")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _escape_paragraph_text(
                        medicine.get("route")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _escape_paragraph_text(
                        medicine.get("frequency")
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _escape_paragraph_text(
                        _format_duration(
                            medicine.get("duration")
                        )
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
                _escape_paragraph_text(title),
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
                        f"<b>{_escape_paragraph_text(severity)} · "
                        f"{_escape_paragraph_text(issue_title)}</b>"
                        f"<br/>"
                        f"{_escape_paragraph_text(message)}"
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
            KeepTogether(
                medicine_block
            )
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
                        f"<b>{_escape_paragraph_text(severity)} · "
                        f"{_escape_paragraph_text(issue.get('title'))}</b>"
                        f"<br/>"
                        f"{_escape_paragraph_text(issue.get('message'))}"
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
                "<b>Safety findings: 0</b>",
                styles["body"],
            )
        )

        flowables.append(
            Spacer(
                1,
                1.5 * mm,
            )
        )

        flowables.append(
            Paragraph(
                "No structural prescription safety findings "
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

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}

    raw_text = prescription.get(
        "raw_text"
    )

    ocr_quality_data = metadata.get(
        "ocr_quality"
    )

    # -----------------------------------------------------
    # Support structured OCR quality metadata
    # -----------------------------------------------------

    if isinstance(
        ocr_quality_data,
        dict,
    ):
        score = ocr_quality_data.get(
            "score"
        )

        level = ocr_quality_data.get(
            "level"
        )

        issues = ocr_quality_data.get(
            "issues",
            [],
        )

        word_count = ocr_quality_data.get(
            "word_count"
        )

        line_count = ocr_quality_data.get(
            "line_count"
        )

    else:
        score = metadata.get(
            "ocr_score"
        )

        level = ocr_quality_data

        issues = metadata.get(
            "ocr_issues",
            [],
        )

        word_count = metadata.get(
            "ocr_word_count"
        )

        line_count = metadata.get(
            "ocr_line_count"
        )

    # -----------------------------------------------------
    # Fall back to common metadata names
    # -----------------------------------------------------

    if word_count is None:
        word_count = metadata.get(
            "word_count"
        )

    if line_count is None:
        line_count = metadata.get(
            "line_count"
        )

    if score is None:
        score = metadata.get(
            "ocr_quality_score"
        )

    if level is None:
        level = metadata.get(
            "ocr_quality_level"
        )

    if not isinstance(
        issues,
        list,
    ):
        issues = []

    if not issues:
        issues_text = "None"
    else:
        issues_text = "; ".join(
            str(issue)
            for issue in issues
        )

    rows = [
        (
            "Score",
            (
                f"{float(score):.0f}%"
                if score is not None
                else "—"
            ),
        ),
        (
            "Quality",
            _format_status(
                level
            ),
        ),
        (
            "Words",
            _text(word_count),
        ),
        (
            "Lines",
            _text(line_count),
        ),
        (
            "Issues",
            issues_text,
        ),
    ]

    text_length = metadata.get(
        "ocr_text_length"
    )

    if text_length is not None:
        rows.append(
            (
                "Extracted text length",
                _text(text_length),
            )
        )

    table = _key_value_table(
        rows,
        styles,
    )

    flowables = [
        Paragraph(
            "<b>OCR Quality</b>",
            styles["body"],
        ),
        Spacer(
            1,
            1.5 * mm,
        ),
        table,
        Spacer(
            1,
            3 * mm,
        ),
        Paragraph(
            "<b>Extracted Prescription Text</b>",
            styles["body"],
        ),
        Spacer(
            1,
            1.5 * mm,
        ),
        Paragraph(
            _escape_paragraph_text(
                raw_text
                or "No OCR text available."
            ).replace(
                "\n",
                "<br/>",
            ),
            styles["small"],
        ),
    ]

    return flowables


# ---------------------------------------------------------
# Pharmacist verification
# ---------------------------------------------------------


def _review_section(
    report: dict,
    styles: dict,
):
    review = report.get(
        "review",
        {},
    )

    if not isinstance(
        review,
        dict,
    ):
        review = {}

    status = _format_review_status(
        review.get(
            "review_status",
            "pending",
        )
    )

    reviewer = review.get(
        "reviewer",
        {},
    )

    if not isinstance(
        reviewer,
        dict,
    ):
        reviewer = {}

    reviewer_name = (
        reviewer.get("name")
        or review.get("reviewer_name")
        or "—"
    )

    reviewed_at = review.get(
        "reviewed_at"
    )

    review_notes = review.get(
        "review_notes"
    )

    rows = [
        (
            "Status",
            status,
        ),
        (
            "Reviewer",
            _text(reviewer_name),
        ),
    ]

    if reviewed_at:
        rows.append(
            (
                "Completed",
                _format_datetime(
                    reviewed_at
                ),
            )
        )

    flowables = [
        _key_value_table(
            rows,
            styles,
        )
    ]

    if review_notes:
        flowables.extend(
            [
                Spacer(
                    1,
                    2 * mm,
                ),
                Paragraph(
                    (
                        "<b>Review notes</b><br/>"
                        f"{_escape_paragraph_text(review_notes)}"
                    ),
                    styles["review"],
                ),
            ]
        )

    return flowables


# ---------------------------------------------------------
# Review history
# ---------------------------------------------------------


def _review_history_section(
    report: dict,
    styles: dict,
):
    review = report.get(
        "review",
        {},
    )

    if not isinstance(
        review,
        dict,
    ):
        return []

    audits = review.get(
        "audits",
        [],
    )

    if not isinstance(
        audits,
        list,
    ):
        audits = []

    if not audits:
        return [
            Paragraph(
                "No pharmacist review actions have been recorded.",
                styles["small"],
            )
        ]

    rows = [
        [
            Paragraph(
                "Action",
                styles["table_header"],
            ),
            Paragraph(
                "Status transition",
                styles["table_header"],
            ),
            Paragraph(
                "Reviewer",
                styles["table_header"],
            ),
            Paragraph(
                "Timestamp",
                styles["table_header"],
            ),
        ]
    ]

    reviewer = review.get(
        "reviewer",
        {},
    )

    if not isinstance(
        reviewer,
        dict,
    ):
        reviewer = {}

    for audit in audits:
        if not isinstance(
            audit,
            dict,
        ):
            continue

        action = _format_status(
            audit.get(
                "action"
            )
        )

        previous_status = _format_review_status(
            audit.get(
                "previous_status"
            )
        )

        new_status = _format_review_status(
            audit.get(
                "new_status"
            )
        )

        audit_reviewer = (
            audit.get("reviewer_name")
            or reviewer.get("name")
            or "—"
        )

        rows.append(
            [
                Paragraph(
                    _escape_paragraph_text(
                        action
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    (
                        f"{_escape_paragraph_text(previous_status)} "
                        f"-> "
                        f"{_escape_paragraph_text(new_status)}"  
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _escape_paragraph_text(
                        audit_reviewer
                    ),
                    styles["table_body"],
                ),
                Paragraph(
                    _escape_paragraph_text(
                        _format_datetime(
                            audit.get(
                                "created_at"
                            )
                        )
                    ),
                    styles["table_body"],
                ),
            ]
        )

    table = Table(
        rows,
        colWidths=[
            31 * mm,
            50 * mm,
            34 * mm,
            59 * mm,
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
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#F8F9FA"),
                    ],
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

    return [table]


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
                        "professional. Pharmacist verification recorded "
                        "in this report reflects the review workflow "
                        "status and does not constitute autonomous "
                        "clinical decision-making."
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
    """

    if not isinstance(
        report,
        dict,
    ):
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

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Analysis Overview
    # -----------------------------------------------------

    story.append(
        _section_title(
            "Analysis Overview",
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
            _escape_paragraph_text(
                summary.get(
                    "message",
                    "No summary available.",
                )
            ),
            styles["body"],
        )
    )

    # -----------------------------------------------------
    # Medication Summary
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Safety Analysis
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # OCR & Extraction
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Pharmacist Verification
    # -----------------------------------------------------

    review = report.get(
        "review",
        {},
    )

    if isinstance(
        review,
        dict,
    ) and review.get(
        "review_status"
    ):
        story.append(
            _section_title(
                "Pharmacist Verification",
                styles,
            )
        )

        story.extend(
            _review_section(
                report,
                styles,
            )
        )

        story.append(
            Spacer(
                1,
                2 * mm,
            )
        )

        story.append(
            Paragraph(
                "<b>Review History</b>",
                styles["body"],
            )
        )

        story.append(
            Spacer(
                1,
                1.5 * mm,
            )
        )

        story.extend(
            _review_history_section(
                report,
                styles,
            )
        )

    # -----------------------------------------------------
    # Disclaimer
    # -----------------------------------------------------

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