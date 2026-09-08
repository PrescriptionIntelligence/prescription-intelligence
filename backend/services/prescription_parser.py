import re

from backend.services.medicine_normalizer import (
    normalize_medicine_candidate,
    load_medicine_vocabulary,
)


# =========================================================
# Helper: Parse frequency
# =========================================================

def _parse_frequency(text: str):
    """
    Parse prescription frequency.

    Examples:
        once daily       -> 1/day
        twice daily      -> 2/day
        three times daily -> 3/day
        2 times daily    -> 2/day
        0 times daily    -> 0/day
        -2 times daily   -> -2/day

    Important:
        The parser preserves zero and negative numeric values.
        Validation is responsible for determining whether those
        values are acceptable.
    """

    if not text:
        return None, None

    lower = text.lower().strip()

    # -----------------------------------------------------
    # Word-based frequency
    # -----------------------------------------------------

    if re.search(
        r"\b(once|one)\s+(daily|a\s+day)\b",
        lower,
    ):
        return 1, "daily"

    if re.search(
        r"\b(twice|two)\s+(daily|a\s+day)\b",
        lower,
    ):
        return 2, "daily"

    if re.search(
        r"\b(three|thrice)\s+(times\s+)?(daily|a\s+day)\b",
        lower,
    ):
        return 3, "daily"

    if "morning" in lower and "evening" in lower:
        return 2, "daily"

    if "morning" in lower:
        return 1, "daily"

    if "evening" in lower:
        return 1, "daily"

    # -----------------------------------------------------
    # Numeric schedule
    #
    # Examples:
    #   1-0-1 -> 2/day
    #   1-1-1 -> 3/day
    #   0-0-0 -> 0/day
    #
    # Negative values are preserved rather than silently
    # converted to positive numbers.
    # -----------------------------------------------------

    schedule_match = re.search(
        r"(?<!\d)"
        r"(-?\d+(?:\.\d+)?)"
        r"[\s\-/:]+"
        r"(-?\d+(?:\.\d+)?)"
        r"[\s\-/:]+"
        r"(-?\d+(?:\.\d+)?)"
        r"(?!\d)",
        lower,
    )

    if schedule_match:
        values = [
            float(schedule_match.group(1)),
            float(schedule_match.group(2)),
            float(schedule_match.group(3)),
        ]

        # A prescription schedule represents the number of
        # administrations when its entries are positive.
        #
        # If every value is zero, preserve 0 so the validator
        # can flag it as invalid rather than treating it as
        # missing.
        frequency = sum(
            1
            for value in values
            if value > 0
        )

        if frequency > 0:
            return frequency, "daily"

        if all(value == 0 for value in values):
            return 0, "daily"

        # Negative schedule values are invalid. Preserve a
        # negative value so validation can report it.
        negative_values = [
            value
            for value in values
            if value < 0
        ]

        if negative_values:
            return negative_values[0], "daily"

    # -----------------------------------------------------
    # Single numeric frequency
    #
    # Examples:
    #   2 times daily -> 2/day
    #   0 times daily -> 0/day
    #   -2 times daily -> -2/day
    # -----------------------------------------------------

    every_match = re.search(
        r"(?<!\d)"
        r"(-?\d+(?:\.\d+)?)\s*"
        r"(?:times|x)"
        r"(?:\s*(?:daily|a\s*day))?"
        r"(?!\d)",
        lower,
    )

    if every_match:
        frequency = float(
            every_match.group(1)
        )

        return frequency, "daily"

    return None, None

# =========================================================
# Helper: Parse dose
# =========================================================

def _parse_dose(text: str):
    """
    Parse dose quantity.

    Examples:
        1 tablet
        2 tablets
        5 ml
        1 capsule
        0 tablet
        -1 tablet
        1-0-1
        0-0-1

    Important:
        Numeric values are preserved exactly, including zero
        and negative values. Validation determines whether
        the extracted value is acceptable.
    """

    if not text:
        return None, None

    lower = text.lower().strip()

    # -----------------------------------------------------
    # Numeric schedule
    #
    # Examples:
    #   1-0-1
    #   0-0-1
    #   1-1-1
    #
    # For a schedule, use the largest positive administration
    # value as the dose quantity.
    # -----------------------------------------------------

    schedule_match = re.search(
        r"(?<!\d)"
        r"(-?\d+(?:\.\d+)?)"
        r"[\s\-/:]+"
        r"(-?\d+(?:\.\d+)?)"
        r"[\s\-/:]+"
        r"(-?\d+(?:\.\d+)?)"
        r"(?!\d)",
        lower,
    )

    if schedule_match:
        schedule_values = [
            float(schedule_match.group(1)),
            float(schedule_match.group(2)),
            float(schedule_match.group(3)),
        ]

        positive_values = [
            value
            for value in schedule_values
            if value > 0
        ]

        if positive_values:
            return max(positive_values), "tablet"

        # Preserve an all-zero schedule so validation can
        # identify it as invalid rather than treating it
        # as missing.
        if all(value == 0 for value in schedule_values):
            return 0.0, "tablet"

        # Preserve a negative value so validation can flag it.
        negative_values = [
            value
            for value in schedule_values
            if value < 0
        ]

        if negative_values:
            return negative_values[0], "tablet"

    # -----------------------------------------------------
    # Explicit dose + unit
    # -----------------------------------------------------

    dose_match = re.search(
        r"(?<!\d)"
        r"(-?\d+(?:\.\d+)?)\s*"
        r"(tablet|tablets|tab|"
        r"capsule|capsules|cap|"
        r"ml|milliliter|milliliters|"
        r"drop|drops|"
        r"puff|puffs|"
        r"unit|units)"
        r"(?!\w)",
        lower,
    )

    if not dose_match:
        return None, None

    value = float(
        dose_match.group(1)
    )

    unit = dose_match.group(2)

    if unit in {"tab", "tablet", "tablets"}:
        unit = "tablet"

    elif unit in {"cap", "capsule", "capsules"}:
        unit = "capsule"

    elif unit in {"ml", "milliliter", "milliliters"}:
        unit = "ml"

    elif unit in {"drop", "drops"}:
        unit = "drop"

    elif unit in {"puff", "puffs"}:
        unit = "puff"

    elif unit in {"unit", "units"}:
        unit = "unit"

    return value, unit

# =========================================================
# Helper: Parse duration
# =========================================================

def _parse_duration(text: str):
    """
    Parse treatment duration.

    Examples:
        for 5 days
        5 days
        for 2 weeks
        1 month
    """

    if not text:
        return None, None

    duration_match = re.search(
        r"\b(?:for\s+)?"
        r"(\d+(?:\.\d+)?)\s*"
        r"(day|days|week|weeks|month|months)\b",
        text.lower(),
    )

    if not duration_match:
        return None, None

    value = float(duration_match.group(1))
    unit = duration_match.group(2).lower()

    if unit == "day":
        unit = "days"

    elif unit == "week":
        unit = "weeks"

    elif unit == "month":
        unit = "months"

    return value, unit


# =========================================================
# Helper: Clean instruction text
# =========================================================

def _clean_instruction_text(text: str) -> str:
    """
    Clean the final instruction field.
    """

    if not text:
        return ""

    cleaned = text.strip()

    cleaned = re.sub(
        r"^\s*instructions?\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^\s*dose\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned.strip()


# =========================================================
# Helper: Remove OCR metadata / disclaimer lines
# =========================================================

def _is_non_medicine_line(line: str) -> bool:
    """
    Identify lines that should not become medicine data.

    This prevents prescription headers, metadata and common
    OCR-test disclaimers from becoming fake medicines.
    """

    if not line:
        return True

    normalized = re.sub(
        r"\s+",
        " ",
        line.strip().lower(),
    )

    # Empty / punctuation-only
    if not re.search(r"[a-zA-Z0-9]", normalized):
        return True

    # Common prescription metadata
    metadata_patterns = [
        r"^doctor\s*:",
        r"^patient\s*:",
        r"^date\s*:",
        r"^age\s*:",
        r"^gender\s*:",
        r"^sex\s*:",
        r"^address\s*:",
        r"^phone\s*:",
        r"^mobile\s*:",
        r"^diagnosis\s*:",
        r"^prescription\s*:?",
        r"^medicines?\s*:?",
        r"^medications?\s*:?",
        r"^rx\s*:?",
        r"^treatment\s*:?",
    ]

    for pattern in metadata_patterns:
        if re.search(pattern, normalized):
            return True

    # Common test / disclaimer lines
    disclaimer_patterns = [
        r"^for\s+ocr\s+testing\s+only$",
        r"^for\s+testing\s+only$",
        r"^not\s+for\s+medical\s+use$",
        r"^test\s+prescription",
        r"^sample\s+prescription",
        r"^demo\s+prescription",
        r"^this\s+is\s+a\s+test",
        r"^this\s+is\s+a\s+sample",
    ]

    for pattern in disclaimer_patterns:
        if re.search(pattern, normalized):
            return True

    return False


# =========================================================
# Helper: Detect numbered medicine entry
# =========================================================

def _is_numbered_medicine_line(line: str) -> bool:
    """
    Detect numbered prescription entries.

    Examples:
        1. Paracetamol 500 mg
        2) Cetirizine 10 mg
        3- Omeprazole 20 mg
    """

    if not line:
        return False

    return bool(
        re.match(
            r"^\s*\d+\s*[\.\)\-:]\s*\S+",
            line,
        )
    )


# =========================================================
# Helper: Split prescription blocks
# =========================================================

def _split_prescription_blocks(raw_text: str) -> list[str]:
    """
    Convert OCR text into logical medicine blocks.

    Important behavior:

    - Ignores text before the first numbered medicine.
    - Ignores common prescription metadata.
    - Stops attaching footer/disclaimer text after the
      final medicine.
    - Preserves unknown lines inside an active medicine block.
    - Supports numbered multi-line prescriptions.
    - Supports simple semicolon-separated entries.
    """

    if not raw_text:
        return []

    normalized_text = (
        raw_text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    lines = [
        line.strip()
        for line in normalized_text.split("\n")
        if line.strip()
    ]

    if not lines:
        return []

    blocks = []
    current_block = []
    started_numbered_mode = False

    for line in lines:

        # -------------------------------------------------
        # Numbered medicine entry
        # -------------------------------------------------

        if _is_numbered_medicine_line(line):

            started_numbered_mode = True

            if current_block:
                blocks.append(
                    "\n".join(current_block)
                )

            current_block = [line]
            continue

        # -------------------------------------------------
        # Before first numbered medicine:
        # ignore headers / metadata.
        # -------------------------------------------------

        if not started_numbered_mode:

            # Legacy unnumbered medicine detection
            # e.g. "Tab Paracetamol 500 mg"
            legacy_match = re.match(
                r"^\s*(?:tab(?:let)?|cap(?:sule)?|"
                r"caps(?:ule)?|inj(?:ection)?|"
                r"syp(?:rup)?)\b",
                line,
                re.IGNORECASE,
            )

            if legacy_match:

                if current_block:
                    blocks.append(
                        "\n".join(current_block)
                    )

                current_block = [line]
                started_numbered_mode = False
                continue

            # Ignore metadata/header text.
            if _is_non_medicine_line(line):
                continue

            # Don't immediately turn arbitrary OCR text
            # into a medicine block.
            continue

        # -------------------------------------------------
        # We are inside numbered medicine mode.
        # -------------------------------------------------

        # Footer / disclaimer after a medicine.
        if _is_non_medicine_line(line):

            normalized = re.sub(
                r"\s+",
                " ",
                line.strip().lower(),
            )

            # These should terminate the current medicine
            # rather than become its instruction text.
            if (
                normalized.startswith("for ocr testing")
                or normalized.startswith("for testing")
                or normalized.startswith("not for medical")
                or normalized.startswith("test prescription")
                or normalized.startswith("sample prescription")
                or normalized.startswith("demo prescription")
            ):
                continue

            # Metadata should not be attached to medicine.
            if re.match(
                r"^(doctor|patient|date|age|gender|sex|"
                r"address|phone|mobile|diagnosis|"
                r"prescription|medicines?|medications?)\s*:?",
                normalized,
            ):
                continue

        # -------------------------------------------------
        # Keep actual medicine fields / instructions.
        # -------------------------------------------------

        if current_block:
            current_block.append(line)

    # -----------------------------------------------------
    # Final block
    # -----------------------------------------------------

    if current_block:
        blocks.append(
            "\n".join(current_block)
        )

    # -----------------------------------------------------
    # Remove empty blocks
    # -----------------------------------------------------

    final_blocks = []

    for block in blocks:

        if not block.strip():
            continue

        # A block must look like a medicine entry.
        first_line = block.splitlines()[0].strip()

        looks_numbered = _is_numbered_medicine_line(
            first_line
        )

        looks_legacy = bool(
            re.match(
                r"^\s*(?:tab(?:let)?|cap(?:sule)?|"
                r"caps(?:ule)?|inj(?:ection)?|"
                r"syp(?:rup)?)\b",
                first_line,
                re.IGNORECASE,
            )
        )

        if looks_numbered or looks_legacy:
            final_blocks.append(block)

    return final_blocks


# =========================================================
# Helper: Legacy single-line entries
# =========================================================

def _split_prescription_entries(raw_text: str) -> list[str]:
    """
    Backward-compatible helper.

    Supports:

        Tab Paracetamol 500 mg 1-0-1
        Tab Pantop 40 mg once daily

    and semicolon-separated entries.
    """

    if not raw_text:
        return []

    entries = []

    for line in raw_text.splitlines():

        line = line.strip()

        if not line:
            continue

        if _is_non_medicine_line(line):
            continue

        parts = re.split(
            r"\s*;\s*",
            line,
        )

        for part in parts:

            part = part.strip()

            if part:
                entries.append(part)

    return entries


# =========================================================
# Helper: Parse prescription block
# =========================================================

def _parse_prescription_block(block: str) -> dict:
    """
    Parse a complete medicine block.

    Example:

        1. Paracetamol 500 mg
        Dose: 1 tablet
        Frequency: Twice daily
        Duration: 5 days
        Instructions: After food
    """

    lines = [
        line.strip()
        for line in block.splitlines()
        if line.strip()
    ]

    if not lines:
        return {}

    medicine_line = lines[0]

    # -----------------------------------------------------
    # Remove numbering
    # -----------------------------------------------------

    medicine_line = re.sub(
        r"^\d+\s*[\.\)\-:]?\s*",
        "",
        medicine_line,
    ).strip()

    # -----------------------------------------------------
    # Detect dosage form
    # -----------------------------------------------------

    dosage_form = None

    dosage_form_match = re.match(
        r"^(tab(?:let)?|cap(?:sule)?|caps(?:ule)?|"
        r"inj(?:ection)?|syp(?:rup)?)\b",
        medicine_line,
        re.IGNORECASE,
    )

    if dosage_form_match:

        dosage_form_raw = (
            dosage_form_match.group(1).lower()
        )

        if dosage_form_raw.startswith("tab"):
            dosage_form = "tablet"

        elif dosage_form_raw.startswith("cap"):
            dosage_form = "capsule"

        elif dosage_form_raw.startswith("inj"):
            dosage_form = "injection"

        elif dosage_form_raw.startswith("syp"):
            dosage_form = "syrup"

        medicine_line = medicine_line[
            dosage_form_match.end():
        ].strip()

    # -----------------------------------------------------
    # Extract medicine name + strength
    # -----------------------------------------------------

    medicine_match = re.match(
        r"^(.+?)\s+"
        r"(\d+(?:\.\d+)?"
        r"(?:\s*\+\s*\d+(?:\.\d+)?)*"
        r")\s*"
        r"(mg|g|mcg|ml|%)\b"
        r"(.*)$",
        medicine_line,
        re.IGNORECASE,
    )

    if medicine_match:

        raw_name = (
            medicine_match.group(1).strip()
        )

        # -------------------------------------------------
        # Reject numeric-only medicine names
        # -------------------------------------------------
        #
        # Examples that must NOT become medicine names:
        #
        #     500 mg
        #     10 mg
        #     2.5 ml
        #
        # These are incomplete/invalid medicine entries.
        # Do not manufacture a medicine identity from them.
        # -------------------------------------------------

        if not re.search(r"[A-Za-z]", raw_name):
            return {}

        strength_value_raw = (
            medicine_match.group(2).strip()
        )

        strength_unit = (
            medicine_match.group(3).lower()
        )

        trailing_text = (
            medicine_match.group(4).strip()
        )

        if "+" in strength_value_raw:

            strength_value = (
                strength_value_raw.replace(
                    " ",
                    "",
                )
            )

            strength_components = [
                {
                    "value": float(
                        part.strip()
                    ),
                    "unit": strength_unit,
                }
                for part in strength_value_raw.split("+")
            ]

        else:

            strength_value = float(
                strength_value_raw
            )

            strength_components = [
                {
                    "value": strength_value,
                    "unit": strength_unit,
                }
            ]

        extraction_confidence = 0.90

    else:

        # -------------------------------------------------
        # Reject strength-only / numeric-only medicine lines
        # -------------------------------------------------

        strength_only_match = re.fullmatch(
            r"\d+(?:\.\d+)?"
            r"(?:\s*\+\s*\d+(?:\.\d+)?)*"
            r"\s*(?:mg|g|mcg|ml|%)",
            medicine_line,
            re.IGNORECASE,
        )

        if strength_only_match:
            return {}

        raw_name = medicine_line.strip()

        trailing_text = ""

        strength_value = None
        strength_unit = None
        strength_components = []

        extraction_confidence = 0.65

    if len(raw_name) < 3:
        return {}

    # -----------------------------------------------------
    # Collect labelled fields
    # -----------------------------------------------------

    dose_text = ""
    frequency_text = ""
    duration_text = ""
    instructions_text = ""

    if trailing_text:
        instructions_text += (
            trailing_text + " "
        )

    for line in lines[1:]:

        # Dose
        dose_match = re.match(
            r"^\s*dose\s*:\s*(.+)$",
            line,
            re.IGNORECASE,
        )

        if dose_match:

            dose_text += (
                " "
                + dose_match.group(1).strip()
            )

            continue

        # Frequency
        frequency_match = re.match(
            r"^\s*frequency\s*:\s*(.+)$",
            line,
            re.IGNORECASE,
        )

        if frequency_match:

            frequency_text += (
                " "
                + frequency_match.group(1).strip()
            )

            continue

        # Duration
        duration_match = re.match(
            r"^\s*duration\s*:\s*(.+)$",
            line,
            re.IGNORECASE,
        )

        if duration_match:

            duration_text += (
                " "
                + duration_match.group(1).strip()
            )

            continue

        # Instructions
        instruction_match = re.match(
            r"^\s*instructions?\s*:\s*(.+)$",
            line,
            re.IGNORECASE,
        )

        if instruction_match:

            instructions_text += (
                " "
                + instruction_match.group(1).strip()
            )

            continue

        # Unknown lines are preserved as possible
        # instruction text.
        instructions_text += (
            " "
            + line
        )

    # -----------------------------------------------------
    # Parse fields
    # -----------------------------------------------------

    dose_value, dose_unit = _parse_dose(
        dose_text
    )

    frequency_value, frequency_unit = (
        _parse_frequency(
            frequency_text
        )
    )

    duration_value, duration_unit = (
        _parse_duration(
            duration_text
        )
    )

    # -----------------------------------------------------
    # Fallback parsing
    # -----------------------------------------------------

    fallback_text = " ".join(
        value
        for value in [
            trailing_text,
            dose_text,
            frequency_text,
            duration_text,
        ]
        if value
    )

    if dose_value is None:
        dose_value, dose_unit = _parse_dose(
            fallback_text
        )

    if frequency_value is None:
        frequency_value, frequency_unit = (
            _parse_frequency(
                fallback_text
            )
        )

    if duration_value is None:
        duration_value, duration_unit = (
            _parse_duration(
                fallback_text
            )
        )

    # -----------------------------------------------------
    # Infer dose from dosage form
    # -----------------------------------------------------

    if (
        dose_value is None
        and frequency_value is not None
    ):

        if dosage_form == "tablet":
            dose_value = 1.0
            dose_unit = "tablet"

        elif dosage_form == "capsule":
            dose_value = 1.0
            dose_unit = "capsule"

        elif dosage_form == "injection":
            dose_value = 1.0
            dose_unit = "injection"

        elif dosage_form == "syrup":
            dose_value = None
            dose_unit = "ml"

    # -----------------------------------------------------
    # Infer dose unit
    # -----------------------------------------------------

    if dose_value is not None and dose_unit is None:

        if dosage_form == "tablet":
            dose_unit = "tablet"

        elif dosage_form == "capsule":
            dose_unit = "capsule"

        elif dosage_form == "syrup":
            dose_unit = "ml"

        elif dosage_form == "injection":
            dose_unit = "injection"

    # -----------------------------------------------------
    # Clean instructions
    # -----------------------------------------------------

    instructions = (
        _clean_instruction_text(
            instructions_text
        )
        if instructions_text.strip()
        else None
    )

    if instructions:

        instructions = re.sub(
            r"\s+",
            " ",
            instructions,
        ).strip()

        # Remove common trailing OCR disclaimers.
        instructions = re.sub(
            r"\s+(?:for\s+ocr\s+testing\s+only|"
            r"for\s+testing\s+only|"
            r"not\s+for\s+medical\s+use)\s*$",
            "",
            instructions,
            flags=re.IGNORECASE,
        ).strip()

        if not instructions:
            instructions = None

    return {
        "raw_name": raw_name,

        "strength_value": strength_value,

        "strength_unit": strength_unit,

        "strength_components": strength_components,

        "dose_value": dose_value,

        "dose_unit": dose_unit,

        "frequency_value": frequency_value,

        "frequency_unit": frequency_unit,

        "duration_value": duration_value,

        "duration_unit": duration_unit,

        "instructions": instructions,

        "dosage_form": dosage_form,

        "extraction_confidence": extraction_confidence,

        "raw_text": block,
    }


# =========================================================
# Main parser
# =========================================================

def extract_medicines(raw_text: str) -> list[dict]:
    """
    Extract structured medicine information from OCR text.

    Supports:

    - Numbered multi-line prescriptions
    - Tablet/capsule/injection/syrup prefixes
    - Medicines with or without recognizable strength
    - Combination strengths such as 3 + 2 mg
    - 1-0-1 / 1-1-1 dosage schedules
    - once/twice/thrice daily
    - tablet/capsule/ml doses
    - treatment duration
    - labelled Dose/Frequency/Duration/Instructions fields
    - medicine normalization
    - OCR metadata/header/footer filtering
    """

    if not raw_text or not raw_text.strip():
        return []

    medicines = []

    # -----------------------------------------------------
    # Load vocabulary once
    # -----------------------------------------------------

    medicine_vocabulary = (
        load_medicine_vocabulary()
    )

    # -----------------------------------------------------
    # Build logical medicine blocks
    # -----------------------------------------------------

    blocks = _split_prescription_blocks(
        raw_text
    )

    # -----------------------------------------------------
    # Process blocks
    # -----------------------------------------------------

    for block in blocks:

        parsed = _parse_prescription_block(
            block
        )

        if not parsed:
            continue

        raw_name = parsed.get(
            "raw_name"
        )

        if not raw_name:
            continue

        strength_value = parsed.get(
            "strength_value"
        )

        strength_unit = parsed.get(
            "strength_unit"
        )

        strength_components = parsed.get(
            "strength_components",
            [],
        )

        dose_value = parsed.get(
            "dose_value"
        )

        dose_unit = parsed.get(
            "dose_unit"
        )

        frequency_value = parsed.get(
            "frequency_value"
        )

        frequency_unit = parsed.get(
            "frequency_unit"
        )

        duration_value = parsed.get(
            "duration_value"
        )

        duration_unit = parsed.get(
            "duration_unit"
        )

        instructions = parsed.get(
            "instructions"
        )

        dosage_form = parsed.get(
            "dosage_form"
        )

        extraction_confidence = parsed.get(
            "extraction_confidence",
            0.65,
        )

        # -------------------------------------------------
        # Normalize medicine
        # -------------------------------------------------

        normalized = (
            normalize_medicine_candidate(
                {
                    "medicine_text": raw_name,
                },
                medicine_vocabulary,
            )
        )

        # -------------------------------------------------
        # Build medicine identity
        # -------------------------------------------------

        if normalized.get("needs_review"):

            name = raw_name
            generic_name = raw_name
            brand_name = None

        else:

            name = (
                normalized.get(
                    "normalized_name"
                )
                or raw_name
            )

            generic_name = (
                normalized.get(
                    "generic_name"
                )
                or name
            )

            brand_name = normalized.get(
                "normalized_name"
            )

        # -------------------------------------------------
        # Normalization confidence
        # -------------------------------------------------

        normalization_confidence = normalized.get(
            "normalization_confidence",
            0.0,
        )

        if (
            normalized.get("needs_review")
            and normalization_confidence < 0.85
        ):

            extraction_confidence = min(
                extraction_confidence,
                0.70,
            )

        # -------------------------------------------------
        # Build final medicine object
        # -------------------------------------------------

        medicine = {

            "name": name,

            "generic_name": generic_name,

            "brand_name": brand_name,

            "strength_value": strength_value,

            "strength_unit": strength_unit,

            "strength_components": (
                strength_components
            ),

            "dose_value": dose_value,

            "dose_unit": dose_unit,

            "daily_dose_value": None,

            "daily_dose_unit": None,

            "daily_dose_components": [],

            "route": (
                "injection"
                if dosage_form == "injection"
                else "oral"
            ),

            "frequency_value": frequency_value,

            "frequency_unit": frequency_unit,

            "duration_value": duration_value,

            "duration_unit": duration_unit,

            "instructions": instructions,

            "extraction_confidence": round(
                extraction_confidence,
                2,
            ),

            "normalization_confidence": (
                normalization_confidence
            ),

            "confidence": round(
                extraction_confidence
                * normalization_confidence,
                2,
            ),

            "needs_review": normalized.get(
                "needs_review",
                True,
            ),

            "raw_text": parsed.get(
                "raw_text"
            ),

            "matched_term": normalized.get(
                "matched_term"
            ),

            "evidence": normalized.get(
                "evidence",
                {},
            ),
        }

        medicines.append(
            medicine
        )

    return medicines