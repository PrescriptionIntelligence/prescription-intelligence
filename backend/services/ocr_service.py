import re

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract

from backend.services.medicine_normalizer import (
    load_medicine_vocabulary,
    _estimate_best_score,
)

from backend.services.ocr_spatial_evidence import (
    extract_spatial_medicine_evidence,
)

# ---------------------------------------------------------------------------
# Basic preprocessing
# ---------------------------------------------------------------------------

def preprocess_image(image: Image.Image) -> Image.Image:
    """
    Preprocess a prescription image before OCR.

    Public behavior is intentionally preserved:

    1. Convert to grayscale
    2. Resize 2x
    3. Increase contrast
    4. Sharpen
    """

    image = image.convert("L")

    width, height = image.size

    image = image.resize(
        (width * 2, height * 2)
    )

    contrast = ImageEnhance.Contrast(image)
    image = contrast.enhance(1.5)

    image = image.filter(ImageFilter.SHARPEN)

    return image


# ---------------------------------------------------------------------------
# OCR preprocessing variants
# ---------------------------------------------------------------------------

def _build_preprocessing_variants(
    image: Image.Image,
) -> list[tuple[str, Image.Image]]:
    """
    Build OCR preprocessing variants.

    The standard variant is always first because it is the fastest and
    preserves the original OCR behavior.

    Additional variants are only used when the fast OCR path is not good
    enough.
    """

    base = preprocess_image(image)

    autocontrast = ImageOps.autocontrast(base)

    threshold_light = base.point(
        lambda pixel: 255 if pixel > 175 else 0
    )

    threshold_medium = base.point(
        lambda pixel: 255 if pixel > 200 else 0
    )

    return [
        ("standard", base),
        ("autocontrast", autocontrast),
        ("threshold_light", threshold_light),
        ("threshold_medium", threshold_medium),
    ]


# ---------------------------------------------------------------------------
# OCR quality scoring
# ---------------------------------------------------------------------------

def _score_ocr_text(text: str) -> int:
    """
    Estimate whether OCR output looks like useful prescription text.

    This is NOT a medical correctness score.
    """

    if not text:
        return 0

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        return 0

    score = 0

    text_lower = text.lower()

    # Useful line structure.
    score += min(len(lines), 20)

    # Very short OCR is usually poor.
    if len(text.strip()) < 20:
        score -= 10

    # Prescription terminology.
    strong_keywords = [
        "tablet",
        "tablets",
        "tab",
        "capsule",
        "capsules",
        "cap",
        "injection",
        "syrup",
        "suspension",
        "dose",
        "frequency",
        "duration",
        "daily",
        "morning",
        "evening",
        "night",
        "before",
        "after",
        "oral",
    ]

    for keyword in strong_keywords:
        if keyword in text_lower:
            score += 4

    # Metadata is useful but receives a smaller bonus.
    metadata_keywords = [
        "patient",
        "doctor",
        "date",
        "age",
        "gender",
        "prescription",
        "medicine",
        "medication",
    ]

    for keyword in metadata_keywords:
        if keyword in text_lower:
            score += 2

    # Strength patterns.
    strength_patterns = [
        r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|%)\b",
        r"\b\d+(?:\.\d+)?\s*(?:milligram|microgram|gram|milliliter)s?\b",
    ]

    for pattern in strength_patterns:
        matches = re.findall(
            pattern,
            text_lower,
        )

        score += min(
            len(matches) * 8,
            24,
        )

    # Dose patterns.
    dose_patterns = [
        r"\b\d+(?:\.\d+)?\s*(?:tablet|tablets|tab|capsule|capsules|cap)\b",
        r"\b\d+(?:\.\d+)?\s*(?:ml|milliliter|milliliters)\b",
        r"\b\d+(?:\.\d+)?\s*(?:drop|drops|puff|puffs)\b",
    ]

    for pattern in dose_patterns:
        matches = re.findall(
            pattern,
            text_lower,
        )

        score += min(
            len(matches) * 6,
            18,
        )

    # Frequency/schedule patterns.
    schedule_patterns = [
        r"\b\d+\s*[-/]\s*\d+\s*[-/]\s*\d+\b",
        r"\b\d+\s*x\s*(?:daily|day)\b",
        r"\bonce\s+(?:daily|a day|per day)\b",
        r"\btwice\s+(?:daily|a day|per day)\b",
        r"\bthree\s+times\s+(?:daily|a day|per day)\b",
        r"\bevery\s+(?:morning|evening|night)\b",
    ]

    for pattern in schedule_patterns:
        matches = re.findall(
            pattern,
            text_lower,
        )

        score += min(
            len(matches) * 6,
            18,
        )

    # Duration patterns.
    duration_pattern = (
        r"\b\d+(?:\.\d+)?\s*"
        r"(?:day|days|week|weeks|month|months)\b"
    )

    duration_matches = re.findall(
        duration_pattern,
        text_lower,
    )

    score += min(
        len(duration_matches) * 5,
        10,
    )

    # Numeric content.
    numeric_matches = re.findall(
        r"\b\d+(?:\.\d+)?\b",
        text_lower,
    )

    score += min(
        len(numeric_matches) * 2,
        12,
    )

    # Obvious OCR garbage.
    punctuation_runs = re.findall(
        r"[^\w\s]{4,}",
        text,
    )

    score -= min(
        len(punctuation_runs) * 3,
        12,
    )

    # Extremely long lines can indicate merged OCR regions.
    for line in lines:
        if len(line) > 180:
            score -= 3

    return score


# ---------------------------------------------------------------------------
# Medicine-aware OCR evidence
# ---------------------------------------------------------------------------

_MEDICINE_EVIDENCE_THRESHOLD = 0.85

_MEDICINE_LINE_CLEANUP_RE = re.compile(
    r"\b(?:tab(?:let)?|cap(?:sule)?|caps(?:ule)?|"
    r"inj(?:ection)?|syp(?:rup)?)\b",
    re.IGNORECASE,
)

_MEDICINE_STRENGTH_CLEANUP_RE = re.compile(
    r"\b\d+(?:\.\d+)?"
    r"(?:\s*\+\s*\d+(?:\.\d+)?)?"
    r"\s*(?:mg|mcg|g|ml|%)\b",
    re.IGNORECASE,
)

_MEDICINE_DOSE_CLEANUP_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*"
    r"(?:tablet|tablets|tab|capsule|capsules|cap|"
    r"ml|milliliter|milliliters|drop|drops|puff|puffs|"
    r"unit|units)\b",
    re.IGNORECASE,
)

_MEDICINE_SCHEDULE_RE = re.compile(
    r"\b\d+(?:\.\d+)?"
    r"(?:\s*[-/:]\s*\d+(?:\.\d+)?){1,2}\b"
)


def _prepare_medicine_evidence_line(
    line: str,
) -> str:
    """
    Remove obvious prescription fields from one OCR line before
    medicine-vocabulary comparison.

    This is intentionally lightweight and does not identify medicines.
    It only prepares OCR text for an evidence estimate.
    """

    if not line:
        return ""

    candidate = line.strip()

    candidate = _MEDICINE_LINE_CLEANUP_RE.sub(
        " ",
        candidate,
    )

    candidate = _MEDICINE_STRENGTH_CLEANUP_RE.sub(
        " ",
        candidate,
    )

    candidate = _MEDICINE_DOSE_CLEANUP_RE.sub(
        " ",
        candidate,
    )

    candidate = _MEDICINE_SCHEDULE_RE.sub(
        " ",
        candidate,
    )

    candidate = re.sub(
        r"\b(?:dose|frequency|duration|instructions?)\s*:",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )

    candidate = re.sub(
        r"\s+",
        " ",
        candidate,
    ).strip()

    return candidate


def _score_medicine_evidence(
    text: str,
    vocabulary: list[dict],
) -> dict:
    """
    Estimate medicine-related evidence inside an OCR candidate.

    This is deliberately NOT a medicine identification step.

    It only asks:

        "Does this OCR candidate contain one or more lines that
         resemble entries in the existing local medicine vocabulary?"

    The existing medicine normalizer performs the actual normalization
    later in the prescription pipeline.

    Returns:

        {
            "score": float,
            "matched_lines": int,
            "strong_matches": int,
            "line_scores": [...]
        }
    """

    if not text or not vocabulary:
        return {
            "score": 0.0,
            "matched_lines": 0,
            "strong_matches": 0,
            "line_scores": [],
        }

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        return {
            "score": 0.0,
            "matched_lines": 0,
            "strong_matches": 0,
            "line_scores": [],
        }

    line_scores = []

    for line in lines:

        prepared = _prepare_medicine_evidence_line(
            line
        )

        if not prepared:
            continue

        # Avoid treating very short OCR fragments as medicine evidence.
        if len(prepared) < 3:
            continue

        score = _estimate_best_score(
            prepared,
            vocabulary,
        )

        if score >= _MEDICINE_EVIDENCE_THRESHOLD:

            line_scores.append(
                {
                    "text": line,
                    "score": round(
                        score,
                        3,
                    ),
                }
            )

    line_scores.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    strong_matches = len(line_scores)

    # Count only the strongest few lines so a long OCR document
    # cannot accumulate unlimited medicine evidence.
    capped_scores = [
        item["score"]
        for item in line_scores[:5]
    ]

    if not capped_scores:
        return {
            "score": 0.0,
            "matched_lines": 0,
            "strong_matches": 0,
            "line_scores": [],
        }

    # The strongest medicine-like line is the primary evidence.
    #
    # Additional strong lines provide diminishing support.
    medicine_score = capped_scores[0]

    for additional_score in capped_scores[1:]:
        medicine_score += (
            additional_score * 0.20
        )

    # Cap the evidence contribution.
    medicine_score = min(
        medicine_score,
        2.0,
    )

    return {
        "score": round(
            medicine_score,
            3,
        ),
        "matched_lines": len(
            capped_scores
        ),
        "strong_matches": strong_matches,
        "line_scores": line_scores[:5],
    }


def _calculate_combined_candidate_score(
    structural_score: int,
    medicine_evidence: dict,
) -> float:
    """
    Combine structural OCR quality with medicine evidence.

    Structural OCR quality remains the dominant signal.

    Medicine evidence is a bounded bonus rather than a replacement
    for OCR quality.

    This prevents a tiny accidental medicine-like fragment from
    dominating an otherwise unusable OCR result.
    """

    medicine_score = float(
        medicine_evidence.get(
            "score",
            0.0,
        )
    )

    matched_lines = int(
        medicine_evidence.get(
            "matched_lines",
            0,
        )
    )

    # Primary medicine evidence.
    bonus = medicine_score * 12.0

    # Additional confirmation from multiple medicine-like lines.
    if matched_lines >= 2:
        bonus += min(
            (matched_lines - 1) * 2.0,
            6.0,
        )

    # Keep medicine evidence bounded.
    bonus = min(
        bonus,
        30.0,
    )

    return round(
        structural_score + bonus,
        2,
    )


def _has_reliable_medicine_evidence(
    medicine_evidence: dict,
) -> bool:
    """
    Return True when an OCR candidate contains at least one strong
    medicine-vocabulary signal.
    """

    return bool(
        medicine_evidence.get(
            "matched_lines",
            0,
        ) > 0
        and medicine_evidence.get(
            "score",
            0.0,
        ) >= _MEDICINE_EVIDENCE_THRESHOLD
    )


# ---------------------------------------------------------------------------
# OCR candidate helpers
# ---------------------------------------------------------------------------

def _normalize_ocr_text(text: str) -> str:
    """
    Normalize OCR text only for candidate comparison.

    The actual OCR text returned to the application is preserved.
    """

    return "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ).strip()


def _run_text_ocr(
    image: Image.Image,
    psm: int,
) -> str:
    """
    Run Tesseract text OCR for one image/PSM configuration.
    """

    return pytesseract.image_to_string(
        image,
        config=f"--psm {psm}",
    )

def _get_spatial_medicine_evidence(
    processed_image: Image.Image,
    psm: int,
    medicine_vocabulary: list[dict],
) -> dict:
    """
    Run word-level OCR for one candidate configuration and generate
    spatial medicine evidence.

    This is evidence only. It does not resolve or verify medicines.
    """

    ocr_data = _extract_ocr_data_with_configuration(
        processed_image,
        psm,
    )

    if not ocr_data:
        return {
            "score": 0.0,
            "matched_blocks": 0,
            "strong_matches": 0,
            "candidates": [],
            "blocks": [],
        }

    return extract_spatial_medicine_evidence(
        ocr_data,
        medicine_vocabulary,
    )

def _make_candidate(
    text: str,
    preprocessing: str,
    psm: int,
    medicine_vocabulary: list[dict] | None = None,
    processed_image: Image.Image | None = None,
) -> dict | None:
    """
    Build a normalized OCR candidate.

    Medicine-aware evidence is optional so this helper remains compatible
    with callers that only need structural OCR scoring.
    """

    normalized_text = _normalize_ocr_text(text)

    if not normalized_text:
        return None

    structural_score = _score_ocr_text(
        normalized_text
    )

    if medicine_vocabulary is None:
        medicine_evidence = {
            "score": 0.0,
            "matched_lines": 0,
            "strong_matches": 0,
            "line_scores": [],
        }
    else:
        if processed_image is not None:
            medicine_evidence = _get_spatial_medicine_evidence(
                processed_image,
                6,
                medicine_vocabulary,
            )
        else:
            medicine_evidence = _score_medicine_evidence(
                normalized_text,
                medicine_vocabulary,
            )

    combined_score = (
        _calculate_combined_candidate_score(
            structural_score,
            medicine_evidence,
        )
    )

    return {
        "text": normalized_text,

        # Preserve the original structural score.
        "score": structural_score,

        # New medicine-aware evidence.
        "medicine_evidence": medicine_evidence,

        # Combined score is used only for candidate selection.
        "combined_score": combined_score,

        "psm": psm,

        "preprocessing": preprocessing,
    }


# ---------------------------------------------------------------------------
# Main OCR text extraction
# ---------------------------------------------------------------------------

def extract_text_from_image(
    image: Image.Image,
) -> str:
    """
    Extract prescription text using a medicine-aware OCR selection strategy.

    Fast path:
        standard preprocessing + PSM 6

    Fallback:
        additional PSM modes and preprocessing variants are evaluated only
        when the fast result is not sufficiently strong.

    Candidate selection considers both:

        1. Structural OCR quality
        2. Medicine-vocabulary evidence

    This avoids selecting OCR that merely looks like a prescription while
    producing no useful medicine candidates.

    The returned OCR text itself remains unchanged.
    """

    medicine_vocabulary = (
        load_medicine_vocabulary()
    )

    variants = _build_preprocessing_variants(image)

    standard_name, standard_image = variants[0]

    # -----------------------------------------------------------------------
    # FAST PATH
    # -----------------------------------------------------------------------

    fast_text = _run_text_ocr(
        standard_image,
        psm=6,
    )

    fast_candidate = _make_candidate(
        fast_text,
        standard_name,
        6,
        medicine_vocabulary=medicine_vocabulary,
        processed_image=standard_image,
    )

    if fast_candidate is not None:

        print(
            f"\n--- FAST OCR | "
            f"{fast_candidate['preprocessing']} | "
            f"PSM {fast_candidate['psm']} | "
            f"Structural Score: "
            f"{fast_candidate['score']} | "
            f"Medicine Evidence: "
            f"{fast_candidate['medicine_evidence']['score']:.2f} | "
            f"Combined Score: "
            f"{fast_candidate['combined_score']:.2f} "
            f"---"
        )

        print(
            fast_candidate["text"]
        )

        # A strong prescription-like result should only take the fast path
        # when there is also reliable medicine evidence.
        #
        # This prevents structurally strong but medicine-empty OCR from
        # bypassing the fallback candidates.
        if (
            fast_candidate["score"] >= 55
            and _has_reliable_medicine_evidence(
                fast_candidate["medicine_evidence"]
            )
        ):

            print(
                f"\n=== SELECTED OCR: "
                f"{fast_candidate['preprocessing']} | "
                f"PSM {fast_candidate['psm']} | "
                f"STRUCTURAL SCORE: "
                f"{fast_candidate['score']} | "
                f"COMBINED SCORE: "
                f"{fast_candidate['combined_score']:.2f} "
                f"| FAST PATH ==="
            )

            return fast_candidate["text"]

    # -----------------------------------------------------------------------
    # FALLBACK PATH
    # -----------------------------------------------------------------------

    candidates = []

    if fast_candidate is not None:
        candidates.append(
            fast_candidate
        )

    # We already tested standard + PSM 6.
    fallback_configurations = [
        ("standard", standard_image, 3),
        ("standard", standard_image, 4),
        ("standard", standard_image, 11),
        ("autocontrast", variants[1][1], 6),
        ("autocontrast", variants[1][1], 11),
        ("threshold_light", variants[2][1], 6),
        ("threshold_light", variants[2][1], 11),
        ("threshold_medium", variants[3][1], 6),
    ]

    seen = set()

    if fast_candidate is not None:
        seen.add(
            fast_candidate["text"].lower()
        )

    for preprocessing, processed_image, psm in fallback_configurations:

        text = _run_text_ocr(
            processed_image,
            psm,
        )

        candidate = _make_candidate(
            text,
            preprocessing,
            psm,
            medicine_vocabulary=medicine_vocabulary,
        )

        if candidate is None:
            continue

        dedupe_key = candidate["text"].lower()

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        candidates.append(candidate)

    if not candidates:
        return ""

    for candidate in candidates:

        medicine_evidence = candidate[
            "medicine_evidence"
        ]

        print(
            f"\n--- "
            f"{candidate['preprocessing']} | "
            f"PSM {candidate['psm']} | "
            f"Structural Score: "
            f"{candidate['score']} | "
            f"Medicine Evidence: "
            f"{medicine_evidence['score']:.2f} | "
            f"Combined Score: "
            f"{candidate['combined_score']:.2f} "
            f"---"
        )

        print(
            candidate["text"]
        )

    # -----------------------------------------------------------------------
    # Candidate selection
    # -----------------------------------------------------------------------

    best_candidate = max(
        candidates,
        key=lambda candidate: (
            candidate["combined_score"],
            candidate["score"],
            len(candidate["text"]),
        ),
    )

    print(
        f"\n=== SELECTED OCR: "
        f"{best_candidate['preprocessing']} | "
        f"PSM {best_candidate['psm']} | "
        f"STRUCTURAL SCORE: "
        f"{best_candidate['score']} | "
        f"COMBINED SCORE: "
        f"{best_candidate['combined_score']:.2f} "
        f"| FALLBACK PATH ==="
    )

    return best_candidate["text"]


# ---------------------------------------------------------------------------
# Word-level OCR
# ---------------------------------------------------------------------------

def _extract_ocr_data_with_configuration(
    processed_image: Image.Image,
    psm: int,
) -> list[dict]:
    """
    Run word-level OCR for one preprocessing/PSM configuration.
    """

    data = pytesseract.image_to_data(
        processed_image,
        config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT,
    )

    results = []

    for i in range(len(data["text"])):

        text = data["text"][i].strip()

        if not text:
            continue

        try:
            confidence = float(
                data["conf"][i]
            )
        except (ValueError, TypeError):
            confidence = -1.0

        if confidence < 0:
            continue

        results.append(
            {
                "text": text,
                "confidence": confidence,
                "left": int(data["left"][i]),
                "top": int(data["top"][i]),
                "width": int(data["width"][i]),
                "height": int(data["height"][i]),
            }
        )

    return results


def _score_ocr_data(
    ocr_data: list[dict],
) -> float:
    """
    Estimate word-level OCR quality.

    This is not a medical correctness score.
    """

    if not ocr_data:
        return 0.0

    recognized_words = [
        word
        for word in ocr_data
        if word.get("text", "").strip()
    ]

    if not recognized_words:
        return 0.0

    average_confidence = sum(
        word.get("confidence", 0.0)
        for word in recognized_words
    ) / len(recognized_words)

    useful_words = 0

    useful_terms = {
        "tab",
        "tablet",
        "tablets",
        "cap",
        "capsule",
        "capsules",
        "mg",
        "mcg",
        "ml",
        "dose",
        "daily",
        "morning",
        "evening",
        "night",
        "before",
        "after",
    }

    for word in recognized_words:

        normalized = (
            word["text"]
            .lower()
            .strip()
        )

        if normalized in useful_terms:
            useful_words += 1
            continue

        if any(
            character.isdigit()
            for character in normalized
        ):
            useful_words += 1

    score = average_confidence

    score += min(
        useful_words * 3,
        24,
    )

    score += min(
        len(recognized_words),
        12,
    )

    return score


def extract_ocr_data(
    image: Image.Image,
) -> list[dict]:
    """
    Extract word-level OCR data.

    Fast path:
        standard preprocessing + PSM 6

    Fallback:
        a small number of additional configurations only when the fast
        result is weak.

    The return schema remains unchanged.

    NOTE:
        Medicine-aware text candidate scoring is intentionally separate
        from word-level OCR data extraction. Spatial OCR will be integrated
        in a later controlled phase.
    """

    variants = _build_preprocessing_variants(image)

    standard_image = variants[0][1]

    # -----------------------------------------------------------------------
    # FAST PATH
    # -----------------------------------------------------------------------

    fast_data = _extract_ocr_data_with_configuration(
        standard_image,
        6,
    )

    fast_score = _score_ocr_data(
        fast_data
    )

    print(
        f"\n=== OCR DATA FAST PATH | "
        f"standard | PSM 6 | "
        f"SCORE: {fast_score:.2f} ==="
    )

    # Word-level OCR has confidence on a different scale than text scoring.
    # A score around 70 generally represents a strong OCR result.
    if fast_data and fast_score >= 70:
        return fast_data

    # -----------------------------------------------------------------------
    # FALLBACK PATH
    # -----------------------------------------------------------------------

    candidates = []

    if fast_data:
        candidates.append(
            {
                "data": fast_data,
                "score": fast_score,
                "psm": 6,
                "preprocessing": "standard",
            }
        )

    fallback_configurations = [
        ("standard", standard_image, 3),
        ("standard", standard_image, 4),
        ("standard", standard_image, 11),
        ("autocontrast", variants[1][1], 6),
        ("autocontrast", variants[1][1], 11),
        ("threshold_light", variants[2][1], 6),
    ]

    for preprocessing, processed_image, psm in fallback_configurations:

        ocr_data = _extract_ocr_data_with_configuration(
            processed_image,
            psm,
        )

        if not ocr_data:
            continue

        score = _score_ocr_data(
            ocr_data
        )

        candidates.append(
            {
                "data": ocr_data,
                "score": score,
                "psm": psm,
                "preprocessing": preprocessing,
            }
        )

    if not candidates:
        return []

    best_candidate = max(
        candidates,
        key=lambda candidate: (
            candidate["score"],
            len(candidate["data"]),
        ),
    )

    print(
        f"\n=== SELECTED OCR DATA: "
        f"{best_candidate['preprocessing']} | "
        f"PSM {best_candidate['psm']} | "
        f"SCORE: {best_candidate['score']:.2f} "
        f"| FALLBACK PATH ==="
    )

    return best_candidate["data"]


# ---------------------------------------------------------------------------
# OCR line grouping
# ---------------------------------------------------------------------------

def group_ocr_words_into_lines(
    ocr_data: list[dict],
    y_tolerance_ratio: float = 0.55,
) -> list[dict]:
    """
    Group OCR words into approximate horizontal text lines.

    Designed for handwritten prescriptions where OCR word heights
    can vary significantly.
    """

    valid_words = [
        word
        for word in ocr_data
        if word.get("text", "").strip()
        and word.get("confidence", -1) >= 0
    ]

    if not valid_words:
        return []

    valid_words.sort(
        key=lambda word: (
            word["top"]
            + word["height"] / 2,
            word["left"],
        )
    )

    lines = []

    for word in valid_words:

        word_top = word["top"]
        word_bottom = (
            word["top"]
            + word["height"]
        )

        word_center_y = (
            word_top
            + word_bottom
        ) / 2

        word_height = max(
            word["height"],
            1,
        )

        best_line = None
        best_distance = float("inf")

        for line in lines:

            line_center_y = line["center_y"]
            line_top = line["top"]
            line_bottom = line["bottom"]

            average_height = max(
                line["average_height"],
                word_height,
                1,
            )

            vertical_distance = abs(
                word_center_y
                - line_center_y
            )

            center_tolerance = (
                average_height
                * y_tolerance_ratio
            )

            overlap_top = max(
                line_top,
                word_top,
            )

            overlap_bottom = min(
                line_bottom,
                word_bottom,
            )

            overlap = max(
                0,
                overlap_bottom
                - overlap_top,
            )

            min_height = max(
                min(
                    line_bottom
                    - line_top,
                    word_height,
                ),
                1,
            )

            overlap_ratio = (
                overlap
                / min_height
            )

            if (
                vertical_distance
                > center_tolerance
                and overlap_ratio < 0.35
            ):
                continue

            if vertical_distance < best_distance:
                best_distance = vertical_distance
                best_line = line

        if best_line is None:

            lines.append(
                {
                    "words": [word],
                    "center_y": word_center_y,
                    "average_height": word_height,
                    "top": word_top,
                    "bottom": word_bottom,
                }
            )

        else:

            best_line["words"].append(
                word
            )

            best_line["center_y"] = sum(
                (
                    w["top"]
                    + w["height"] / 2
                )
                for w in best_line["words"]
            ) / len(best_line["words"])

            best_line["average_height"] = sum(
                max(
                    w["height"],
                    1,
                )
                for w in best_line["words"]
            ) / len(best_line["words"])

            best_line["top"] = min(
                w["top"]
                for w in best_line["words"]
            )

            best_line["bottom"] = max(
                w["top"]
                + w["height"]
                for w in best_line["words"]
            )

    result = []

    for line in lines:

        words = sorted(
            line["words"],
            key=lambda word: word["left"],
        )

        text = " ".join(
            word["text"]
            for word in words
        ).strip()

        if not text:
            continue

        confidence = sum(
            word["confidence"]
            for word in words
        ) / len(words)

        result.append(
            {
                "text": text,
                "confidence": confidence,
                "left": min(
                    word["left"]
                    for word in words
                ),
                "right": max(
                    word["left"]
                    + word["width"]
                    for word in words
                ),
                "top": min(
                    word["top"]
                    for word in words
                ),
                "bottom": max(
                    word["top"]
                    + word["height"]
                    for word in words
                ),
                "words": words,
            }
        )

    result.sort(
        key=lambda line: line["top"]
    )

    return result