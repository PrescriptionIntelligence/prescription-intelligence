import re


MEDICINE_MARKERS = {
    "tab",
    "tablet",
    "cap",
    "capsule",
    "syr",
    "syrup",
    "inj",
    "injection",
}


STRENGTH_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|%)\b",
    re.IGNORECASE,
)


MEDICINE_MARKER_PATTERN = re.compile(
    r"\b(tab(?:let)?|cap(?:sule)?|syr(?:up)?|inj(?:ection)?)\b",
    re.IGNORECASE,
)


def _contains_medicine_marker(text: str) -> bool:
    return bool(
        MEDICINE_MARKER_PATTERN.search(text)
    )


def _contains_strength(text: str) -> bool:
    return bool(
        STRENGTH_PATTERN.search(text)
    )


def _extract_marker(text: str) -> str | None:
    match = MEDICINE_MARKER_PATTERN.search(text)

    if not match:
        return None

    return match.group(1)


def _extract_strength(text: str) -> str | None:
    match = STRENGTH_PATTERN.search(text)

    if not match:
        return None

    return match.group(0)


def _calculate_candidate_score(
    confidence: float,
    marker_found: bool,
    strength_found: bool,
) -> float:

    score = 0.0

    if marker_found:
        score += 0.60

    if strength_found:
        score += 0.25

    normalized_confidence = min(
        max(confidence, 0.0) / 100.0,
        1.0,
    )

    score += normalized_confidence * 0.15

    return min(score, 1.0)


def _clean_token(token: str) -> str:
    """
    Remove obvious numbering/symbol noise from an OCR token.
    """

    token = token.strip()

    token = re.sub(
        r"^[©@*()\[\]{}_\-=+.,;:]+",
        "",
        token,
    )

    token = re.sub(
        r"[©@*()\[\]{}_\-=+.,;:]+$",
        "",
        token,
    )

    return token.strip()


def _extract_medicine_text_from_words(
    line: dict,
    marker: str | None,
    strength: str | None,
) -> str:
    """
    Extract the text immediately following the medicine marker.

    Instead of sending the entire OCR line to the normalizer,
    use spatially ordered OCR words.

    This is intentionally conservative because OCR handwriting
    can contain unrelated text on the same line.
    """

    words = line.get("words", [])

    if not words:
        return ""

    words = sorted(
        words,
        key=lambda word: word["left"],
    )

    marker_index = None

    if marker:
        marker_lower = marker.lower()

        for i, word in enumerate(words):
            if word["text"].strip().lower() == marker_lower:
                marker_index = i
                break

    # If the exact marker word cannot be located,
    # fall back to line text.
    if marker_index is None:

        text = line.get("text", "")

        if marker:
            text = re.sub(
                re.escape(marker),
                " ",
                text,
                count=1,
                flags=re.IGNORECASE,
            )

        if strength:
            text = text.replace(
                strength,
                " ",
            )

        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

    # Start immediately after "Tab", "Cap", etc.
    medicine_words = words[
        marker_index + 1:
    ]

    selected = []

    for word in medicine_words:

        token = word["text"].strip()

        if not token:
            continue

        # Stop if a recognizable strength is encountered.
        if STRENGTH_PATTERN.search(token):
            break

        cleaned = _clean_token(token)

        if not cleaned:
            continue

        # Ignore obvious OCR numbering/symbol tokens.
        if re.fullmatch(
            r"\d+",
            cleaned,
        ):
            continue

        # Ignore extremely low-confidence single-character noise.
        if (
            len(cleaned) <= 1
            and float(word.get("confidence", 0)) < 60
        ):
            continue

        selected.append(cleaned)

    return " ".join(selected).strip()


def detect_medicine_candidates(
    ocr_lines: list[dict],
) -> list[dict]:
    """
    Detect potential medicine entries from OCR lines.

    The detector identifies prescription-like regions but does
    not decide what medicine they represent.
    """

    candidates = []

    for line in ocr_lines:

        text = line.get(
            "text",
            "",
        ).strip()

        if not text:
            continue

        confidence = float(
            line.get(
                "confidence",
                0,
            )
        )

        marker = _extract_marker(text)
        strength = _extract_strength(text)

        marker_found = marker is not None
        strength_found = strength is not None

        if not marker_found and not strength_found:
            continue

        candidate_score = _calculate_candidate_score(
            confidence=confidence,
            marker_found=marker_found,
            strength_found=strength_found,
        )

        medicine_text = (
            _extract_medicine_text_from_words(
                line=line,
                marker=marker,
                strength=strength,
            )
        )

        if not medicine_text:
            continue

        candidates.append(
            {
                "text": text,

                "medicine_text": medicine_text,

                "marker": marker,

                "strength": strength,

                "ocr_confidence": round(
                    confidence / 100,
                    3,
                ),

                "candidate_score": round(
                    candidate_score,
                    3,
                ),

                "marker_found": marker_found,

                "strength_found": strength_found,

                "left": line.get("left"),

                "top": line.get("top"),

                "right": line.get("right"),

                "bottom": line.get("bottom"),
            }
        )

    return candidates

def _extract_medicine_text(
    text: str,
    marker: str | None,
    strength: str | None,
) -> str:
    """
    Remove the prescription marker and detected strength
    from reconstructed OCR text.

    The remaining text is used as noisy medicine-name
    evidence for later normalization.
    """

    result = text

    if marker:
        result = result.replace(
            marker,
            " ",
            1,
        )

    if strength:
        result = result.replace(
            strength,
            " ",
            1,
        )

    # Remove common prescription numbering and symbols
    # from the beginning of the candidate.
    result = re.sub(
        r"^[\s©@*()\[\]{}_\-=+]+",
        " ",
        result,
    )

    # Normalize whitespace.
    result = re.sub(
        r"\s+",
        " ",
        result,
    ).strip()

    return result

def detect_medicine_candidates_from_items(
    items: list[dict],
) -> list[dict]:
    """
    Convert reconstructed prescription items into
    medicine candidates.

    The items have already been spatially reconstructed
    around prescription markers such as Tab or Cap.
    """

    candidates = []

    for item in items:

        text = item.get(
            "text",
            "",
        ).strip()

        if not text:
            continue

        marker = item.get(
            "marker_text",
            None,
        )

        # Reconstructed items should normally already
        # contain a prescription marker.
        if not marker:
            continue

        confidence = float(
            item.get(
                "confidence",
                0.0,
            )
        )

        strength = _extract_strength(
            text,
        )

        medicine_text = _extract_medicine_text(
            text=text,
            marker=marker,
            strength=strength,
        )

        candidate_score = _calculate_candidate_score(
            confidence=confidence,
            marker_found=True,
            strength_found=strength is not None,
        )

        candidates.append(
            {
                "text": text,

                "medicine_text": medicine_text,

                "marker": marker,

                "strength": strength,

                "ocr_confidence": round(
                    confidence / 100,
                    3,
                ),

                "candidate_score": round(
                    candidate_score,
                    3,
                ),

                "marker_found": True,

                "strength_found": strength is not None,

                "left": item.get("left"),

                "top": item.get("top"),

                "right": item.get("right"),

                "bottom": item.get("bottom"),
            }
        )

    return candidates