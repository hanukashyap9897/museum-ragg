"""
ICR (handwriting recognition) service using Microsoft's TrOCR model.

Unlike Tesseract (rule/pattern based, built for printed text), TrOCR is a
transformer model trained specifically on handwritten text, so it handles
messy, inconsistent handwriting far better.

Note: the model (~1.3GB) downloads automatically the first time this runs,
then is cached in ~/.cache/huggingface — subsequent runs are fast to load.

Requires: pip install transformers torch pillow
"""

from pathlib import Path
from functools import lru_cache

import numpy as np
from PIL import Image

import fitz  # PyMuPDF, reused here just to rasterize PDF pages to images

MODEL_NAME = "microsoft/trocr-large-handwritten"


def _otsu_threshold(gray: np.ndarray) -> int:
    """
    Computes a black/white cutoff automatically from the image's own
    histogram (Otsu's method), instead of a fixed guess like 200.
    This adapts to different lighting, paper color, and photo exposure —
    important once we're dealing with photographed pages instead of
    clean flatbed scans.
    """
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = gray.size

    sum_total = np.dot(np.arange(256), hist)
    sum_background = 0.0
    weight_background = 0
    max_variance = 0.0
    threshold = 128

    for t in range(256):
        weight_background += hist[t]
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break

        sum_background += t * hist[t]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground

        variance_between = (
            weight_background * weight_foreground *
            (mean_background - mean_foreground) ** 2
        )
        if variance_between > max_variance:
            max_variance = variance_between
            threshold = t

    return threshold


from PIL import ImageOps


def _deskew_image(image: Image.Image, max_angle: float = 15.0, step: float = 0.5) -> Image.Image:
    """
    Estimates the rotation angle of a photographed page and straightens it.
    Reuses _otsu_threshold to get a binary ink mask, tries rotating the mask
    across angles from -max_angle to +max_angle in step increments, and picks
    the angle that maximizes the variance of row-wise ink pixel sums.
    """
    gray = np.array(image.convert("L"))
    thresh = _otsu_threshold(gray)
    ink_mask = gray < thresh

    mask_img = Image.fromarray((ink_mask * 255).astype(np.uint8))

    best_angle = 0.0
    max_var = -1.0

    angles = np.arange(-max_angle, max_angle + step, step)
    for angle in angles:
        rotated_mask = mask_img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=0)
        arr = np.array(rotated_mask)
        row_sums = arr.sum(axis=1)
        var = float(np.var(row_sums))
        if var > max_var:
            max_var = var
            best_angle = float(angle)

    if abs(best_angle) < 0.1:
        return image

    return image.rotate(best_angle, resample=Image.BICUBIC, expand=True, fillcolor="white")


def _split_double_page(image: Image.Image, gutter_search_frac: float = 0.15):

    """
    Detects whether an image is a two-page book spread and, if so, splits
    it into two separate single-page images.

    Only applies to wide images (aspect ratio width > 1.35 * height).
    Single-page cards and letters are returned as-is.
    """
    if image.width < image.height * 1.35:
        return [image]

    gray = np.array(image.convert("L"))
    threshold = _otsu_threshold(gray)
    ink_mask = gray < threshold

    col_ink_counts = ink_mask.sum(axis=0)
    width = image.width

    search_start = int(width * (0.5 - gutter_search_frac))
    search_end = int(width * (0.5 + gutter_search_frac))
    middle_band = col_ink_counts[search_start:search_end]

    if len(middle_band) == 0:
        return [image]

    avg_ink = col_ink_counts.mean()
    min_col_index = int(np.argmin(middle_band)) + search_start
    min_ink = col_ink_counts[min_col_index]

    if avg_ink == 0 or min_ink > avg_ink * 0.3:
        return [image]

    left = image.crop((0, 0, min_col_index, image.height))
    right = image.crop((min_col_index, 0, width, image.height))
    return [left, right]


def _crop_card(image: Image.Image) -> Image.Image:
    """
    Crops out dark background margins from photo scans of paper cards.
    """
    gray = np.array(image.convert("L"))
    bright_mask = gray > 100
    if not np.any(bright_mask):
        return image
    rows = np.where(bright_mask.any(axis=1))[0]
    cols = np.where(bright_mask.any(axis=0))[0]
    if len(rows) > 0 and len(cols) > 0:
        ymin, ymax = rows[0], rows[-1]
        xmin, xmax = cols[0], cols[-1]
        if (ymax - ymin > 80) and (xmax - xmin > 80):
            return image.crop((xmin, ymin, xmax, ymax))
    return image


import cv2


def _detect_ruled_lines(card: Image.Image) -> list[int]:
    """
    Detects horizontal ruled lines on notebook paper using a horizontal
    morphological filter and adaptive thresholding. Returns a sorted list
    of y-coordinates.

    kernel_len is intentionally short (8% of width, not 25%) because
    photographed pages often have visible perspective curvature in the
    ruled lines near the top/edges of the frame — a long, strict kernel
    requiring a straight run across 25% of the image width fails to
    detect those curved lines entirely, silently dropping the first
    1-2 lines of the page from detection.
    """
    gray = np.array(card.convert("L"))
    width = card.width
    kernel_len = max(15, int(width * 0.08))
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, 1))

    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4)
    horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)

    row_sums = horizontal_lines.sum(axis=1) / 255
    min_span_pixels = int(width * 0.08)  # lowered from 0.2 to match shorter kernel
    line_rows = np.where(row_sums > min_span_pixels)[0]

    if len(line_rows) == 0:
        return []

    ruled_ys = []
    curr_group = [line_rows[0]]
    for y in line_rows[1:]:
        if y - curr_group[-1] <= 15:
            curr_group.append(y)
        else:
            ruled_ys.append(int(np.mean(curr_group)))
            curr_group = [y]
    ruled_ys.append(int(np.mean(curr_group)))

    print(f"[DEBUG RULED LINES] card.height={card.height}, found {len(ruled_ys)} lines at y-coords: {ruled_ys}", flush=True)
    if ruled_ys:
        print(f"[DEBUG RULED LINES] Gap above first detected line: {ruled_ys[0]}px (card height {card.height}px)", flush=True)

    return ruled_ys

def _find_content_bounds(card: Image.Image, min_row_ink_fraction: float = 0.03) -> tuple[int, int]:
    """
    Finds the y-range that actually contains handwriting on the page, so we
    can ignore all the blank ruled-paper lines below the last written line
    entirely — rather than trying to filter them out one crop at a time,
    which fails on real photos due to paper grain/texture/shadow noise.
    """
    gray = np.array(card.convert("L"))
    threshold = _otsu_threshold(gray)
    ink_mask = gray < threshold

    row_ink_fraction = ink_mask.sum(axis=1) / card.width
    content_rows = np.where(row_ink_fraction > min_row_ink_fraction)[0]

    if len(content_rows) == 0:
        return (0, card.height)

    top = max(0, int(content_rows[0]) - 20)
    bottom = min(card.height, int(content_rows[-1]) + 20)
    print(f"[DEBUG CONTENT BOUNDS] Real content spans y={top} to y={bottom} (page height {card.height})", flush=True)
    return (top, bottom)


def _segment_lines_by_ruled_paper(card: Image.Image, ruled_ys: list[int]) -> list[Image.Image]:
    """
    Treats each ruled-line y-coordinate as a baseline anchor.
    Crops from (y - spacing * 0.75) up to (y + spacing * 0.25) to cleanly capture
    text body + ascenders sitting above the baseline, and descenders just below it.
    Also handles text sitting above the first ruled line (y0 - spacing * 1.75 to y0 - spacing * 0.75).
    """
    spacings = [ruled_ys[i+1] - ruled_ys[i] for i in range(len(ruled_ys)-1)]
    valid_spacings = [s for s in spacings if s < card.height * 0.3]
    if not valid_spacings:
        return []
    med_spacing = float(np.median(valid_spacings))

    main_ys = [ruled_ys[0]]
    for y in ruled_ys[1:]:
        if abs((y - main_ys[-1]) - med_spacing) <= 0.25 * med_spacing:
            main_ys.append(y)
        elif y - main_ys[-1] > 1.5 * med_spacing:
            break

    bands = []
    # Band for text sitting above the first ruled line (e.g. "Hello Rachel,")
    if main_ys[0] > 0.6 * med_spacing:
        top = int(max(0, main_ys[0] - med_spacing * 1.75))
        bottom = int(min(card.height, main_ys[0] - med_spacing * 0.75))
        if bottom - top > 15:
            bands.append((top, bottom))

    # Baseline-anchored bands for each ruled line
    for y in main_ys:
        top = int(max(0, y - med_spacing * 0.75))
        bottom = int(min(card.height, y + med_spacing * 0.25))
        if bottom - top > 15:
            bands.append((top, bottom))

    crops = []
    for top, bottom in bands:
        crop = card.crop((0, top, card.width, bottom))
        crops.append(ImageOps.expand(crop, border=12, fill="white"))
    return crops

@lru_cache(maxsize=1)
def _get_text_detector():
    from paddleocr import TextDetection
    return TextDetection(enable_mkldnn=False)


def _detect_text_lines_paddle(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """
    Uses PaddleOCR's text detection model to find bounding boxes of each
    line of text on the page. Replaces hand-tuned ruled-line/ink-gap
    heuristics, which don't generalize across different photos, tilts,
    lighting, and paper types.
    """
    import numpy as np

    detector = _get_text_detector()

    img_array = np.array(image.convert("RGB"))
    result = detector.predict(img_array)
    res = next(iter(result))

    boxes = []
    for poly in res.json["res"]["dt_polys"]:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        boxes.append((int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))))

    boxes.sort(key=lambda b: b[1])
    merged = []
    for box in boxes:
        if merged and abs(box[1] - merged[-1][1]) < (box[3] - box[1]) * 0.5:
            x1, y1, x2, y2 = merged[-1]
            merged[-1] = [min(x1, box[0]), min(y1, box[1]), max(x2, box[2]), max(y2, box[3])]
        else:
            merged.append(list(box))

    merged = [tuple(b) for b in merged]
    print(f"[DEBUG PADDLE DETECTION] Found {len(merged)} text line boxes", flush=True)
    return merged



def _segment_lines(image: Image.Image, min_line_height: int = 25, padding: int = 6):
    """
    Splits a page image into individual horizontal text-line crops.
    First tries ruled-line paper detection; if unavailable or inconsistent, falls back to ink-gap segmentation.
    """
    card = _crop_card(image)

    # 1. Try Ruled-Line Paper Detection
    content_top, content_bottom = _find_content_bounds(card)
    ruled_ys = _detect_ruled_lines(card)
    ruled_ys = [y for y in ruled_ys if content_top - 30 <= y <= content_bottom + 30]
    if len(ruled_ys) >= 3:
        ruled_crops = _segment_lines_by_ruled_paper(card, ruled_ys)
        if ruled_crops:
            return ruled_crops

    # 2. Fallback to Ink-Gap Segmentation

    gray = np.array(card.convert("L"))

    paper_bg = float(np.median(gray))
    ink_threshold = min(_otsu_threshold(gray), max(50.0, paper_bg - 25.0))
    ink_mask = gray < ink_threshold

    row_ink_counts = ink_mask.sum(axis=1)
    min_ink_pixels = max(2, int(card.width * 0.003))
    is_text_row = row_ink_counts > min_ink_pixels

    raw_lines = []
    in_line = False
    start = 0
    for y, has_text in enumerate(is_text_row):
        if has_text and not in_line:
            start = y
            in_line = True
        elif not has_text and in_line:
            end = y
            if (end - start) >= min_line_height:
                raw_lines.append((start, end))
            in_line = False
    if in_line:
        end = len(is_text_row)
        if (end - start) >= min_line_height:
            raw_lines.append((start, end))

    if not raw_lines:
        return [ImageOps.expand(card, border=15, fill="white")]

    # Merge line breaks that are closer than 1 pixel to avoid splitting descenders/ascenders
    merged = []
    curr_start, curr_end = raw_lines[0]
    for s, e in raw_lines[1:]:
        if s - curr_end < 1:
            curr_end = e
        else:
            merged.append((curr_start, curr_end))
            curr_start, curr_end = s, e
    merged.append((curr_start, curr_end))



    crops = []
    for s, e in merged:
        top = max(0, s - padding)
        bottom = min(card.height, e + padding)
        crop = card.crop((0, top, card.width, bottom))
        padded_crop = ImageOps.expand(crop, border=12, fill="white")
        crops.append(padded_crop)

    return crops



@lru_cache(maxsize=1)
def _load_model():
    """
    Loads the model + processor once and caches them in memory
    (avoids reloading a ~1.3GB model on every single page/request).
    """
    from transformers import RobertaTokenizer, ViTImageProcessor, VisionEncoderDecoderModel
    try:
        from transformers import TrOCRProcessor
    except ImportError:
        from transformers.models.trocr import TrOCRProcessor

    img_processor = ViTImageProcessor.from_pretrained(MODEL_NAME)
    tokenizer = RobertaTokenizer.from_pretrained(MODEL_NAME)
    processor = TrOCRProcessor(image_processor=img_processor, tokenizer=tokenizer)
    model = VisionEncoderDecoderModel.from_pretrained(MODEL_NAME)
    return processor, model




def _has_ink(crop: Image.Image, min_ink_fraction: float = 0.02, min_width_coverage: float = 0.2) -> bool:
    """
    Checks if a line crop contains sufficient ink pixels and spans enough width
    to avoid running TrOCR on blank lines or stray ink fragments.
    """
    w, h = crop.size
    margin = int(h * 0.15)
    interior = crop.crop((0, margin, w, max(margin + 1, h - margin)))
    gray = np.array(interior.convert("L"))
    threshold = _otsu_threshold(gray)
    ink_mask = gray < threshold

    ink_pixels = ink_mask.sum()
    has_enough_ink = ink_pixels > (interior.width * interior.height * min_ink_fraction)

    col_has_ink = ink_mask.any(axis=0)
    width_coverage = col_has_ink.sum() / interior.width
    has_wide_coverage = width_coverage > min_width_coverage

    return has_enough_ink and has_wide_coverage




def _recognize_image(image: Image.Image) -> str:
    processor, model = _load_model()

    image = image.convert("RGB")
    pixel_values = processor(images=image, return_tensors="pt").pixel_values
    generated_ids = model.generate(pixel_values, max_length=512)
    text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    return text.strip()


def _recognize_page(image: Image.Image) -> str:
    """
    Handles a full page image (or a two-page book spread):
    1. Deskews the image to straighten tilted handwritten text.
    2. Detects and splits double-page spreads into separate page images.
    3. Segments each page into individual lines (how TrOCR is meant to be used).
    4. Saves debug crops to debug_crops/ for verification.
    5. Filters out blank lines and recognizes valid text lines.
    """
    image = _deskew_image(image)
    pages = _split_double_page(image)

    debug_dir = Path("debug_crops")
    debug_dir.mkdir(exist_ok=True)

    page_texts = []
    for page_idx, page_image in enumerate(pages):
        boxes = _detect_text_lines_paddle(page_image)
        padding = 8
        line_crops = []
        for (x1, y1, x2, y2) in boxes:
            top = max(0, y1 - padding)
            bottom = min(page_image.height, y2 + padding)
            line_crops.append(page_image.crop((0, top, page_image.width, bottom)))

        for i, crop in enumerate(line_crops):
            crop.save(debug_dir / f"page_{page_idx}_line_{i:02d}.png")

        if not line_crops:
            page_texts.append(_recognize_image(page_image))
        else:
            recognized_lines = []
            skipped_count = 0
            for crop in line_crops:
                if _has_ink(crop):
                    recognized_lines.append(_recognize_image(crop))
                else:
                    skipped_count += 1
            print(f"[DEBUG BLANK FILTER] Sent {len(recognized_lines)} line crops to TrOCR, skipped {skipped_count} blank crops.", flush=True)
            page_texts.append("\n".join(recognized_lines))

    # If we split into two pages, separate them clearly in the output
    separator = "\n\n--- page split ---\n\n"
    return separator.join(page_texts)




def _pdf_pages_to_images(file_path: str, dpi: int = 300):
    doc = fitz.open(file_path)
    for page_number in range(len(doc)):
        page = doc[page_number]
        pix = page.get_pixmap(dpi=dpi)
        img_path = Path(file_path).parent / f"_tmp_icr_page_{page_number}.png"
        pix.save(img_path)
        yield img_path
    doc.close()


def run_icr(file_path: str, file_type: str) -> str:
    """
    Entry point used by the API layer.
    Returns recognized handwritten text, page by page (if PDF).

    Note: TrOCR works best on a single line or a tightly cropped block of
    text, not a full messy page. For a first pass we feed it the whole page;
    if results are poor, the next improvement is adding line/region
    segmentation before recognition.
    """
    results = []

    if file_type.lower() == "pdf":
        for img_path in _pdf_pages_to_images(file_path):
            try:
                image = Image.open(img_path)
                text = _recognize_page(image)
                results.append(text)
            finally:
                img_path.unlink(missing_ok=True)
    else:
        image = Image.open(file_path)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        results.append(_recognize_page(image))

    return "\n\n".join(results)