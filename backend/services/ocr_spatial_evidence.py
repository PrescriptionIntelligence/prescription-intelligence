"""
Spatial OCR evidence for prescription analysis.

This module does NOT make clinical decisions.

Its purpose is to take word-level OCR output, preserve the spatial
relationship between words, and generate conservative medicine-related
evidence that can be used when selecting OCR candidates.

Medicine identity is still resolved by the existing medicine normalizer.
"""

from __future__ import annotations

import re

from backend.services.medicine_normalizer import (
    _estimate_best_score,
)
from backend.services.ocr_layout import (
    group_words_into_spatial_blocks,
)


MEDICINE_EVIDENCE_THRESHOLD = 0.85

# Prescription dosage-form indicators.
_DOSAGE_FORM_RE = re.compile(
    r"\b(?:tab(?:let)?|cap(?:sule)?|caps(?:ule)?|"
    r"inj(?:ection)?|syp(?:rup)?)\b",
    re.IGNORECASE,
)

# Strength values.
_STRENGTH_RE = re.compile(
    r"\b\d+(?:\.\d+)?"
    r"(?:\s*\+\s*\d+(?:\.\d+)?)?"
    r"\s*(?:mg|mcg|g|ml|%)\b",
    re.IGNORECASE,
)

# Numeric dose values.
_DOSE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*"
    r"(?:tablet|tablets|tab|capsule|capsules|cap|"
    r"ml|milliliter|milliliters|drop|drops|puff|puffs|"
    r"unit|units)\b",
    re.IGNORECASE,
)

# Common prescription schedules.
_SCHEDULE_RE = re.compile(
    r"\b\d+(?:\.\d+)?"
    r"(?:\s*[-/:]\s*\d+(?:\.\d+)?){1,2}\b"
)

# Labels which should not themselves become medicine candidates.
_FIELD_LABEL_RE = re.compile(
    r"\b(?:dose|frequency|duration|instructions?|"
    r"doctor|patient|date|age|gender|sex|"
    r"diagnosis|prescription|medicines?|medications?|"
    r"advice|follow[\s-]?up|assessment)\b",
    re.IGNORECASE,
)

# Obvious footer/header terms.
_METADATA_ONLY_RE = re.compile(
    r"^(?:doctor|patient|date|age|gender|sex|address|"
    r"phone|mobile|diagnosis|prescription|medicines?|"
    r"medications?|advice|follow[\s-]?up|assessment)"
    r"\s*:?\s*$",
    re.IGNORECASE,
)


def _clean_spatial_candidate(text: str) -> str:
    """
    Remove obvious prescription metadata and dosage fields from a
    spatial OCR candidate.

    This function does not identify medicines.
    """

    if not text:
        return ""

    candidate = text.strip()

    if not candidate:
        return ""

    candidate = _DOSAGE_FORM_RE.sub(
        " ",
        candidate,
    )

    candidate = _STRENGTH_RE.sub(
        " ",
        candidate,
    )

    candidate = _DOSE_RE.sub(
        " ",
        candidate,
    )

    candidate = _SCHEDULE_RE.sub(
        " ",
        candidate,
    )

    candidate = _FIELD_LABEL_RE.sub(
        " ",
        candidate,
    )

    # Remove leading numbering such as:
    # 1. Medicine
    # 2) Medicine
    candidate = re.sub(
        r"^\s*\d+\s*[\.\)\-:]\s*",
        "",
        candidate,
    )

    # Remove standalone numeric fragments.
    candidate = re.sub(
        r"\b\d+(?:\.\d+)?\b",
        " ",
        candidate,
    )

    candidate = re.sub(
        r"\s+",
        " ",
        candidate,
    ).strip()

    return candidate


def _has_meaningful_candidate_tokens(
    text: str,
) -> bool:
    """
    Require at least one meaningful alphabetic token.

    Very short OCR fragments are intentionally rejected.
    """

    tokens = re.findall(
        r"[A-Za-z]{3,}",
        text,
    )

    return bool(tokens)


def _contains_dosage_form(
    text: str,
) -> bool:
    return bool(
        _DOSAGE_FORM_RE.search(text)
    )


def _contains_strength(
    text: str,
) -> bool:
    return bool(
        _STRENGTH_RE.search(text)
    )


def _contains_schedule(
    text: str,
) -> bool:
    return bool(
        _SCHEDULE_RE.search(text)
    )


def _score_spatial_block(
    block: dict,
    vocabulary: list[dict],
) -> dict:
    """
    Score one spatial OCR block for medicine-related evidence.

    The result is evidence only.

    A medicine match must still be resolved by the existing
    medicine normalizer later in the pipeline.
    """

    raw_text = str(
        block.get("text", "")
    ).strip()

    if not raw_text:
        return {
            "text": "",
            "medicine_score": 0.0,
            "confidence": 0.0,
            "candidate": "",
            "dosage_form_signal": False,
            "strength_signal": False,
            "schedule_signal": False,
        }

    candidate = _clean_spatial_candidate(
        raw_text
    )

    if not candidate:
        return {
            "text": raw_text,
            "medicine_score": 0.0,
            "confidence": float(
                block.get(
                    "confidence",
                    0.0,
                )
            ),
            "candidate": "",
            "dosage_form_signal": _contains_dosage_form(
                raw_text
            ),
            "strength_signal": _contains_strength(
                raw_text
            ),
            "schedule_signal": _contains_schedule(
                raw_text
            ),
        }

    if not _has_meaningful_candidate_tokens(
        candidate
    ):
        return {
            "text": raw_text,
            "medicine_score": 0.0,
            "confidence": float(
                block.get(
                    "confidence",
                    0.0,
                )
            ),
            "candidate": candidate,
            "dosage_form_signal": _contains_dosage_form(
                raw_text
            ),
            "strength_signal": _contains_strength(
                raw_text
            ),
            "schedule_signal": _contains_schedule(
                raw_text
            ),
        }

    # Very long blocks are more likely to contain several unrelated
    # visual regions and should not be aggressively medicine-matched.
    if len(candidate) > 100:
        return {
            "text": raw_text,
            "medicine_score": 0.0,
            "confidence": float(
                block.get(
                    "confidence",
                    0.0,
                )
            ),
            "candidate": candidate,
            "dosage_form_signal": _contains_dosage_form(
                raw_text
            ),
            "strength_signal": _contains_strength(
                raw_text
            ),
            "schedule_signal": _contains_schedule(
                raw_text
            ),
        }

    medicine_score = _estimate_best_score(
        candidate,
        vocabulary,
    )

    return {
        "text": raw_text,
        "medicine_score": round(
            medicine_score,
            3,
        ),
        "confidence": round(
            float(
                block.get(
                    "confidence",
                    0.0,
                )
            ),
            2,
        ),
        "candidate": candidate,
        "dosage_form_signal": _contains_dosage_form(
            raw_text
        ),
        "strength_signal": _contains_strength(
            raw_text
        ),
        "schedule_signal": _contains_schedule(
            raw_text
        ),
    }


def extract_spatial_medicine_evidence(
    ocr_data: list[dict],
    vocabulary: list[dict],
    min_confidence: float = 0.0,
) -> dict:
    """
    Extract conservative medicine evidence from word-level OCR.

    Spatial blocks are generated by the existing ocr_layout module.

    Returns:

        {
            "score": float,
            "matched_blocks": int,
            "strong_matches": int,
            "candidates": [...],
            "blocks": [...]
        }

    This function never declares a medicine clinically verified.
    """

    if not ocr_data or not vocabulary:
        return {
            "score": 0.0,
            "matched_blocks": 0,
            "strong_matches": 0,
            "candidates": [],
            "blocks": [],
        }

    blocks = group_words_into_spatial_blocks(
        ocr_data,
        min_confidence=min_confidence,
    )

    if not blocks:
        return {
            "score": 0.0,
            "matched_blocks": 0,
            "strong_matches": 0,
            "candidates": [],
            "blocks": [],
        }

    scored_blocks = []

    for block in blocks:

        evidence = _score_spatial_block(
            block,
            vocabulary,
        )

        scored_blocks.append(
            {
                **evidence,
                "left": block.get(
                    "left",
                    0,
                ),
                "right": block.get(
                    "right",
                    0,
                ),
                "top": block.get(
                    "top",
                    0,
                ),
                "bottom": block.get(
                    "bottom",
                    0,
                ),
            }
        )

    strong_blocks = [
        block
        for block in scored_blocks
        if block["medicine_score"]
        >= MEDICINE_EVIDENCE_THRESHOLD
    ]

    # Sort strongest medicine-like blocks first.
    strong_blocks.sort(
        key=lambda block: (
            block["medicine_score"],
            block["confidence"],
        ),
        reverse=True,
    )

    # Only a small number of strong blocks should influence
    # OCR candidate selection.
    selected_blocks = strong_blocks[:5]

    if not selected_blocks:
        return {
            "score": 0.0,
            "matched_blocks": 0,
            "strong_matches": 0,
            "candidates": [],
            "blocks": scored_blocks,
        }

    # Primary evidence comes from the strongest spatial block.
    spatial_score = selected_blocks[0][
        "medicine_score"
    ]

    # Additional spatial blocks provide confirmation with
    # diminishing influence.
    for block in selected_blocks[1:]:
        spatial_score += (
            block["medicine_score"]
            * 0.20
        )

    spatial_score = min(
        spatial_score,
        2.0,
    )

    candidates = []

    for block in selected_blocks:

        candidate = block["candidate"]

        if not candidate:
            continue

        candidates.append(
            {
                "text": block["text"],
                "candidate": candidate,
                "medicine_score": block[
                    "medicine_score"
                ],
                "confidence": block[
                    "confidence"
                ],
                "dosage_form_signal": block[
                    "dosage_form_signal"
                ],
                "strength_signal": block[
                    "strength_signal"
                ],
                "schedule_signal": block[
                    "schedule_signal"
                ],
                "left": block["left"],
                "right": block["right"],
                "top": block["top"],
                "bottom": block["bottom"],
            }
        )

    return {
        "score": round(
            spatial_score,
            3,
        ),
        "matched_blocks": len(
            selected_blocks
        ),
        "strong_matches": len(
            strong_blocks
        ),
        "candidates": candidates,
        "blocks": scored_blocks,
    }