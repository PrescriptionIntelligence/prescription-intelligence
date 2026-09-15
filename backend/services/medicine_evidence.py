"""
Medicine Evidence Fusion

Combines multiple independent signals to improve medicine
hypothesis ranking.

This is an evidence layer, NOT a medical diagnosis system.

Signals currently supported:

    - medicine similarity
    - OCR confidence
    - dosage-form compatibility
    - strength compatibility
    - prescription marker evidence

The output is still a hypothesis and must not be treated
as a confirmed medicine unless the evidence is sufficiently
strong.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------
# Evidence weights
# ---------------------------------------------------------

SIMILARITY_WEIGHT = 0.55
OCR_WEIGHT = 0.15
DOSAGE_FORM_WEIGHT = 0.15
STRENGTH_WEIGHT = 0.10
MARKER_WEIGHT = 0.05


# ---------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------

def _safe_float(value) -> float:
    """Safely convert a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_text(value) -> str:
    """Normalize text for comparison."""
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).strip().lower(),
    )


def _normalize_strength_unit(value) -> str:
    """Normalize common strength units."""
    unit = _normalize_text(value)

    aliases = {
        "milligram": "mg",
        "milligrams": "mg",
        "mg": "mg",
        "microgram": "mcg",
        "micrograms": "mcg",
        "mcg": "mcg",
        "gram": "g",
        "grams": "g",
        "g": "g",
        "milliliter": "ml",
        "milliliters": "ml",
        "ml": "ml",
        "%": "%",
    }

    return aliases.get(unit, unit)


# ---------------------------------------------------------
# Dosage form compatibility
# ---------------------------------------------------------

def _normalize_dosage_form(value: str | None) -> str:
    """
    Normalize dosage-form markers and dosage-form names.

    Handles noisy OCR such as:
        Tab
        © Tab
        (3) tab
        Tablet
        Cap
        Syr
        Inj
    """
    value = _normalize_text(value)

    if not value:
        return ""

    mapping = {
        "tab": "tablet",
        "tablet": "tablet",
        "cap": "capsule",
        "capsule": "capsule",
        "syr": "syrup",
        "syrup": "syrup",
        "inj": "injection",
        "injection": "injection",
    }

    if value in mapping:
        return mapping[value]

    marker_patterns = [
        (r"\btab(?:let)?\b", "tablet"),
        (r"\bcap(?:sule)?\b", "capsule"),
        (r"\bsyr(?:up)?\b", "syrup"),
        (r"\binj(?:ection)?\b", "injection"),
    ]

    for pattern, normalized in marker_patterns:
        if re.search(
            pattern,
            value,
            re.IGNORECASE,
        ):
            return normalized

    return value


def calculate_dosage_form_evidence(
    candidate: dict,
    hypothesis: dict,
) -> float:
    """
    Compare prescription marker with the predicted dosage form.

    Returns:
        1.0 -> strong compatibility
        0.5 -> insufficient evidence
        0.0 -> conflict
    """
    marker = _normalize_dosage_form(
        candidate.get("marker")
    )

    dosage_form = _normalize_dosage_form(
        hypothesis.get("dosage_form")
    )

    if not marker or not dosage_form:
        return 0.5

    if marker == dosage_form:
        return 1.0

    return 0.0


# ---------------------------------------------------------
# Strength compatibility
# ---------------------------------------------------------

def _extract_numeric_strength(
    strength: str | None,
) -> tuple[float | None, str | None]:
    """
    Extract numeric strength and unit from OCR text.

    Examples:
        500 mg
        40mg
        2 mg
        0.5 mg
    """
    if not strength:
        return None, None

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|%)",
        str(strength),
        re.IGNORECASE,
    )

    if not match:
        return None, None

    return (
        float(match.group(1)),
        _normalize_strength_unit(match.group(2)),
    )


def _extract_structured_candidate_strength(
    candidate: dict,
) -> tuple[float | None, str | None]:
    """
    Extract structured prescription strength.

    Preferred fields:
        strength_value
        strength_unit

    Backward-compatible fallback:
        strength
    """
    value = candidate.get("strength_value")
    unit = candidate.get("strength_unit")

    numeric_value = None

    try:
        if value is not None:
            numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = None

    normalized_unit = _normalize_strength_unit(unit)

    if numeric_value is not None and normalized_unit:
        return numeric_value, normalized_unit

    strength = candidate.get("strength")

    if isinstance(strength, dict):
        value = strength.get("value")
        unit = strength.get("unit")

        try:
            numeric_value = (
                float(value)
                if value is not None
                else None
            )
        except (TypeError, ValueError):
            numeric_value = None

        normalized_unit = _normalize_strength_unit(unit)

        if numeric_value is not None and normalized_unit:
            return numeric_value, normalized_unit

    if isinstance(strength, str):
        return _extract_numeric_strength(strength)

    return None, None


def calculate_strength_evidence(
    candidate: dict,
    hypothesis: dict,
) -> float:
    """
    Compare prescription-extracted strength with vocabulary strength.

    Returns:
        1.0 -> exact compatibility
        0.5 -> strength unavailable
        0.0 -> conflict

    Structured fields are preferred over legacy free-text
    strength fields.
    """
    candidate_value, candidate_unit = (
        _extract_structured_candidate_strength(
            candidate
        )
    )

    hypothesis_value = hypothesis.get(
        "strength_value"
    )

    hypothesis_unit = hypothesis.get(
        "strength_unit"
    )

    if (
        candidate_value is None
        or not hypothesis_value
        or not hypothesis_unit
    ):
        return 0.5

    try:
        expected_value = float(
            hypothesis_value
        )
    except (TypeError, ValueError):
        return 0.5

    expected_unit = _normalize_strength_unit(
        hypothesis_unit
    )

    if (
        candidate_unit == expected_unit
        and abs(candidate_value - expected_value) <= 1e-9
    ):
        return 1.0

    return 0.0


# ---------------------------------------------------------
# Marker evidence
# ---------------------------------------------------------

def calculate_marker_evidence(
    candidate: dict,
    hypothesis: dict,
) -> float:
    """
    Determine whether a dosage-form marker exists.

    The marker itself does not prove medicine identity,
    so this is intentionally a small signal.
    """
    marker = candidate.get(
        "marker"
    )

    dosage_form = hypothesis.get(
        "dosage_form"
    )

    if not marker or not dosage_form:
        return 0.5

    marker_normalized = _normalize_dosage_form(
        marker
    )

    dosage_form_normalized = _normalize_dosage_form(
        dosage_form
    )

    if marker_normalized == dosage_form_normalized:
        return 1.0

    return 0.0


# ---------------------------------------------------------
# OCR evidence
# ---------------------------------------------------------

def calculate_ocr_evidence(
    candidate: dict,
) -> float:
    """
    Convert OCR confidence into an evidence score.

    Candidate OCR confidence is expected to be
    in the range 0.0 - 1.0.
    """
    confidence = _safe_float(
        candidate.get(
            "ocr_confidence",
            0.0,
        )
    )

    return min(
        max(confidence, 0.0),
        1.0,
    )


# ---------------------------------------------------------
# Combined evidence
# ---------------------------------------------------------

def calculate_hypothesis_evidence(
    candidate: dict,
    hypothesis: dict,
) -> dict:
    """
    Calculate evidence for one medicine hypothesis.
    """
    similarity = min(
        max(
            _safe_float(
                hypothesis.get(
                    "score",
                    0.0,
                )
            ),
            0.0,
        ),
        1.0,
    )

    ocr = calculate_ocr_evidence(
        candidate
    )

    dosage_form = calculate_dosage_form_evidence(
        candidate,
        hypothesis,
    )

    strength = calculate_strength_evidence(
        candidate,
        hypothesis,
    )

    marker = calculate_marker_evidence(
        candidate,
        hypothesis,
    )

    combined_score = (
        similarity * SIMILARITY_WEIGHT
        + ocr * OCR_WEIGHT
        + dosage_form * DOSAGE_FORM_WEIGHT
        + strength * STRENGTH_WEIGHT
        + marker * MARKER_WEIGHT
    )

    return {
        "similarity": round(
            similarity,
            3,
        ),
        "ocr": round(
            ocr,
            3,
        ),
        "dosage_form": round(
            dosage_form,
            3,
        ),
        "strength": round(
            strength,
            3,
        ),
        "marker": round(
            marker,
            3,
        ),
        "combined_score": round(
            min(
                max(
                    combined_score,
                    0.0,
                ),
                1.0,
            ),
            3,
        ),
    }


# ---------------------------------------------------------
# Rank hypotheses using evidence
# ---------------------------------------------------------

def rank_hypotheses_by_evidence(
    candidate: dict,
    hypotheses: list[dict],
) -> list[dict]:
    """
    Re-rank medicine hypotheses using multiple evidence
    signals instead of medicine similarity alone.
    """
    ranked = []

    for hypothesis in hypotheses:
        evidence = calculate_hypothesis_evidence(
            candidate,
            hypothesis,
        )

        result = {
            **hypothesis,
            "evidence": evidence,
            "evidence_score": evidence[
                "combined_score"
            ],
        }

        ranked.append(
            result
        )

    ranked.sort(
        key=lambda item: item[
            "evidence_score"
        ],
        reverse=True,
    )

    return ranked