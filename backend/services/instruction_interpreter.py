"""
Instruction Interpreter

Extracts structured medication instructions from noisy
prescription text.

This is an interpretation layer, NOT a medical diagnosis
or prescribing system.

The interpreter focuses on identifying:

    - dosage quantity
    - frequency
    - timing
    - food relationship
    - duration
    - route
    - native-language instruction patterns

Uncertain information is marked for review instead of
being invented.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------
# Frequency patterns
# ---------------------------------------------------------

FREQUENCY_PATTERNS = {
    "once_daily": [
        r"\bod\b",
        r"\bonce\s*(daily|a\s*day)?\b",
        r"\b1\s*(time|times)\s*(daily|a\s*day)?\b",
        r"\b1[-\s]?0[-\s]?0\b",
    ],

    "twice_daily": [
        r"\bbd\b",
        r"\bbid\b",
        r"\btwice\s*(daily|a\s*day)?\b",
        r"\b2\s*(times|time)\s*(daily|a\s*day)?\b",
        r"\b1[-\s]?0[-\s]?1\b",
    ],

    "three_times_daily": [
        r"\btds\b",
        r"\btid\b",
        r"\bthrice\s*(daily|a\s*day)?\b",
        r"\b3\s*(times|time)\s*(daily|a\s*day)?\b",
        r"\b1[-\s]?1[-\s]?1\b",
    ],

    "four_times_daily": [
        r"\bqid\b",
        r"\b4\s*(times|time)\s*(daily|a\s*day)?\b",
        r"\b1[-\s]?1[-\s]?1[-\s]?1\b",
    ],
}


# ---------------------------------------------------------
# Timing patterns
# ---------------------------------------------------------

TIMING_PATTERNS = {
    "morning": [
        r"\bmorning\b",
        r"\bam\b",
        r"\bma?orning\b",
    ],

    "afternoon": [
        r"\bafternoon\b",
        r"\bnoon\b",
    ],

    "evening": [
        r"\bevening\b",
        r"\bpm\b",
    ],

    "night": [
        r"\bnight\b",
        r"\bnighttime\b",
    ],

    "bedtime": [
        r"\bbedtime\b",
        r"\bat\s*bedtime\b",
    ],
}


# ---------------------------------------------------------
# Food relationship patterns
# ---------------------------------------------------------

FOOD_PATTERNS = {
    "before_food": [
        r"\bbefore\s*(food|meal|meals)\b",
        r"\bbefore\s*breakfast\b",
        r"\bbefore\s*lunch\b",
        r"\bbefore\s*dinner\b",
        r"\bac\b",
        r"\bempty\s*stomach\b",
    ],

    "after_food": [
        r"\bafter\s*(food|meal|meals)\b",
        r"\bafter\s*breakfast\b",
        r"\bafter\s*lunch\b",
        r"\bafter\s*dinner\b",
        r"\bpc\b",
    ],

    "with_food": [
        r"\bwith\s*(food|meal|meals)\b",
    ],
}


# ---------------------------------------------------------
# Route patterns
# ---------------------------------------------------------

ROUTE_PATTERNS = {
    "oral": [
        r"\bpo\b",
        r"\boral\b",
        r"\bby\s*mouth\b",
    ],

    "topical": [
        r"\btopical\b",
        r"\bapply\b",
        r"\bexternal\b",
    ],

    "injection": [
        r"\bim\b",
        r"\biv\b",
        r"\binjection\b",
    ],

    "sublingual": [
        r"\bsublingual\b",
        r"\bunder\s*the\s*tongue\b",
    ],
}


# ---------------------------------------------------------
# Duration extraction
# ---------------------------------------------------------

def _extract_duration(
    text: str,
) -> dict | None:
    """
    Extract medication duration.

    Examples:

        5 days
        7 day
        2 weeks
        1 month
    """

    patterns = [
        (
            r"\b(\d+)\s*(day|days)\b",
            "days",
        ),
        (
            r"\b(\d+)\s*(week|weeks)\b",
            "weeks",
        ),
        (
            r"\b(\d+)\s*(month|months)\b",
            "months",
        ),
    ]

    for pattern, unit in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:

            return {
                "value": int(
                    match.group(1)
                ),
                "unit": unit,
                "text": match.group(0),
            }

    return None


# ---------------------------------------------------------
# Quantity extraction
# ---------------------------------------------------------

def _extract_quantity(
    text: str,
) -> int | float | None:
    """
    Extract simple dosage quantities.

    Examples:

        1 tablet
        2 tablets
        half tablet
    """

    match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*"
        r"(tablet|tablets|tab|tabs|capsule|capsules|cap|caps)\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:

        value = float(
            match.group(1)
        )

        if value.is_integer():
            return int(value)

        return value

    if re.search(
        r"\bhalf\s*(tablet|tab|capsule|cap)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return 0.5

    return None


# ---------------------------------------------------------
# Pattern finder
# ---------------------------------------------------------

def _find_pattern(
    text: str,
    patterns: dict[str, list[str]],
) -> str | None:
    """
    Return the first matching semantic category.
    """

    for category, expressions in patterns.items():

        for expression in expressions:

            if re.search(
                expression,
                text,
                flags=re.IGNORECASE,
            ):
                return category

    return None


# ---------------------------------------------------------
# Instruction interpretation
# ---------------------------------------------------------

def interpret_instruction(
    text: str | None,
) -> dict:
    """
    Interpret one prescription instruction string.

    The output is structured but intentionally conservative.
    Missing or uncertain information remains None.
    """

    raw_text = text or ""

    clean_text = re.sub(
        r"\s+",
        " ",
        raw_text.strip().lower(),
    )

    if not clean_text:

        return {
            "raw_text": raw_text,
            "clean_text": "",
            "quantity": None,
            "frequency": None,
            "timing": None,
            "food_relation": None,
            "duration": None,
            "route": None,
            "confidence": 0.0,
            "needs_review": True,
        }

    frequency = _find_pattern(
        clean_text,
        FREQUENCY_PATTERNS,
    )

    timing = _find_pattern(
        clean_text,
        TIMING_PATTERNS,
    )

    food_relation = _find_pattern(
        clean_text,
        FOOD_PATTERNS,
    )

    route = _find_pattern(
        clean_text,
        ROUTE_PATTERNS,
    )

    duration = _extract_duration(
        clean_text
    )

    quantity = _extract_quantity(
        clean_text
    )

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    signals_found = sum(
        value is not None
        for value in [
            quantity,
            frequency,
            timing,
            food_relation,
            duration,
            route,
        ]
    )

    if signals_found == 0:

        confidence = 0.0

    elif signals_found == 1:

        confidence = 0.45

    elif signals_found == 2:

        confidence = 0.65

    elif signals_found == 3:

        confidence = 0.80

    else:

        confidence = 0.90

    return {
        "raw_text": raw_text,
        "clean_text": clean_text,
        "quantity": quantity,
        "frequency": frequency,
        "timing": timing,
        "food_relation": food_relation,
        "duration": duration,
        "route": route,
        "confidence": confidence,
        "needs_review": confidence < 0.80,
    }


# ---------------------------------------------------------
# Interpret prescription item
# ---------------------------------------------------------

def interpret_prescription_item_instruction(
    item: dict,
) -> dict:
    """
    Interpret instruction text associated with a
    reconstructed prescription item.
    """

    text = item.get(
        "text",
        "",
    )

    return interpret_instruction(
        text
    )


# ---------------------------------------------------------
# Interpret all prescription instructions
# ---------------------------------------------------------

def interpret_prescription_instructions(
    items: list[dict],
) -> list[dict]:
    """
    Interpret instructions for all reconstructed
    prescription items.
    """

    return [
        interpret_prescription_item_instruction(
            item
        )
        for item in items
    ]