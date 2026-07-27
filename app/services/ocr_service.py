"""
OCR service.

Strategy:
1. Try to pull text directly out of the PDF (works if it has a real text layer).
2. For any page with little/no extractable text (i.e. it's a scanned image),
   render that page to an image and run Tesseract OCR on it.

Requires (system-level, not just pip):
- Tesseract OCR installed and on PATH: https://github.com/UB-Mannheim/tesseract/wiki (Windows)
- Poppler (needed by pdf2image) — on Windows, download poppler binaries and add
  the `bin/` folder to PATH: https://github.com/oschwartz10612/poppler-windows/releases
"""

import platform
from pathlib import Path

import numpy as np
import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance

# On Windows, pytesseract often can't find tesseract.exe even after install
# unless it's been added to PATH manually. Point at the default install
# location directly so it "just works". Adjust this path if you installed
# Tesseract somewhere else.
if platform.system() == "Windows":
    _default_windows_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if _default_windows_path.exists():
        pytesseract.pytesseract.tesseract_cmd = str(_default_windows_path)

# Minimum characters on a page before we trust the embedded text layer
# and skip OCR for that page.
MIN_TEXT_LEN_THRESHOLD = 20

# --oem 1  = use the LSTM neural-net recognition engine (much more accurate
#            than the legacy engine, which is Tesseract's default fallback)
# --psm 6  = "assume a single uniform block of text" — a better fit for
#            scanned memo/letter pages than the default psm, which tries
#            to guess layout and can fragment text incorrectly
TESSERACT_CONFIG = "--oem 1 --psm 6"


def _otsu_threshold(gray: np.ndarray) -> int:
    """Computes a black/white cutoff automatically from the image's own
    histogram, instead of guessing a fixed brightness value."""
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = gray.size
    sum_total = np.dot(np.arange(256), hist)
    sum_bg = 0.0
    w_bg = 0
    max_var = 0.0
    threshold = 128
    for t in range(256):
        w_bg += hist[t]
        if w_bg == 0:
            continue
        w_fg = total - w_bg
        if w_fg == 0:
            break
        sum_bg += t * hist[t]
        m_bg = sum_bg / w_bg
        m_fg = (sum_total - sum_bg) / w_fg
        var_between = w_bg * w_fg * (m_bg - m_fg) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return threshold


def _upscale_and_contrast(image: Image.Image) -> Image.Image:
    """First half of preprocessing: grayscale, upscale, contrast boost —
    stops before binarizing. Exposed separately because the combined
    OCR+ICR pipeline needs to crop regions from this less-destructive
    version (TrOCR handles grayscale/contrast-enhanced crops better than
    stark pure-black-white ones)."""
    gray = image.convert("L")

    if gray.width < 2400:
        scale = 2400 / gray.width
        new_size = (int(gray.width * scale), int(gray.height * scale))
        gray = gray.resize(new_size, Image.LANCZOS)

    return ImageEnhance.Contrast(gray).enhance(1.5)


def _binarize(gray: Image.Image) -> Image.Image:
    """Second half of preprocessing: pure black/white using an automatic
    threshold. This is what Tesseract actually reads."""
    arr = np.array(gray)
    threshold = _otsu_threshold(arr)
    binarized = (arr > threshold) * 255
    return Image.fromarray(binarized.astype(np.uint8))


def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """
    Cleans up a scanned/photocopied page before handing it to Tesseract.
    This targets exactly the kind of document that trips OCR up: faded
    photocopies, slightly small text, JPEG artifact noise.

    Settings below were chosen by directly comparing OCR output across
    several variants on a real faded-photocopy test document — sharpening
    was tested and dropped because it measurably hurt accuracy (introduced
    new character confusions like "Dte" -> "Pte").
    """
    return _binarize(_upscale_and_contrast(image))


def extract_text_from_pdf(file_path: str) -> str:
    """
    Returns the full extracted text of the PDF, page by page.
    Uses the embedded text layer where available, OCR (with preprocessing)
    otherwise.
    """
    doc = fitz.open(file_path)
    full_text = []

    for page_number in range(len(doc)):
        page = doc[page_number]
        text = page.get_text().strip()

        if len(text) >= MIN_TEXT_LEN_THRESHOLD:
            # Real text layer — no OCR needed for this page
            full_text.append(text)
        else:
            # Likely a scanned/image page — render, clean up, and OCR it
            pix = page.get_pixmap(dpi=300)
            img_path = Path(file_path).parent / f"_tmp_page_{page_number}.png"
            pix.save(img_path)

            try:
                image = Image.open(img_path)
                cleaned = _preprocess_for_ocr(image)
                ocr_text = pytesseract.image_to_string(cleaned, config=TESSERACT_CONFIG)
                full_text.append(ocr_text.strip())
            finally:
                img_path.unlink(missing_ok=True)  # clean up temp image

    doc.close()
    return "\n\n".join(full_text)


def extract_text_from_image(file_path: str) -> str:
    """
    Runs OCR directly on a standalone image file (png/jpg/tiff), after
    cleaning it up first.
    """
    image = Image.open(file_path)
    cleaned = _preprocess_for_ocr(image)
    return pytesseract.image_to_string(cleaned, config=TESSERACT_CONFIG).strip()


def run_ocr(file_path: str, file_type: str) -> str:
    """
    Entry point used by the API layer. Dispatches based on file type.
    """
    if file_type.lower() == "pdf":
        return extract_text_from_pdf(file_path)
    else:
        return extract_text_from_image(file_path)
