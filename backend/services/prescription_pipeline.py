import re

from backend.services.prescription_parser import extract_medicines
from backend.services.dose_calculator import calculate_daily_doses
from backend.services.prescription_validator import validate_medicines

from backend.services.prescription_interpreter import (
    interpret_prescription,
)

from backend.services.prescription_plan_builder import (
    build_prescription_plan,
)

from backend.services.prescription_safety import (
    analyze_prescription_safety,
)

from backend.services.safety_checker import (
    check_daily_dose_limits,
    check_duplicate_medicines,
    check_drug_interactions,
    check_ambiguous_medicines,
)


def _assess_ocr_quality(raw_text: str) -> dict:
    """
    Estimate OCR text quality without making medical judgments.

    Returns:
        score: 0-100
        level: good | fair | poor | failed
        issues: detected OCR quality problems
    """

    if not raw_text or not raw_text.strip():
        return {
            "score": 0,
            "level": "failed",
            "issues": ["No text extracted"],
        }

    text = raw_text.strip()

    score = 0
    issues = []

    # ---------------------------------------------------------
    # Text length
    # ---------------------------------------------------------

    word_count = len(text.split())

    if word_count >= 10:
        score += 30
    elif word_count >= 5:
        score += 15
    else:
        issues.append(
            "Very short OCR output — may be incomplete"
        )

    # ---------------------------------------------------------
    # Prescription keywords
    # ---------------------------------------------------------

    keywords = [
        "tab",
        "tablet",
        "cap",
        "capsule",
        "mg",
        "ml",
        "dose",
        "daily",
        "morning",
        "evening",
        "night",
        "once",
        "twice",
        "frequency",
        "duration",
    ]

    found_keywords = sum(
        1
        for keyword in keywords
        if re.search(
            r"\b" + re.escape(keyword) + r"\b",
            text,
            re.IGNORECASE,
        )
    )

    score += min(
        found_keywords * 5,
        30,
    )

    if found_keywords < 2:
        issues.append(
            "Few prescription-related terms found"
        )

    # ---------------------------------------------------------
    # Garbled OCR / symbol noise
    # ---------------------------------------------------------

    non_alnum = len(
        [
            char
            for char in text
            if not char.isalnum()
            and not char.isspace()
        ]
    )

    total_chars = max(
        len(text),
        1,
    )

    noise_ratio = (
        non_alnum / total_chars
    )

    if noise_ratio > 0.4:
        issues.append(
            "High proportion of symbols — OCR noise likely"
        )
    else:
        score += 20

    # ---------------------------------------------------------
    # Line structure
    # ---------------------------------------------------------

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if len(lines) >= 3:
        score += 20
    elif len(lines) >= 1:
        score += 10
    else:
        issues.append(
            "No line structure detected"
        )

    score = min(
        max(score, 0),
        100,
    )

    if score >= 70:
        level = "good"
    elif score >= 40:
        level = "fair"
    else:
        level = "poor"

        if not issues:
            issues.append(
                "OCR quality appears low — manual review recommended"
            )

    return {
        "score": score,
        "level": level,
        "issues": issues,
        "word_count": word_count,
        "line_count": len(lines),
    }


def _compute_confidence_summary(
    medicines: list[dict],
) -> dict:
    """
    Summarize confidence across extracted medicines.
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
        medicine["extraction_confidence"]
        for medicine in medicines
        if medicine.get(
            "extraction_confidence"
        ) is not None
    ]

    normalization_confidences = [
        medicine["normalization_confidence"]
        for medicine in medicines
        if medicine.get(
            "normalization_confidence"
        ) is not None
    ]

    all_confidences = (
        extraction_confidences
        + normalization_confidences
    )

    min_confidence = (
        min(all_confidences)
        if all_confidences
        else None
    )

    needs_review = sum(
        1
        for medicine in medicines
        if (
            medicine.get("needs_review")
            or (
                medicine.get(
                    "normalization_confidence"
                )
                or 1.0
            ) < 0.70
            or (
                medicine.get(
                    "extraction_confidence"
                )
                or 1.0
            ) < 0.70
        )
    )

    verified = sum(
        1
        for medicine in medicines
        if (
            not medicine.get("needs_review")
            and (
                medicine.get(
                    "normalization_confidence"
                )
                or 0.0
            ) >= 0.85
            and (
                medicine.get(
                    "extraction_confidence"
                )
                or 0.0
            ) >= 0.80
        )
    )

    return {
        "avg_extraction": (
            round(
                sum(extraction_confidences)
                / len(extraction_confidences),
                3,
            )
            if extraction_confidences
            else None
        ),
        "avg_normalization": (
            round(
                sum(normalization_confidences)
                / len(normalization_confidences),
                3,
            )
            if normalization_confidences
            else None
        ),
        "min_confidence": (
            round(
                min_confidence,
                3,
            )
            if min_confidence is not None
            else None
        ),
        "needs_review_count": needs_review,
        "verified_count": verified,
    }


def _build_interpreter_candidates(
    medicines: list[dict],
) -> list[dict]:
    """
    Convert parser medicine records into the candidate
    format expected by the medicine interpreter.

    The original parser records are preserved.

    This adapter exists so the interpretation layer can
    operate on the parser output without modifying the
    parser itself.
    """

    candidates = []

    for medicine in medicines:
        candidate = dict(medicine)

        # -----------------------------------------------------
        # Preserve the original medicine text.
        # -----------------------------------------------------

        if not candidate.get("text"):
            candidate["text"] = (
                candidate.get("raw_text")
                or candidate.get("medicine_text")
                or candidate.get("name")
                or ""
            )

        # -----------------------------------------------------
        # Medicine text expected by the interpreter.
        # -----------------------------------------------------

        if not candidate.get("medicine_text"):
            candidate["medicine_text"] = (
                candidate.get("name")
                or candidate.get("raw_name")
                or candidate.get("text")
                or ""
            )

        # -----------------------------------------------------
        # Confidence fields expected by the interpreter.
        # -----------------------------------------------------

        if candidate.get("ocr_confidence") is None:
            candidate["ocr_confidence"] = (
                candidate.get(
                    "extraction_confidence"
                )
                or 0.0
            )

        if candidate.get("candidate_score") is None:
            candidate["candidate_score"] = (
                candidate.get(
                    "normalization_confidence"
                )
                or 0.0
            )

        candidates.append(candidate)

    return candidates


def _merge_safety_flags(
    legacy_flags: list[dict],
    safety_analysis: dict,
) -> list[dict]:
    """
    Combine the existing safety-check flags with the newer
    prescription-safety analysis.

    Existing flags are preserved for backward compatibility.

    Safety-analysis issues are converted into the common
    safety flag shape only when they are not already represented.
    """

    combined = list(
        legacy_flags
    )

    existing_keys = set()

    for flag in combined:
        existing_keys.add(
            (
                flag.get("type"),
                flag.get("medicine"),
            )
        )

    medicines_analysis = safety_analysis.get(
        "medicines",
        [],
    )

    for medicine_report in medicines_analysis:
        medicine_name = (
            medicine_report.get(
                "normalized_name"
            )
            or medicine_report.get(
                "medicine"
            )
        )

        for issue in medicine_report.get(
            "issues",
            [],
        ):
            issue_type = issue.get(
                "type"
            )

            if not issue_type:
                continue

            key = (
                issue_type,
                medicine_name,
            )

            if key in existing_keys:
                continue

            combined.append(
                {
                    "type": issue_type,
                    "severity": issue.get(
                        "severity",
                        "low",
                    ),
                    "medicine": medicine_name,
                    "message": issue.get(
                        "message",
                        issue_type,
                    ),
                }
            )

            existing_keys.add(key)

    # ---------------------------------------------------------
    # Prescription-level safety issues
    # ---------------------------------------------------------

    for issue in safety_analysis.get(
        "prescription_issues",
        [],
    ):
        issue_type = issue.get(
            "type"
        )

        if not issue_type:
            continue

        key = (
            issue_type,
            None,
        )

        if key in existing_keys:
            continue

        combined.append(
            {
                "type": issue_type,
                "severity": issue.get(
                    "severity",
                    "low",
                ),
                "medicine": None,
                "message": issue.get(
                    "message",
                    issue_type,
                ),
            }
        )

        existing_keys.add(key)

    return combined


def process_prescription(
    raw_text: str,
) -> dict:
    """
    Run the complete prescription intelligence pipeline.

    Pipeline:

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
        Medicine interpretation
            ↓
        Prescription plan
            ↓
        Prescription safety analysis
            ↓
        Legacy safety checks
            ↓
        Unified pipeline result

    Important:
        This system is an interpretation and safety-support
        system. It does not diagnose, prescribe, or independently
        determine clinical appropriateness.
    """

    raw_text = raw_text or ""

    # =========================================================
    # 1. OCR quality
    # =========================================================

    ocr_quality = _assess_ocr_quality(
        raw_text
    )

    # =========================================================
    # 2. Medicine extraction
    # =========================================================

    medicines = extract_medicines(
        raw_text
    )

    # =========================================================
    # 3. Daily dose calculation
    # =========================================================

    medicines = calculate_daily_doses(
        medicines
    )

    # =========================================================
    # 4. Structural validation
    # =========================================================

    validation_flags = validate_medicines(
        medicines
    )

    # =========================================================
    # 5. Medicine interpretation
    # =========================================================

    interpreter_candidates = (
        _build_interpreter_candidates(
            medicines
        )
    )

    interpretation = interpret_prescription(
        interpreter_candidates
    )

    # =========================================================
    # 6. Prescription plan
    # =========================================================

    prescription_plan = build_prescription_plan(
        interpretation
    )

    # =========================================================
    # 7. New prescription-level safety analysis
    # =========================================================

    safety_analysis = analyze_prescription_safety(
        prescription_plan
    )

    # =========================================================
    # 8. Existing safety checks
    # =========================================================

    safety_flags = []

    # ---------------------------------------------------------
    # OCR extraction failure
    # ---------------------------------------------------------

    if raw_text.strip() and not medicines:
        safety_flags.append(
            {
                "type": "ocr_extraction_failed",
                "severity": "warning",
                "medicine": None,
                "message": (
                    "No medicines could be reliably extracted "
                    "from the prescription. Please upload a "
                    "clearer image or verify the prescription "
                    "manually."
                ),
            }
        )

    # ---------------------------------------------------------
    # Poor OCR quality
    # ---------------------------------------------------------

    if ocr_quality["level"] in (
        "poor",
        "failed",
    ):
        safety_flags.append(
            {
                "type": "poor_ocr_quality",
                "severity": "warning",
                "medicine": None,
                "message": (
                    f"OCR quality is "
                    f"{ocr_quality['level']} "
                    f"(score: "
                    f"{ocr_quality['score']}/100). "
                    "Results may be incomplete. "
                    + (
                        "Issues: "
                        + "; ".join(
                            ocr_quality["issues"]
                        )
                        if ocr_quality["issues"]
                        else ""
                    )
                ),
            }
        )

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    safety_flags.extend(
        validation_flags
    )

    # ---------------------------------------------------------
    # Duplicate medicines
    # ---------------------------------------------------------

    safety_flags.extend(
        check_duplicate_medicines(
            medicines
        )
    )

    # ---------------------------------------------------------
    # Drug interactions
    # ---------------------------------------------------------

    safety_flags.extend(
        check_drug_interactions(
            medicines
        )
    )

    # ---------------------------------------------------------
    # Ambiguous medicines
    # ---------------------------------------------------------

    safety_flags.extend(
        check_ambiguous_medicines(
            medicines
        )
    )

    # ---------------------------------------------------------
    # Daily dose limits
    # ---------------------------------------------------------

    safety_flags.extend(
        check_daily_dose_limits(
            medicines
        )
    )

    # =========================================================
    # 9. Merge new safety-analysis results
    # =========================================================

    safety_flags = _merge_safety_flags(
        safety_flags,
        safety_analysis,
    )

    # =========================================================
    # 10. Confidence summary
    # =========================================================

    confidence_summary = (
        _compute_confidence_summary(
            medicines
        )
    )

    # =========================================================
    # 11. Review state
    # =========================================================

    has_high_or_error = any(
        flag.get("severity")
        in (
            "error",
            "high",
        )
        for flag in safety_flags
    )

    has_medium = any(
        flag.get("severity")
        == "medium"
        for flag in safety_flags
    )

    interpretation_requires_review = (
        interpretation.get("review_required_count", 0)
        > 0
    )

    plan_requires_review = (
        prescription_plan.get(
            "review_required_count",
            0,
        )
        > 0
    )

    safety_requires_review = (
        safety_analysis.get(
            "safety_status"
        )
        == "review_required"
    )

    # =========================================================
    # 12. Analysis metadata
    # =========================================================

    analysis_metadata = {
        "ocr_quality": ocr_quality,
        "ocr_text_length": len(
            raw_text.strip()
        ),
        "medicine_count": len(
            medicines
        ),
        "safety_flag_count": len(
            safety_flags
        ),
        "confidence_summary": confidence_summary,

        "needs_review": (
            ocr_quality["level"]
            in (
                "poor",
                "failed",
            )
            or not medicines
            or confidence_summary[
                "needs_review_count"
            ] > 0
            or has_high_or_error
            or has_medium
            or interpretation_requires_review
            or plan_requires_review
            or safety_requires_review
        ),

        "interpretation_status": interpretation.get(
            "status"
        ),

        "prescription_plan_status": prescription_plan.get(
            "status"
        ),

        "safety_analysis_status": safety_analysis.get(
            "safety_status"
        ),
    }

    # =========================================================
    # 13. Unified result
    # =========================================================

    return {
        # Existing public pipeline outputs
        "medicines": medicines,
        "safety_flags": safety_flags,
        "analysis_metadata": analysis_metadata,

        # New intelligence layers
        "interpretation": interpretation,
        "prescription_plan": prescription_plan,
        "safety_analysis": safety_analysis,
    }