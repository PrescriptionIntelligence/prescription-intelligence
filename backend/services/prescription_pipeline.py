import re

from backend.services.prescription_parser import extract_medicines
from backend.services.dose_calculator import calculate_daily_doses
from backend.services.prescription_validator import validate_medicines
from backend.services.safety_checker import (
    check_daily_dose_limits,
    check_duplicate_medicines,
    check_drug_interactions,
    check_ambiguous_medicines,
)


def _assess_ocr_quality(raw_text: str) -> dict:
    """
    Estimate the OCR text quality without making medical judgments.

    Returns a quality dict with:
      - score: 0-100
      - level: "good" | "fair" | "poor" | "failed"
      - issues: list of detected quality problems
    """

    if not raw_text or not raw_text.strip():
        return {"score": 0, "level": "failed", "issues": ["No text extracted"]}

    text = raw_text.strip()
    score = 0
    issues = []

    # Text length: longer text typically means better OCR
    word_count = len(text.split())
    if word_count >= 10:
        score += 30
    elif word_count >= 5:
        score += 15
    else:
        issues.append("Very short OCR output — may be incomplete")

    # Prescription keywords
    keywords = [
        "tab", "tablet", "cap", "capsule", "mg", "ml",
        "dose", "daily", "morning", "evening", "night",
        "once", "twice", "frequency", "duration",
    ]
    found_keywords = sum(
        1 for kw in keywords
        if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
    )
    score += min(found_keywords * 5, 30)

    if found_keywords < 2:
        issues.append("Few prescription-related terms found")

    # Garbled text check: too many non-alphanumeric characters
    non_alnum = len([c for c in text if not c.isalnum() and not c.isspace()])
    total_chars = max(len(text), 1)
    noise_ratio = non_alnum / total_chars
    if noise_ratio > 0.4:
        issues.append("High proportion of symbols — OCR noise likely")
    else:
        score += 20

    # Line structure
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) >= 3:
        score += 20
    elif len(lines) >= 1:
        score += 10
    else:
        issues.append("No line structure detected")

    score = min(max(score, 0), 100)

    if score >= 70:
        level = "good"
    elif score >= 40:
        level = "fair"
    else:
        level = "poor"
        if not issues:
            issues.append("OCR quality appears low — manual review recommended")

    return {
        "score": score,
        "level": level,
        "issues": issues,
        "word_count": word_count,
        "line_count": len(lines),
    }


def _compute_confidence_summary(medicines: list[dict]) -> dict:
    """
    Summarize confidence across all medicines.
    """
    if not medicines:
        return {
            "avg_extraction": None,
            "avg_normalization": None,
            "min_confidence": None,
            "needs_review_count": 0,
            "verified_count": 0,
        }

    extraction_confidences = [
        m["extraction_confidence"]
        for m in medicines
        if m.get("extraction_confidence") is not None
    ]
    normalization_confidences = [
        m["normalization_confidence"]
        for m in medicines
        if m.get("normalization_confidence") is not None
    ]

    all_confidences = extraction_confidences + normalization_confidences
    min_confidence = min(all_confidences) if all_confidences else None

    needs_review = sum(
        1 for m in medicines
        if m.get("needs_review") or
        (m.get("normalization_confidence") or 1.0) < 0.70 or
        (m.get("extraction_confidence") or 1.0) < 0.70
    )

    verified = sum(
        1 for m in medicines
        if not m.get("needs_review") and
        (m.get("normalization_confidence") or 0.0) >= 0.85 and
        (m.get("extraction_confidence") or 0.0) >= 0.80
    )

    return {
        "avg_extraction": (
            round(sum(extraction_confidences) / len(extraction_confidences), 3)
            if extraction_confidences else None
        ),
        "avg_normalization": (
            round(sum(normalization_confidences) / len(normalization_confidences), 3)
            if normalization_confidences else None
        ),
        "min_confidence": round(min_confidence, 3) if min_confidence is not None else None,
        "needs_review_count": needs_review,
        "verified_count": verified,
    }


def process_prescription(raw_text: str) -> dict:
    """
    Run the complete prescription intelligence pipeline.

    OCR text
        ↓
    OCR quality assessment
        ↓
    Medicine extraction
        ↓
    Daily dose calculation
        ↓
    Structural validation
        ↓
    Safety checks
        ↓
    Structured report
    """

    # 1. Assess OCR quality
    ocr_quality = _assess_ocr_quality(raw_text)

    # 2. Extract medicines
    medicines = extract_medicines(raw_text)

    # 3. Calculate daily doses
    medicines = calculate_daily_doses(medicines)

    # 4. Validate extracted data
    validation_flags = validate_medicines(medicines)

    # 5. Run safety checks
    safety_flags = []

    # If OCR produced text but no medicines could be extracted,
    # do not treat this as "no safety issues".
    if raw_text.strip() and not medicines:
        safety_flags.append(
            {
                "type": "ocr_extraction_failed",
                "severity": "warning",
                "medicine": None,
                "message": (
                    "No medicines could be reliably extracted from "
                    "the prescription. Please upload a clearer image "
                    "or verify the prescription manually."
                ),
            }
        )

    # Flag poor OCR quality
    if ocr_quality["level"] in ("poor", "failed"):
        safety_flags.append(
            {
                "type": "poor_ocr_quality",
                "severity": "warning",
                "medicine": None,
                "message": (
                    f"OCR quality is {ocr_quality['level']} "
                    f"(score: {ocr_quality['score']}/100). "
                    "Results may be incomplete. "
                    + (
                        "Issues: " + "; ".join(ocr_quality["issues"])
                        if ocr_quality["issues"]
                        else ""
                    )
                ),
            }
        )

    # Structural validation
    safety_flags.extend(validation_flags)

    # Duplicate medicine check
    safety_flags.extend(check_duplicate_medicines(medicines))

    # Drug interaction check
    safety_flags.extend(check_drug_interactions(medicines))

    # Ambiguous / low-confidence medicine check
    safety_flags.extend(check_ambiguous_medicines(medicines))

    # Daily dose limit check
    safety_flags.extend(check_daily_dose_limits(medicines))

    # 6. Compute analysis metadata
    confidence_summary = _compute_confidence_summary(medicines)

    analysis_metadata = {
        "ocr_quality": ocr_quality,
        "ocr_text_length": len(raw_text.strip()),
        "medicine_count": len(medicines),
        "safety_flag_count": len(safety_flags),
        "confidence_summary": confidence_summary,
        "needs_review": (
            ocr_quality["level"] in ("poor", "failed")
            or not medicines
            or confidence_summary["needs_review_count"] > 0
            or any(
                f.get("severity") in ("error", "high")
                for f in safety_flags
            )
        ),
    }

    return {
        "medicines": medicines,
        "safety_flags": safety_flags,
        "analysis_metadata": analysis_metadata,
    }
