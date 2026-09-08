"""
Spatial layout analysis for prescription OCR.

This module does NOT identify medicines.

Its job is to preserve the spatial structure of OCR output
and group nearby OCR words into meaningful visual blocks.
"""

from __future__ import annotations

from statistics import median


def _word_center(word: dict) -> tuple[float, float]:
    """Return the center (x, y) of an OCR word."""

    center_x = (
        word["left"] + word["width"] / 2
    )

    center_y = (
        word["top"] + word["height"] / 2
    )

    return center_x, center_y


def _vertical_overlap(
    word_a: dict,
    word_b: dict,
) -> float:
    """
    Calculate vertical overlap between two OCR words.

    Returns a value between 0 and 1.
    """

    a_top = word_a["top"]
    a_bottom = (
        word_a["top"] + word_a["height"]
    )

    b_top = word_b["top"]
    b_bottom = (
        word_b["top"] + word_b["height"]
    )

    overlap = max(
        0,
        min(a_bottom, b_bottom)
        - max(a_top, b_top),
    )

    smaller_height = max(
        min(
            word_a["height"],
            word_b["height"],
        ),
        1,
    )

    return overlap / smaller_height


def _horizontal_gap(
    word_a: dict,
    word_b: dict,
) -> float:
    """
    Calculate horizontal distance between two words.

    Assumes word_a is to the left of word_b.
    """

    a_right = (
        word_a["left"] + word_a["width"]
    )

    return max(
        0,
        word_b["left"] - a_right,
    )


def _prepare_words(
    ocr_data: list[dict],
    min_confidence: float = 0.0,
) -> list[dict]:
    """
    Remove unusable OCR entries and normalize their structure.
    """

    words = []

    for word in ocr_data:

        text = str(
            word.get("text", "")
        ).strip()

        confidence = float(
            word.get("confidence", -1)
        )

        if not text:
            continue

        if confidence < min_confidence:
            continue

        if word.get("width", 0) <= 0:
            continue

        if word.get("height", 0) <= 0:
            continue

        words.append(
            {
                "text": text,
                "confidence": confidence,
                "left": int(word["left"]),
                "top": int(word["top"]),
                "width": int(word["width"]),
                "height": int(word["height"]),
            }
        )

    return words


def group_words_into_spatial_blocks(
    ocr_data: list[dict],
    min_confidence: float = 0.0,
    vertical_tolerance_ratio: float = 0.75,
    horizontal_gap_ratio: float = 4.0,
) -> list[dict]:
    """
    Group OCR words into spatial blocks.

    Unlike the existing line grouper, this function considers
    BOTH vertical alignment and horizontal distance.

    This is important for prescriptions because a single visual
    row may contain:

        medicine | dose | frequency | instructions

    and should not automatically become one medicine name.

    Returns:

        [
            {
                "text": "...",
                "confidence": 72.4,
                "left": 100,
                "right": 500,
                "top": 300,
                "bottom": 350,
                "words": [...]
            }
        ]
    """

    words = _prepare_words(
        ocr_data,
        min_confidence=min_confidence,
    )

    if not words:
        return []

    # Estimate typical OCR word height.
    typical_height = median(
        word["height"]
        for word in words
    )

    vertical_tolerance = (
        typical_height
        * vertical_tolerance_ratio
    )

    horizontal_gap_limit = (
        typical_height
        * horizontal_gap_ratio
    )

    # Top-to-bottom, then left-to-right.
    words.sort(
        key=lambda word: (
            word["top"],
            word["left"],
        )
    )

    blocks = []

    for word in words:

        center_x, center_y = _word_center(
            word
        )

        best_block = None
        best_distance = float("inf")

        for block in blocks:

            block_center_y = block[
                "center_y"
            ]

            vertical_distance = abs(
                center_y - block_center_y
            )

            if (
                vertical_distance
                > vertical_tolerance
            ):
                continue

            # Find the closest word on the right/left
            # edge of the existing block.
            block_right = block["right"]
            block_left = block["left"]

            if word["left"] >= block_right:

                horizontal_gap = (
                    word["left"]
                    - block_right
                )

            elif (
                word["left"]
                + word["width"]
                <= block_left
            ):

                horizontal_gap = (
                    block_left
                    - (
                        word["left"]
                        + word["width"]
                    )
                )

            else:

                horizontal_gap = 0

            # A large horizontal gap means that the OCR
            # words may belong to different visual regions.
            if (
                horizontal_gap
                > horizontal_gap_limit
            ):
                continue

            distance = (
                vertical_distance
                + horizontal_gap * 0.25
            )

            if distance < best_distance:
                best_distance = distance
                best_block = block

        if best_block is None:

            blocks.append(
                {
                    "words": [word],
                    "center_y": center_y,
                    "left": word["left"],
                    "right": (
                        word["left"]
                        + word["width"]
                    ),
                    "top": word["top"],
                    "bottom": (
                        word["top"]
                        + word["height"]
                    ),
                }
            )

        else:

            best_block["words"].append(word)

            best_block["left"] = min(
                best_block["left"],
                word["left"],
            )

            best_block["right"] = max(
                best_block["right"],
                word["left"]
                + word["width"],
            )

            best_block["top"] = min(
                best_block["top"],
                word["top"],
            )

            best_block["bottom"] = max(
                best_block["bottom"],
                word["top"]
                + word["height"],
            )

            # Recalculate vertical center.
            best_block["center_y"] = sum(
                _word_center(w)[1]
                for w in best_block["words"]
            ) / len(
                best_block["words"]
            )

    # Build clean output.
    result = []

    for block in blocks:

        words = sorted(
            block["words"],
            key=lambda word: (
                word["left"],
                word["top"],
            ),
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
                "confidence": round(
                    confidence,
                    2,
                ),
                "left": block["left"],
                "right": block["right"],
                "top": block["top"],
                "bottom": block["bottom"],
                "words": words,
            }
        )

    result.sort(
        key=lambda block: (
            block["top"],
            block["left"],
        )
    )

    return result