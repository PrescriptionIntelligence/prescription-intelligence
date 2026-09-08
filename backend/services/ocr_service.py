from PIL import Image, ImageEnhance, ImageFilter
import pytesseract


def preprocess_image(image: Image.Image) -> Image.Image:
    """
    Preprocess a prescription image before OCR.

    Steps:
    1. Convert to grayscale
    2. Resize for better OCR recognition
    3. Increase contrast
    4. Sharpen the image
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


def _score_ocr_text(text: str) -> int:
    """
    Give a simple quality score to OCR output.

    This is NOT a medical correctness score.
    It only estimates whether the OCR output contains
    useful prescription-like text.
    """

    if not text:
        return 0

    score = 0

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # More meaningful lines generally indicate better OCR.
    score += min(len(lines), 20)

    text_lower = text.lower()

    # Common prescription-related terms.
    keywords = [
        "tab",
        "tablet",
        "cap",
        "capsule",
        "dose",
        "frequency",
        "duration",
        "mg",
        "ml",
        "prescription",
        "medicine",
        "after",
        "before",
        "daily",
        "morning",
        "night",
    ]

    for keyword in keywords:
        if keyword in text_lower:
            score += 5

    # Penalize extremely short OCR output.
    if len(text.strip()) < 20:
        score -= 10

    return score


def extract_text_from_image(image: Image.Image) -> str:
    """
    Run OCR using multiple Tesseract page segmentation modes
    and select the output with the best quality score.
    """

    processed_image = preprocess_image(image)

    psm_modes = [3, 4, 6, 11, 12]

    candidates = []

    for psm in psm_modes:
        text = pytesseract.image_to_string(
            processed_image,
            config=f"--psm {psm}",
        )

        score = _score_ocr_text(text)

        candidates.append(
            {
                "text": text,
                "score": score,
                "psm": psm,
            }
        )

    for candidate in candidates:
        print(
            f"\n--- PSM {candidate['psm']} | "
            f"Score: {candidate['score']} ---"
        )
        print(candidate["text"])

    best_candidate = max(
        candidates,
        key=lambda candidate: candidate["score"],
    )

    print(
        f"\n=== SELECTED PSM: {best_candidate['psm']} "
        f"| SCORE: {best_candidate['score']} ==="
    )

    return best_candidate["text"]

def extract_ocr_data(image: Image.Image) -> list[dict]:
    """
    Extract word-level OCR information including:
    - recognized text
    - confidence
    - bounding box coordinates

    This preserves spatial information that image_to_string()
    throws away.

    Returns:
        [
            {
                "text": "Tab",
                "confidence": 91.2,
                "left": 120,
                "top": 310,
                "width": 30,
                "height": 20,
            },
            ...
        ]
    """

    processed_image = preprocess_image(image)

    data = pytesseract.image_to_data(
        processed_image,
        config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )

    results = []

    for i in range(len(data["text"])):

        text = data["text"][i].strip()

        if not text:
            continue

        try:
            confidence = float(data["conf"][i])
        except (ValueError, TypeError):
            confidence = -1.0

        # Ignore Tesseract entries that have no usable confidence.
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

def group_ocr_words_into_lines(
    ocr_data: list[dict],
    y_tolerance_ratio: float = 0.55,
) -> list[dict]:
    """
    Group OCR words into approximate horizontal text lines.

    Designed for handwritten prescriptions where OCR word heights
    can vary significantly.

    The grouping uses:
    - vertical center position
    - word height
    - overlap between vertical bounding boxes

    It intentionally avoids merging words from separate prescription
    rows merely because they are geographically close.
    """

    valid_words = [
        word
        for word in ocr_data
        if word.get("text", "").strip()
        and word.get("confidence", -1) >= 0
    ]

    if not valid_words:
        return []

    # Sort primarily from top to bottom.
    valid_words.sort(
        key=lambda word: (
            word["top"] + word["height"] / 2,
            word["left"],
        )
    )

    lines = []

    for word in valid_words:

        word_top = word["top"]
        word_bottom = word["top"] + word["height"]

        word_center_y = (
            word_top + word_bottom
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
                word_center_y - line_center_y
            )

            # Dynamic center-distance tolerance.
            center_tolerance = (
                average_height * y_tolerance_ratio
            )

            # Calculate vertical overlap.
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
                overlap_bottom - overlap_top,
            )

            min_height = max(
                min(
                    line_bottom - line_top,
                    word_height,
                ),
                1,
            )

            overlap_ratio = (
                overlap / min_height
            )

            # A word belongs to a line when either:
            #
            # 1. its center is sufficiently close, OR
            # 2. its bounding box substantially overlaps.
            #
            # But do not accept very distant words.
            if (
                vertical_distance > center_tolerance
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

            best_line["words"].append(word)

            best_line["center_y"] = sum(
                (
                    w["top"] + w["height"] / 2
                )
                for w in best_line["words"]
            ) / len(best_line["words"])

            best_line["average_height"] = sum(
                max(w["height"], 1)
                for w in best_line["words"]
            ) / len(best_line["words"])

            best_line["top"] = min(
                w["top"]
                for w in best_line["words"]
            )

            best_line["bottom"] = max(
                w["top"] + w["height"]
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
                    word["left"] + word["width"]
                    for word in words
                ),

                "top": min(
                    word["top"]
                    for word in words
                ),

                "bottom": max(
                    word["top"] + word["height"]
                    for word in words
                ),

                "words": words,
            }
        )

    result.sort(
        key=lambda line: line["top"]
    )

    return result