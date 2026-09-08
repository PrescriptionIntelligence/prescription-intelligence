"""
Instruction Text Extractor

Separates medicine/strength information from medication
instructions.

This layer prepares text for the instruction interpreter.

It does NOT:
    - identify medicines
    - diagnose
    - prescribe
    - invent missing information
"""

from __future__ import annotations

import re


# ---------------------------------------------------------
# Instruction vocabulary
# ---------------------------------------------------------

INSTRUCTION_TERMS = {
    # Frequency
    "od",
    "bd",
    "bid",
    "tds",
    "tid",
    "qid",
    "once",
    "twice",
    "thrice",
    "daily",
    "weekly",

    # Timing
    "morning",
    "afternoon",
    "evening",
    "night",
    "bedtime",
    "noon",

    # Food
    "before",
    "after",
    "food",
    "meal",
    "meals",
    "breakfast",
    "lunch",
    "dinner",
    "empty",
    "stomach",

    # Administration
    "take",
    "takes",
    "give",
    "use",
    "apply",
    "oral",
    "mouth",
    "topical",
    "external",
    "inject",
    "injection",

    # Duration
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",

    # Dosage forms
    "tablet",
    "tablets",
    "tab",
    "capsule",
    "capsules",
    "cap",
    "syrup",
    "syr",
    "injection",
    "inj",
}


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _normalize_text(
    text: str | None,
) -> str:
    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(text).strip(),
    )


def _is_schedule_pattern(
    token: str,
) -> bool:
    return bool(
        re.fullmatch(
            r"\d+(?:[-/]\d+){1,3}",
            token,
        )
    )


def _is_numeric_token(
    token: str,
) -> bool:
    return bool(
        re.fullmatch(
            r"\d+(?:\.\d+)?",
            token,
        )
    )


def _is_strength_unit(
    token: str,
) -> bool:
    return token.lower() in {
        "mg",
        "mcg",
        "g",
        "ml",
        "%",
    }


def _is_instruction_word(
    token: str,
) -> bool:
    return token.lower() in INSTRUCTION_TERMS


# ---------------------------------------------------------
# Main extraction
# ---------------------------------------------------------

def extract_instruction_text(
    text: str | None,
) -> dict:
    """
    Separate medicine/strength metadata from instruction text.

    Examples:

        Ativan 2 mg 1-0-1 after food
        ->
        medicine/strength: Ativan 2 mg
        instructions:      1-0-1 after food

        Paracetamol 500 mg twice daily for 5 days
        ->
        medicine/strength: Paracetamol 500 mg
        instructions:      twice daily for 5 days

        Sizodon Plus 3 + 2 mg 1 tablet at night
        ->
        medicine/strength: Sizodon Plus 3 + 2 mg
        instructions:      1 tablet at night
    """

    raw_text = text or ""
    clean_text = _normalize_text(raw_text)

    if not clean_text:
        return {
            "raw_text": raw_text,
            "instruction_text": "",
            "non_instruction_text": "",
            "instruction_tokens": [],
            "confidence": 0.0,
            "needs_review": True,
        }

    # -----------------------------------------------------
    # Preserve whitespace-separated words.
    # -----------------------------------------------------

    tokens = clean_text.split()

    instruction_tokens: list[str] = []
    non_instruction_tokens: list[str] = []

    instruction_started = False

    i = 0

    while i < len(tokens):

        token = tokens[i]

        # Remove punctuation only around the token.
        normalized = token.strip(
            ".,;:()[]{}"
        )

        lower = normalized.lower()

        # -------------------------------------------------
        # Strength:
        #
        # 500 mg
        # 40 mg
        # 2 mg
        #
        # If a number is followed by a strength unit,
        # BOTH belong to medicine metadata.
        # -------------------------------------------------

        if (
            _is_numeric_token(normalized)
            and i + 1 < len(tokens)
            and _is_strength_unit(
                tokens[i + 1].strip(
                    ".,;:()[]{}"
                )
            )
        ):
            non_instruction_tokens.append(
                normalized
            )

            non_instruction_tokens.append(
                tokens[i + 1].strip(
                    ".,;:()[]{}"
                )
            )

            i += 2
            continue

        # -------------------------------------------------
        # Combined strength:
        #
        # 500mg
        # 40ml
        # -------------------------------------------------

        if re.fullmatch(
            r"\d+(?:\.\d+)?"
            r"(?:mg|mcg|g|ml|%)",
            lower,
        ):
            non_instruction_tokens.append(
                normalized
            )

            i += 1
            continue

        # -------------------------------------------------
        # Once we encounter a clear instruction marker,
        # subsequent dosage quantities belong to the
        # instruction.
        #
        # Example:
        #
        # twice daily for 5 days
        #                 ^
        #                 5 belongs to instruction
        # -------------------------------------------------

        if _is_instruction_word(normalized):
            instruction_started = True

            instruction_tokens.append(
                normalized
            )

            i += 1
            continue

        # -------------------------------------------------
        # Schedule:
        #
        # 1-0-1
        # 1-1-1
        # -------------------------------------------------

        if _is_schedule_pattern(normalized):
            instruction_started = True

            instruction_tokens.append(
                normalized
            )

            i += 1
            continue

        # -------------------------------------------------
        # Numeric quantity
        # -------------------------------------------------

        if _is_numeric_token(normalized):

            # If instructions have already started,
            # this number is likely dosage quantity or
            # duration quantity.
            if instruction_started:

                instruction_tokens.append(
                    normalized
                )

            else:

                # Before instruction context exists,
                # a standalone number is ambiguous.
                #
                # Preserve it as non-instruction metadata.
                non_instruction_tokens.append(
                    normalized
                )

            i += 1
            continue
        
        # -------------------------------------------------
        # Numeric quantity + dosage form
        #
        # Example:
        #
        # 1 tablet at night
        # 2 capsules daily
        #
        # This is an instruction, not medicine metadata.
        # -------------------------------------------------

        if lower in {
            "tablet",
            "tablets",
            "tab",
            "capsule",
            "capsules",
            "cap",
            "syrup",
            "syr",
            "injection",
            "inj",
        }:

            # If the previous token was a standalone number,
            # move that number from metadata into instructions.
            if (
                i > 0
                and _is_numeric_token(
                    tokens[i - 1].strip(
                        ".,;:()[]{}"
                    )
                )
                and (
                    not instruction_tokens
                    or instruction_tokens[-1]
                    != tokens[i - 1].strip(
                        ".,;:()[]{}"
                    )
                )
            ):
                quantity = tokens[i - 1].strip(
                    ".,;:()[]{}"
                )

                # Remove the quantity from the
                # non-instruction metadata if present.
                if quantity in non_instruction_tokens:
                    non_instruction_tokens.remove(
                        quantity
                    )

                instruction_tokens.append(
                    quantity
                )

            instruction_started = True

            instruction_tokens.append(
                normalized
            )

            i += 1
            continue

        # -------------------------------------------------
        # "for" is useful instruction context.
        # -------------------------------------------------

        if lower == "for":

            instruction_started = True

            instruction_tokens.append(
                normalized
            )

            i += 1
            continue

        # -------------------------------------------------
        # Any remaining word
        # -------------------------------------------------

        if instruction_started:

            instruction_tokens.append(
                normalized
            )

        else:

            non_instruction_tokens.append(
                normalized
            )

        i += 1

    instruction_text = " ".join(
        instruction_tokens
    )

    non_instruction_text = " ".join(
        non_instruction_tokens
    )

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    if not instruction_tokens:

        confidence = 0.0

    else:

        ratio = (
            len(instruction_tokens)
            / max(len(tokens), 1)
        )

        if ratio >= 0.50:
            confidence = 0.90

        elif ratio >= 0.25:
            confidence = 0.75

        else:
            confidence = 0.60

    return {
        "raw_text": raw_text,
        "instruction_text": instruction_text,
        "non_instruction_text": non_instruction_text,
        "instruction_tokens": instruction_tokens,
        "confidence": confidence,
        "needs_review": confidence < 0.75,
    }


# ---------------------------------------------------------
# Item helper
# ---------------------------------------------------------

def extract_instruction_from_item(
    item: dict,
) -> dict:

    return extract_instruction_text(
        item.get(
            "text",
            "",
        )
    )


# ---------------------------------------------------------
# Batch helper
# ---------------------------------------------------------

def extract_instructions_from_items(
    items: list[dict],
) -> list[dict]:

    return [
        extract_instruction_from_item(item)
        for item in items
    ]