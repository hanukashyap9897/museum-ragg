"""
Combined OCR + ICR pipeline for mixed-content pages.

Real documents often have printed body text AND handwritten signatures,
annotations, or "SEEN BY" notes on the SAME page. Neither engine alone
handles this: OCR (Tesseract) garbles handwriting, and ICR (TrOCR) is
built for handwriting, not dense printed paragraphs.

Strategy — fully automatic, no manual region selection required:
1. Run Tesseract as normal, but ask it for per-line CONFIDENCE scores
   (not just text) via image_to_data.
2. Printed text reliably comes back with high confidence. Handwriting
   reliably confuses Tesseract into low confidence or gibberish — that's
   the signal we use to detect "this line is probably handwritten."
3. Automatically crop out just those low-confidence lines (in memory,
   no user interaction) and run them through the existing ICR (TrOCR)
   pipeline instead.
4. Merge: high-confidence lines keep their OCR text, low-confidence
   lines get replaced with the ICR reading, reassembled in top-to-bottom
   reading order.
"""

from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from PIL import Image

from app.services.ocr_service import (
    TESSERACT_CONFIG,
    _upscale_and_contrast,
    _binarize,
)

# Tesseract confidence is 0-100 (or -1 for "no text detected here").
# Below this, a line is treated as "probably not clean printed text" —
# handwriting, a stamp, a signature, or heavy noise — and gets a second
# opinion from ICR.
LOW_CONFIDENCE_THRESHOLD = 45

# Skip ICR re-recognition on lines this short — usually stray punctuation
# or noise, not worth a slow model call.
MIN_LINE_CHARS_FOR_ICR = 2

# Padding (in pixels, on the upscaled image) added around a flagged line
# before cropping, so ICR sees a little breathing room instead of text
# clipped exactly at the edges.
CROP_PADDING = 6


def _group_words_into_lines(tess_data: dict):
    """
    Tesseract's image_to_data returns one row per WORD. This groups words
    back into lines (using Tesseract's own block/paragraph/line numbering)
    and computes each line's combined text, average confidence, and
    bounding box.
    """
    lines = {}

    n = len(tess_data["text"])
    for i in range(n):
        word = tess_data["text"][i].strip()
        conf = int(tess_data["conf"][i])

        if word == "":
            continue

        key = (tess_data["block_num"][i], tess_data["par_num"][i], tess_data["line_num"][i])
        left, top = tess_data["left"][i], tess_data["top"][i]
        width, height = tess_data["width"][i], tess_data["height"][i]

        if key not in lines:
            lines[key] = {
                "words": [],
                "confs": [],
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
            }

        entry = lines[key]
        entry["words"].append(word)
        entry["confs"].append(conf)
        entry["left"] = min(entry["left"], left)
        entry["top"] = min(entry["top"], top)
        entry["right"] = max(entry["right"], left + width)
        entry["bottom"] = max(entry["bottom"], top + height)

    result = []
    for entry in lines.values():
        valid_confs = [c for c in entry["confs"] if c >= 0]
        avg_conf = sum(valid_confs) / len(valid_confs) if valid_confs else -1
        result.append({
            "text": " ".join(entry["words"]),
            "avg_conf": avg_conf,
            "left": entry["left"],
            "top": entry["top"],
            "right": entry["right"],
            "bottom": entry["bottom"],
        })

    # Reading order: top to bottom
    result.sort(key=lambda l: l["top"])
    return result


def _recognize_page_combined(image: Image.Image) -> str:
    """
    Runs the full automatic combined pipeline on a single page image.
    """
    # Lazy import — only pulls in the heavy TrOCR/transformers dependency
    # when this combined pipeline actually runs, not for plain OCR calls.
    from app.services.icr_service import _recognize_image as icr_recognize_image

    enhanced = _upscale_and_contrast(image)  # grayscale, upscaled, contrast-boosted — NOT binarized
    binarized = _binarize(enhanced)          # what Tesseract actually reads

    tess_data = pytesseract.image_to_data(
        binarized, config=TESSERACT_CONFIG, output_type=Output.DICT
    )
    lines = _group_words_into_lines(tess_data)

    final_lines = []
    for line in lines:
        is_low_confidence = line["avg_conf"] < LOW_CONFIDENCE_THRESHOLD
        is_long_enough = len(line["text"]) >= MIN_LINE_CHARS_FOR_ICR

        if is_low_confidence and is_long_enough:
            # Crop this region from the ENHANCED (not binarized) image —
            # TrOCR reads grayscale/contrast crops better than stark
            # pure black-and-white ones.
            box = (
                max(0, line["left"] - CROP_PADDING),
                max(0, line["top"] - CROP_PADDING),
                min(enhanced.width, line["right"] + CROP_PADDING),
                min(enhanced.height, line["bottom"] + CROP_PADDING),
            )
            crop = enhanced.crop(box)
            icr_text = icr_recognize_image(crop)
            # Only replace if ICR actually returned something — otherwise
            # keep the original OCR guess rather than losing the line entirely
            final_lines.append(icr_text if icr_text.strip() else line["text"])
        else:
            final_lines.append(line["text"])

    return "\n".join(final_lines)


def _pdf_pages_to_images(file_path: str, dpi: int = 300):
    doc = fitz.open(file_path)
    for page_number in range(len(doc)):
        page = doc[page_number]
        pix = page.get_pixmap(dpi=dpi)
        img_path = Path(file_path).parent / f"_tmp_combined_page_{page_number}.png"
        pix.save(img_path)
        yield img_path
    doc.close()


def run_combined(file_path: str, file_type: str) -> str:
    """
    Entry point used by the API layer. Automatically OCRs printed text
    and ICRs handwritten regions on the same page(s), merging into one
    final text — no manual region selection needed.
    """
    results = []

    if file_type.lower() == "pdf":
        for img_path in _pdf_pages_to_images(file_path):
            try:
                image = Image.open(img_path)
                results.append(_recognize_page_combined(image))
            finally:
                img_path.unlink(missing_ok=True)
    else:
        image = Image.open(file_path)
        results.append(_recognize_page_combined(image))

    return "\n\n".join(results)
