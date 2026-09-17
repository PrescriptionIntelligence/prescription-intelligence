"""
Evidence chain builder.

Produces a structured, explainable trace for each medicine detected
in the prescription:

  Prescription image
      ↓ OCR evidence
  Detected text
      ↓ Normalization evidence
  Normalized medicine
      ↓ Resolution evidence (local vocabulary or external hypothesis)
  Resolved identity
      ↓ Strength evidence
  Strength compatibility
      ↓ Safety-rule evidence
  Safety findings

Each evidence step carries:
  - source   : which system produced it
  - type     : what kind of evidence it is
  - value    : the evidence result (score, match, text, …)
  - note     : human-readable interpretation

This chain is pharmacist-facing decision-support context.
It does NOT expose internal filesystem paths, stored filenames,
secret keys, or implementation internals.
"""

from __future__ import annotations

from typing import Any


# =========================================================
# EVIDENCE STEP LABELS
# =========================================================

EVIDENCE_SOURCE_OCR = "OCR extraction"
EVIDENCE_SOURCE_LOCAL = "Local medicine vocabulary"
EVIDENCE_SOURCE_EXTERNAL = "External terminology (hypothesis only)"
EVIDENCE_SOURCE_STRENGTH = "Strength compatibility check"
EVIDENCE_SOURCE_SAFETY = "Safety rule evaluation"
EVIDENCE_SOURCE_RESOLUTION = "Medicine resolution"


def _pct(value: float | None) -> str:
    if value is None:
        return "unavailable"
    return f"{round(value * 100)}%"


def _bool_label(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "not checked"


def build_ocr_evidence(
    raw_text: str | None,
    ocr_confidence: float | None,
    ocr_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the OCR evidence step for one medicine.

    Args:
        raw_text:        The raw OCR text fragment for this medicine.
        ocr_confidence:  Per-medicine extraction confidence (0–1).
        ocr_quality:     Prescription-level OCR quality summary.
    """

    quality_level = None
    quality_issues: list[str] = []

    if isinstance(ocr_quality, dict):
        quality_level = ocr_quality.get("level")
        quality_issues = ocr_quality.get("issues") or []

    note_parts: list[str] = []

    if ocr_confidence is not None:
        if ocr_confidence >= 0.80:
            note_parts.append("Extraction confidence is high.")
        elif ocr_confidence >= 0.50:
            note_parts.append("Extraction confidence is moderate — review recommended.")
        else:
            note_parts.append("Extraction confidence is low — manual verification required.")

    if quality_level in ("poor", "failed"):
        note_parts.append(
            f"Overall OCR quality is {quality_level}."
            + (f" Issues: {'; '.join(quality_issues)}." if quality_issues else "")
        )

    return {
        "step": "ocr_extraction",
        "source": EVIDENCE_SOURCE_OCR,
        "detected_text": raw_text or "",
        "ocr_confidence": ocr_confidence,
        "ocr_confidence_label": _pct(ocr_confidence),
        "quality_level": quality_level,
        "note": " ".join(note_parts) if note_parts else "Text extracted from prescription image.",
    }


def build_normalization_evidence(
    original_text: str | None,
    normalized_name: str | None,
    normalization_confidence: float | None,
    matched_term: str | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build the normalization evidence step.

    Distinguishes between local vocabulary matches and their
    similarity scores.
    """

    note_parts: list[str] = []

    if original_text and normalized_name:
        if original_text.strip().lower() == normalized_name.strip().lower():
            note_parts.append("Exact name match in local medicine vocabulary.")
        else:
            note_parts.append(
                f"'{original_text}' normalized to '{normalized_name}'."
            )

    if normalization_confidence is not None:
        if normalization_confidence >= 0.85:
            note_parts.append(f"Normalization confidence: {_pct(normalization_confidence)}.")
        elif normalization_confidence >= 0.60:
            note_parts.append(
                f"Moderate normalization confidence ({_pct(normalization_confidence)}) — "
                "pharmacist verification recommended."
            )
        else:
            note_parts.append(
                f"Low normalization confidence ({_pct(normalization_confidence)}) — "
                "identity uncertain."
            )

    exact_match = None
    full_text_similarity = None
    token_similarity = None
    ocr_corrected = None

    if isinstance(evidence, dict):
        exact_match = evidence.get("exact_match")
        full_text_similarity = evidence.get("full_text_similarity")
        token_similarity = evidence.get("token_similarity")
        ocr_corrected = evidence.get("ocr_corrected")

    if exact_match is True:
        note_parts.append("Exact vocabulary term matched.")
    elif ocr_corrected is True:
        note_parts.append("OCR correction was applied during matching.")

    return {
        "step": "normalization",
        "source": EVIDENCE_SOURCE_LOCAL,
        "original_text": original_text or "",
        "normalized_name": normalized_name or "",
        "matched_term": matched_term or "",
        "normalization_confidence": normalization_confidence,
        "normalization_confidence_label": _pct(normalization_confidence),
        "exact_match": exact_match,
        "full_text_similarity": (
            round(full_text_similarity, 3)
            if isinstance(full_text_similarity, float)
            else None
        ),
        "token_similarity": (
            round(token_similarity, 3)
            if isinstance(token_similarity, float)
            else None
        ),
        "ocr_corrected": ocr_corrected,
        "note": " ".join(note_parts) if note_parts else "Medicine name looked up in local vocabulary.",
    }


def build_resolution_evidence(
    resolution: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build the resolution evidence step from medicine resolver output.

    Clearly distinguishes local vocabulary evidence from external
    terminology hypotheses.
    """

    if not isinstance(resolution, dict):
        return {
            "step": "resolution",
            "source": EVIDENCE_SOURCE_RESOLUTION,
            "status": "unavailable",
            "reason": "no_resolution_data",
            "is_external_hypothesis": False,
            "note": "Resolution data not available.",
        }

    status = resolution.get("status", "unknown")
    reason = resolution.get("reason", "")
    ev = resolution.get("evidence") or {}

    top_score = ev.get("top_score")
    second_score = ev.get("second_score")
    margin = ev.get("margin")
    strength_compatible = ev.get("strength_compatible")
    strength_reason = ev.get("strength_reason", "")
    is_external = ev.get("external_hypothesis", False)

    source = EVIDENCE_SOURCE_EXTERNAL if is_external else EVIDENCE_SOURCE_LOCAL

    note_parts: list[str] = []

    if status == "accepted":
        note_parts.append("Medicine identity resolved — accepted by local vocabulary.")
    elif status == "needs_review":
        if reason == "external_hypothesis_requires_review":
            note_parts.append(
                "Identity suggested by external terminology source. "
                "External hypotheses require pharmacist review — they are "
                "supporting evidence only, not clinical verification."
            )
        elif reason == "strength_conflict":
            note_parts.append(
                "Prescription strength does not match vocabulary reference. "
                "Pharmacist strength verification required."
            )
        elif reason == "ambiguous_match":
            note_parts.append(
                f"Multiple medicine candidates with similar scores "
                f"(margin: {round(margin, 3) if margin is not None else 'n/a'}). "
                "Pharmacist identification required."
            )
        elif reason == "poor_ocr_confidence":
            note_parts.append(
                "OCR confidence is too low to accept identity automatically. "
                "Manual review required."
            )
        else:
            note_parts.append("Medicine identity requires pharmacist review.")
    elif status == "unknown":
        note_parts.append(
            "Insufficient evidence to identify medicine. "
            "Manual review required."
        )
    else:
        note_parts.append(f"Resolution status: {status}.")

    if top_score is not None:
        note_parts.append(f"Best match score: {round(top_score, 3)}.")

    if second_score is not None and margin is not None:
        note_parts.append(f"Next candidate score: {round(second_score, 3)} (margin: {round(margin, 3)}).")

    return {
        "step": "resolution",
        "source": source,
        "status": status,
        "reason": reason,
        "top_score": round(top_score, 3) if isinstance(top_score, float) else top_score,
        "second_score": round(second_score, 3) if isinstance(second_score, float) else second_score,
        "margin": round(margin, 3) if isinstance(margin, float) else margin,
        "is_external_hypothesis": bool(is_external),
        "strength_compatible": strength_compatible,
        "strength_compatible_label": _bool_label(strength_compatible),
        "strength_reason": strength_reason,
        "note": " ".join(note_parts),
    }


def build_safety_evidence(
    safety_flags: list[dict[str, Any]] | None,
    medicine_name: str | None,
) -> dict[str, Any]:
    """
    Build the safety-rule evidence step for one medicine.

    Only includes safety flags relevant to this medicine.
    """

    flags = safety_flags or []

    relevant = [
        flag for flag in flags
        if isinstance(flag, dict) and (
            flag.get("medicine") == medicine_name
            or flag.get("medicine") is None
        )
    ]

    high_count = sum(
        1 for f in relevant
        if str(f.get("severity", "")).lower() in ("high", "error", "critical")
    )

    medium_count = sum(
        1 for f in relevant
        if str(f.get("severity", "")).lower() == "medium"
    )

    if high_count > 0:
        level = "review_required"
        note = f"{high_count} high-severity safety finding(s) require pharmacist review."
    elif medium_count > 0:
        level = "caution"
        note = f"{medium_count} medium-severity safety finding(s). Pharmacist attention recommended."
    elif relevant:
        level = "informational"
        note = "Informational safety findings only."
    else:
        level = "clear"
        note = "No safety rule findings for this medicine."

    return {
        "step": "safety_evaluation",
        "source": EVIDENCE_SOURCE_SAFETY,
        "finding_count": len(relevant),
        "high_severity_count": high_count,
        "medium_severity_count": medium_count,
        "level": level,
        "findings_summary": [
            {
                "type": f.get("type"),
                "severity": f.get("severity"),
                "message": f.get("message"),
            }
            for f in relevant[:5]  # limit to 5 to avoid response bloat
        ],
        "note": note,
    }


def build_medicine_evidence_chain(
    medicine: dict[str, Any],
    ocr_quality: dict[str, Any] | None,
    safety_flags: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """
    Build the complete evidence chain for one medicine.

    The chain covers every step from OCR detection to safety
    evaluation, making the result explainable.
    """

    raw_text = medicine.get("raw_text") or medicine.get("medicine_text") or ""
    ocr_confidence = medicine.get("extraction_confidence")
    normalization_confidence = medicine.get("normalization_confidence")
    # Use the pre-resolution text (raw OCR fragment or medicine_text) as
    # original_text for the normalization step. Never fall back to
    # medicine.get("name"), which is the post-resolution resolved name —
    # using it would create a misleading self-match in the evidence chain.
    original_text = (
        medicine.get("raw_text")
        or medicine.get("medicine_text")
        or ""
    )
    normalized_name = medicine.get("name") or ""
    matched_term = medicine.get("matched_term") or ""
    evidence = medicine.get("evidence") or {}
    resolution = medicine.get("resolution") or {}
    medicine_name = medicine.get("name") or medicine.get("generic_name")

    ocr_step = build_ocr_evidence(raw_text, ocr_confidence, ocr_quality)
    norm_step = build_normalization_evidence(
        original_text,
        normalized_name,
        normalization_confidence,
        matched_term,
        evidence,
    )
    resolution_step = build_resolution_evidence(resolution)
    safety_step = build_safety_evidence(safety_flags, medicine_name)

    return {
        "chain": [ocr_step, norm_step, resolution_step, safety_step],
        "summary": {
            "ocr_confidence": ocr_confidence,
            "normalization_confidence": normalization_confidence,
            "resolution_status": resolution_step["status"],
            "is_external_hypothesis": resolution_step["is_external_hypothesis"],
            "safety_level": safety_step["level"],
        },
    }
