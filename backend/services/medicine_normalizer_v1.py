import csv
import re
from difflib import SequenceMatcher
from pathlib import Path


# Minimum fuzzy similarity required before accepting a match.
FUZZY_MATCH_THRESHOLD = 0.85

# If the best and second-best MEDICINES are too close,
# we should not confidently identify the medicine.
AMBIGUITY_MARGIN = 0.10


# ---------------------------------------------------------
# Medicine vocabulary
# ---------------------------------------------------------

def load_medicine_vocabulary():
    """
    Load medicine vocabulary from:

        data/medicines/medicine_vocabulary.csv

    CSV format:

        brand_name,generic_name,strength_value,
        strength_unit,dosage_form,aliases

    Multiple aliases are separated by "|".
    """

    project_root = Path(__file__).resolve().parents[2]

    csv_path = (
        project_root
        / "data"
        / "medicines"
        / "medicine_vocabulary.csv"
    )

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Medicine vocabulary not found: {csv_path}"
        )

    medicines = []

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        required_columns = {
            "brand_name",
            "generic_name",
            "strength_value",
            "strength_unit",
            "dosage_form",
            "aliases",
        }

        if not reader.fieldnames:
            raise ValueError(
                "Medicine CSV has no header row."
            )

        missing_columns = (
            required_columns
            - set(reader.fieldnames)
        )

        if missing_columns:
            raise ValueError(
                "Medicine CSV is missing columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row in reader:

            aliases = row.get(
                "aliases",
                "",
            )

            aliases = [
                alias.strip()
                for alias in aliases.split("|")
                if alias.strip()
            ]

            medicine = {
                "brand_name": row.get(
                    "brand_name",
                    "",
                ).strip(),

                "generic_name": row.get(
                    "generic_name",
                    "",
                ).strip(),

                "strength_value": row.get(
                    "strength_value",
                    "",
                ).strip(),

                "strength_unit": row.get(
                    "strength_unit",
                    "",
                ).strip(),

                "dosage_form": row.get(
                    "dosage_form",
                    "",
                ).strip(),

                "aliases": aliases,
            }

            # Ignore completely empty rows.
            if not any(medicine.values()):
                continue

            medicines.append(medicine)

    return medicines


# ---------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------

def _clean_text(text: str) -> str:
    """
    Normalize OCR text before comparison.
    """

    if not text:
        return ""

    text = text.lower()

    # Remove punctuation/symbols.
    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    # Normalize whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ---------------------------------------------------------
# Similarity
# ---------------------------------------------------------

def _similarity(
    a: str,
    b: str,
) -> float:
    """
    Calculate fuzzy similarity between two strings.
    """

    if not a or not b:
        return 0.0

    return SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


# ---------------------------------------------------------
# Searchable medicine terms
# ---------------------------------------------------------

def _get_match_terms(
    medicine: dict,
) -> list[str]:
    """
    Get all searchable names for a medicine.

    Includes:

    - brand name
    - generic name
    - aliases
    """

    terms = []

    for key in [
        "brand_name",
        "generic_name",
    ]:

        value = medicine.get(key)

        if value:
            terms.append(value)

    aliases = medicine.get(
        "aliases",
        [],
    )

    if aliases:
        terms.extend(aliases)

    return [
        term
        for term in terms
        if term
    ]


# ---------------------------------------------------------
# Prepare OCR candidate
# ---------------------------------------------------------

def _prepare_candidate(
    clean_text: str,
) -> str:
    """
    Remove common prescription artifacts from OCR text.
    """

    candidate = re.sub(
        r"\b(tab|tablet|cap|capsule|syr|syrup|inj|injection)\b",
        " ",
        clean_text,
        flags=re.IGNORECASE,
    )

    # Remove numbering artifacts.
    candidate = re.sub(
        r"\b\d+\b",
        " ",
        candidate,
    )

    candidate = re.sub(
        r"\s+",
        " ",
        candidate,
    ).strip()

    return candidate


# ---------------------------------------------------------
# Score one medicine
# ---------------------------------------------------------

def _score_medicine(
    candidate: str,
    medicine: dict,
) -> dict | None:
    """
    Calculate the strongest evidence for one medicine.

    Multiple aliases belonging to the same medicine are
    combined into ONE medicine-level score.

    This prevents a medicine from becoming falsely
    ambiguous with its own aliases.
    """

    terms = _get_match_terms(medicine)

    if not terms:
        return None

    candidate_tokens = [
        token
        for token in candidate.split()
        if len(token) >= 3
    ]

    best_result = None

    for term in terms:

        clean_term = _clean_text(term)

        if not clean_term:
            continue

        # -------------------------------------------------
        # Full candidate similarity
        # -------------------------------------------------

        full_score = _similarity(
            candidate,
            clean_term,
        )

        # -------------------------------------------------
        # Token-level similarity
        # -------------------------------------------------

        token_scores = []

        for token in candidate_tokens:

            token_score = _similarity(
                token,
                clean_term,
            )

            token_scores.append(
                token_score
            )

        best_token_score = (
            max(token_scores)
            if token_scores
            else 0.0
        )

        # -------------------------------------------------
        # Exact token match
        # -------------------------------------------------

        exact_token_match = any(
            token == clean_term
            for token in candidate_tokens
        )

        # -------------------------------------------------
        # Prefix evidence
        # -------------------------------------------------

        prefix_score = 0.0

        for token in candidate_tokens:

            if (
                len(token) >= 4
                and (
                    clean_term.startswith(token)
                    or token.startswith(clean_term)
                )
            ):
                prefix_score = max(
                    prefix_score,
                    0.90,
                )

        # -------------------------------------------------
        # Combine evidence
        # -------------------------------------------------

        if exact_token_match:

            score = 1.0

        elif prefix_score >= 0.90:

            score = max(
                best_token_score,
                prefix_score,
            )

        else:

            score = max(
                best_token_score,
                full_score * 0.75,
            )

        result = {
            "medicine": medicine,
            "matched_term": term,
            "score": score,
            "full_score": full_score,
            "token_score": best_token_score,
        }

        # Keep only the strongest term belonging to
        # this medicine.
        if (
            best_result is None
            or result["score"] > best_result["score"]
        ):
            best_result = result

    return best_result


# ---------------------------------------------------------
# Find best medicine
# ---------------------------------------------------------

def _find_best_fuzzy_match(
    clean_text: str,
    medicines: list[dict],
):
    """
    Find the best medicine vocabulary match.

    IMPORTANT:
    Ambiguity is checked between DIFFERENT medicines,
    not between aliases of the same medicine.
    """

    if not clean_text:
        return None

    candidate = _prepare_candidate(
        clean_text
    )

    if not candidate:
        return None

    results = []

    # Score each medicine ONCE.
    for medicine in medicines:

        result = _score_medicine(
            candidate,
            medicine,
        )

        if result is not None:
            results.append(result)

    if not results:
        return None

    # Highest medicine-level score first.
    results.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    best = results[0]

    second_score = (
        results[1]["score"]
        if len(results) > 1
        else 0.0
    )

    # ---------------------------------------------------------
    # Safety check 1:
    # Match must be strong enough.
    # ---------------------------------------------------------

    if best["score"] < FUZZY_MATCH_THRESHOLD:
        return None

    # ---------------------------------------------------------
    # Safety check 2:
    # Best and second-best DIFFERENT medicines
    # must be sufficiently separated.
    # ---------------------------------------------------------

    if (
        len(results) > 1
        and (
            best["score"] - second_score
            < AMBIGUITY_MARGIN
        )
    ):
        return None

    return best


# ---------------------------------------------------------
# Estimate best confidence for review
# ---------------------------------------------------------

def _estimate_best_score(
    clean_text: str,
    medicines: list[dict],
) -> float:
    """
    Estimate the strongest medicine-level similarity.

    Used only when no reliable match was accepted.
    """

    candidate = _prepare_candidate(
        clean_text
    )

    if not candidate:
        return 0.0

    best_score = 0.0

    for medicine in medicines:

        result = _score_medicine(
            candidate,
            medicine,
        )

        if result is not None:
            best_score = max(
                best_score,
                result["score"],
            )

    return best_score


# ---------------------------------------------------------
# Normalize one candidate
# ---------------------------------------------------------

def normalize_medicine_candidate(
    candidate: dict,
    medicines: list[dict],
) -> dict:
    """
    Normalize one medicine candidate.

    Does not invent a medicine when confidence
    is insufficient.
    """

    raw_text = candidate.get(
        "medicine_text",
        candidate.get(
            "text",
            "",
        ),
    )

    clean_text = _clean_text(
        raw_text
    )

    match = _find_best_fuzzy_match(
        clean_text,
        medicines,
    )

    # ---------------------------------------------------------
    # No reliable match
    # ---------------------------------------------------------

    if match is None:

        best_score = _estimate_best_score(
            clean_text,
            medicines,
        )

        return {
            "raw_text": raw_text,
            "clean_text": clean_text,
            "normalized_name": None,
            "generic_name": None,
            "strength_value": None,
            "strength_unit": None,
            "dosage_form": None,
            "matched_term": None,
            "normalization_confidence": round(
                best_score,
                3,
            ),
            "needs_review": True,
        }

    # ---------------------------------------------------------
    # Reliable match
    # ---------------------------------------------------------

    medicine = match["medicine"]

    return {
        "raw_text": raw_text,
        "clean_text": clean_text,
        "normalized_name": medicine.get(
            "brand_name"
        ),
        "generic_name": medicine.get(
            "generic_name"
        ),
        "strength_value": medicine.get(
            "strength_value"
        ),
        "strength_unit": medicine.get(
            "strength_unit"
        ),
        "dosage_form": medicine.get(
            "dosage_form"
        ),
        "matched_term": match[
            "matched_term"
        ],
        "normalization_confidence": round(
            match["score"],
            3,
        ),
        "needs_review": False,
    }


# ---------------------------------------------------------
# Normalize all candidates
# ---------------------------------------------------------

def normalize_medicine_candidates(
    candidates: list[dict],
) -> list[dict]:
    """
    Normalize all detected medicine candidates
    using the medicine CSV vocabulary.
    """

    medicines = load_medicine_vocabulary()

    return [
        normalize_medicine_candidate(
            candidate,
            medicines,
        )
        for candidate in candidates
    ]