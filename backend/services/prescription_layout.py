"""
Prescription-specific spatial reconstruction.

This module receives spatial OCR blocks and reconstructs
possible prescription entries.

It does NOT identify medicines. It only determines which
nearby OCR regions may belong to the same prescription item.
"""

from __future__ import annotations

import re
from statistics import median


MEDICINE_MARKER_PATTERN = re.compile(
    r"\b(tab(?:let)?|cap(?:sule)?|syr(?:up)?|inj(?:ection)?)\b",
    re.IGNORECASE,
)


ITEM_NUMBER_PATTERN = re.compile(
    r"^\s*[\(\[]?\d{1,2}[\)\].]?\s*$"
)


def _block_height(block: dict) -> float:
    """Return the visual height of a block."""

    return max(
        block["bottom"] - block["top"],
        1,
    )


def _block_center_y(block: dict) -> float:
    """Return the vertical center of a block."""

    return (
        block["top"] + block["bottom"]
    ) / 2


def _contains_marker(text: str) -> bool:
    """Check whether a block contains Tab, Cap, Syr, etc."""

    return bool(
        MEDICINE_MARKER_PATTERN.search(
            text or ""
        )
    )


def _is_item_number(text: str) -> bool:
    """
    Check whether OCR text looks like a prescription
    item number such as 1), 2., (3).
    """

    cleaned = (
        text
        .strip()
        .replace("©", "")
        .strip()
    )

    return bool(
        ITEM_NUMBER_PATTERN.match(cleaned)
    )


def _median_block_height(
    blocks: list[dict],
) -> float:
    """Estimate typical visual block height."""

    heights = [
        _block_height(block)
        for block in blocks
    ]

    return median(heights) if heights else 1.0


def reconstruct_prescription_items(
    blocks: list[dict],
    vertical_band_ratio: float = 2.0,
    right_distance_ratio: float = 14.0,
) -> list[dict]:
    """
    Reconstruct possible prescription items around
    medicine-marker blocks.

    Strategy:

    1. Find blocks containing Tab/Cap/Syr/Inj.
    2. Find nearby blocks on the same visual band.
    3. Prefer blocks to the right of the marker.
    4. Preserve all evidence instead of forcing a
       medicine identification.

    The distance thresholds are relative to the typical
    OCR block height, not fixed image coordinates.
    """

    if not blocks:
        return []

    blocks = sorted(
        blocks,
        key=lambda block: (
            block["top"],
            block["left"],
        ),
    )

    typical_height = _median_block_height(
        blocks
    )

    vertical_band = (
        typical_height
        * vertical_band_ratio
    )

    right_distance_limit = (
        typical_height
        * right_distance_ratio
    )

    marker_blocks = [
        block
        for block in blocks
        if _contains_marker(
            block.get("text", "")
        )
    ]

    items = []

    for marker_block in marker_blocks:

        marker_center_y = _block_center_y(
            marker_block
        )

        nearby = []

        for block in blocks:

            if block is marker_block:
                continue

            block_center_y = _block_center_y(
                block
            )

            vertical_distance = abs(
                block_center_y
                - marker_center_y
            )

            # Must be visually close vertically.
            if vertical_distance > vertical_band:
                continue

            # Prefer blocks starting to the right of
            # the medicine marker.
            horizontal_distance = (
                block["left"]
                - marker_block["right"]
            )

            # Ignore blocks far to the left.
            if horizontal_distance < (
                -typical_height * 3
            ):
                continue

            # Ignore blocks far away horizontally.
            if horizontal_distance > (
                right_distance_limit
            ):
                continue

            nearby.append(
                {
                    "block": block,
                    "vertical_distance": vertical_distance,
                    "horizontal_distance": max(
                        horizontal_distance,
                        0,
                    ),
                }
            )

        # Sort nearby blocks in reading order,
        # prioritizing horizontal proximity.
        nearby.sort(
            key=lambda item: (
                item["vertical_distance"],
                item["horizontal_distance"],
                item["block"]["left"],
            )
        )

        # Build the reconstructed evidence sequence.
        evidence_blocks = [marker_block]

        evidence_blocks.extend(
            item["block"]
            for item in nearby
        )

        # Remove duplicates while preserving order.
        unique_blocks = []
        seen_ids = set()

        for block in evidence_blocks:

            block_id = id(block)

            if block_id in seen_ids:
                continue

            seen_ids.add(block_id)
            unique_blocks.append(block)

        # -------------------------------------------------
        # Prescription reading order
        # -------------------------------------------------
        #
        # The medicine marker is our anchor.
        #
        # OCR blocks can have slightly different vertical
        # positions because of handwriting, so normal
        # top-to-bottom sorting can place words before the
        # marker incorrectly.
        #
        # Order nearby evidence primarily from left to right,
        # while keeping the marker as the anchor.

        marker_center_y = _block_center_y(
            marker_block
        )

        blocks_on_or_near_marker_line = []
        blocks_below_marker_line = []

        for block in unique_blocks:

            block_center_y = _block_center_y(
                block
            )

            vertical_distance = abs(
                block_center_y - marker_center_y
            )

            if vertical_distance <= vertical_band:
                blocks_on_or_near_marker_line.append(
                    block
                )
            else:
                blocks_below_marker_line.append(
                    block
                )

        # Same visual band: read left to right.
        blocks_on_or_near_marker_line.sort(
            key=lambda block: block["left"]
        )

        # Continuation blocks: top to bottom, then left to right.
        blocks_below_marker_line.sort(
            key=lambda block: (
                block["top"],
                block["left"],
            )
        )

        ordered_blocks = (
            blocks_on_or_near_marker_line
            + blocks_below_marker_line
        )

        # Force the medicine-marker block to be the anchor.
        if marker_block in ordered_blocks:

            ordered_blocks.remove(
                marker_block
            )

        ordered_blocks.insert(
            0,
            marker_block,
        )

        text = " ".join(
            block["text"]
            for block in ordered_blocks
        ).strip()

        if not text:
            continue

        average_confidence = sum(
            block["confidence"]
            for block in unique_blocks
        ) / len(unique_blocks)

        items.append(
            {
                "text": text,
                "marker_text": marker_block["text"],
                "confidence": round(
                    average_confidence,
                    2,
                ),
                "left": min(
                    block["left"]
                    for block in unique_blocks
                ),
                "right": max(
                    block["right"]
                    for block in unique_blocks
                ),
                "top": min(
                    block["top"]
                    for block in unique_blocks
                ),
                "bottom": max(
                    block["bottom"]
                    for block in unique_blocks
                ),
                "blocks": ordered_blocks,
            }
        )

    return items