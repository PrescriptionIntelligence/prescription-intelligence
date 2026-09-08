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

    best_candidate = max(
        candidates,
        key=lambda candidate: candidate["score"],
    )

    return best_candidate["text"]