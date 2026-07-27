"""
Anchor-based signature/handwriting detection for structured military memos.

Why this exists: the earlier confidence-based approach (flag whatever
Tesseract is unsure about, send it to ICR) failed badly — it flagged
short printed labels and table borders just as often as real handwriting,
and TrOCR hallucinates fluent-sounding nonsense on anything that isn't
actual handwriting.

This takes a different, more reliable approach for THIS document type:
these memos have a very consistent closing structure —

    [ handwritten signature ]
    (Officer Name)          <- printed, matches OFFICER_ANCHOR below
    Lt Col                  <- printed rank, confirms this is a real anchor

We already reliably OCR the printed "(Name)" line — that's not what needs
ICR. What's useful to extract via ICR is the handwritten region ABOVE that
anchor. We crop that specific, predictable zone rather than scanning the
whole page for "low confidence."

Safety check: before calling the (slow) ICR model, measure how much actual
ink is in the cropped zone. If it's essentially blank — which can happen on
duplicate/office copies that use a typed "Sd/-" placeholder instead of a
live ink signature — we report that plainly instead of forcing a guess.
"""

import re
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytesseract
from pytesseract import Output
from PIL import Image

from app.services.ocr_service import TESSERACT_CONFIG, _upscale_and_contrast, _otsu_threshold

# Matches a printed line that's just "(Officer Name)" on its own —
# the standard closing-signature pattern in these memos.
OFFICER_ANCHOR = re.compile(r"^\(([A-Z][a-zA-Z\.\s]{2,30})\)$")

# The line immediately following the anchor should look like a rank —
# this confirms we found a real signature block, not a coincidental
# parenthetical elsewhere in the text.
RANK_KEYWORDS = ("Lt Col", "Col", "Maj Gen", "Brig", "Major", "Capt", "Gen", "GSO")

# How many "anchor line heights" tall the signature crop zone should be,
# above the printed name line.
SIGNATURE_ZONE_HEIGHT_MULTIPLIER = 4

# Minimum fraction of dark pixels in the crop to consider it "has real
# content" rather than blank paper — below this, skip ICR and report
# no signature found rather than force a hallucinated guess.
MIN_INK_FRACTION = 0.01


def _group_lines(tess_data: dict):
    lines = {}
    n = len(tess_data["text"])
    for i in range(n):
        word = tess_data["text"][i].strip()
        if word == "":
            continue
        key = (tess_data["block_num"][i], tess_data["par_num"][i], tess_data["line_num"][i])
        left, top, w, h = (
            tess_data["left"][i], tess_data["top"][i],
            tess_data["width"][i], tess_data["height"][i],
        )
        if key not in lines:
            lines[key] = {"words": [], "left": left, "top": top, "right": left + w, "bottom": top + h}
        entry = lines[key]
        entry["words"].append(word)
        entry["left"] = min(entry["left"], left)
        entry["top"] = min(entry["top"], top)
        entry["right"] = max(entry["right"], left + w)
        entry["bottom"] = max(entry["bottom"], top + h)

    result = [{"text": " ".join(e["words"]), **e} for e in lines.values()]
    result.sort(key=lambda l: l["top"])
    return result


def _detect_signature_zones(image: Image.Image):
    """
    Finds officer-name anchors on a page and returns the crop coordinates
    for the signature zone above each one, in the SAME coordinate space
    as the enhanced (non-binarized) image — ready to crop directly.
    Also returns the page-level ink threshold, so later ink-density checks
    on small crops use a consistent, reliable reference point instead of
    recomputing Otsu on a tiny, mostly-uniform region (which produces
    unreliable results — Otsu always finds SOME split point even when
    there's no real content to split).
    """
    from app.services.ocr_service import _binarize

    enhanced = _upscale_and_contrast(image)
    binarized = _binarize(enhanced)
    page_threshold = _otsu_threshold(np.array(enhanced))

    tess_data = pytesseract.image_to_data(binarized, config=TESSERACT_CONFIG, output_type=Output.DICT)
    lines = _group_lines(tess_data)

    zones = []
    for idx, line in enumerate(lines):
        match = OFFICER_ANCHOR.match(line["text"].strip())
        if not match:
            continue

        next_line_text = lines[idx + 1]["text"] if idx + 1 < len(lines) else ""
        if not any(rank in next_line_text for rank in RANK_KEYWORDS):
            continue

        line_height = line["bottom"] - line["top"]
        zone_height = line_height * SIGNATURE_ZONE_HEIGHT_MULTIPLIER
        box = (
            line["left"],
            max(0, line["top"] - zone_height),
            line["right"],
            line["top"],
        )
        zones.append({
            "officer_name": match.group(1).strip(),
            "crop_box": box,
        })

    return enhanced, zones, page_threshold


def detect_and_recognize_signatures(file_path: str, file_type: str) -> list[dict]:
    """
    Entry point. Returns a list of detected signature zones per page, e.g.:
      [{"page": 1, "officer_name": "Bitan Chaki",
        "signature_found": True, "signature_text": "..."}]

    Does NOT touch the document's main ocr_text — this is an additive,
    separate result so it can't corrupt the already-working OCR output.
    """
    from app.services.icr_service import _recognize_image as icr_recognize_image

    results = []

    if file_type.lower() == "pdf":
        doc = fitz.open(file_path)
        pages = []
        for page_number in range(len(doc)):
            pix = doc[page_number].get_pixmap(dpi=300)
            img_path = Path(file_path).parent / f"_tmp_sig_page_{page_number}.png"
            pix.save(img_path)
            pages.append((page_number + 1, img_path))
        doc.close()
    else:
        pages = [(1, Path(file_path))]

    for page_num, img_path in pages:
        try:
            image = Image.open(img_path)
            enhanced, zones, page_threshold = _detect_signature_zones(image)

            for zone in zones:
                crop = enhanced.crop(tuple(int(c) for c in zone["crop_box"]))
                arr = np.array(crop)

                if arr.size == 0:
                    continue

                ink_fraction = (arr < page_threshold).sum() / arr.size

                if ink_fraction < MIN_INK_FRACTION:
                    results.append({
                        "page": page_num,
                        "officer_name": zone["officer_name"],
                        "signature_found": False,
                        "signature_text": None,
                    })
                else:
                    icr_text = icr_recognize_image(crop)
                    results.append({
                        "page": page_num,
                        "officer_name": zone["officer_name"],
                        "signature_found": True,
                        "signature_text": icr_text.strip() if icr_text.strip() else None,
                    })
        finally:
            if file_type.lower() == "pdf":
                img_path.unlink(missing_ok=True)

    return results
