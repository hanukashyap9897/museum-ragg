"""
Intelligent Document Processing (IDP) pipeline.

Combines three genuinely-existing capabilities:

1. PPStructureV3 — page layout analysis + table structure recognition +
   text extraction, all in one pass (PPStructureV3 bakes OCR into the
   layout parsing step itself, unlike the old PPStructure API which
   required a separate OCR pass on cropped regions).
2. Anchor-based signature flagging (regex on extracted text) — flags
   where a signature likely sits, WITHOUT attempting to OCR/ICR it,
   since reading an actual pen signature is unreliable and low-value
   (the officer's name is already captured from the printed text right
   next to it).

NOTE ON UNTESTED LIBRARY SURFACE (paddleocr==3.7.0):
PPStructureV3's `res.json["res"]["parsing_res_list"]` block labels are
written against the commonly-documented set:
    {"text", "title", "doc_title", "paragraph_title", "figure_title",
     "list", "header", "table", "image"}
If you hit unexpected blocks landing in "other", run:
    print(res.json["res"]["parsing_res_list"])
on one real page once and adjust TEXT_LIKE_TYPES below to match — flagging
this now since I can't run PaddleOCR in my current environment to verify
it directly against your installed version.
"""

import re
import traceback
import uuid
from functools import lru_cache
from pathlib import Path

import fitz  # PyMuPDF

# Reuse the already-validated date/reference-number extraction rather than
# rewriting the same regex logic twice.
from app.services.metadata_service import _extract_dates, _extract_ref_numbers

# --- Signature anchor detection (same validated logic as signature_service.py) ---

# A standalone printed line that's JUST "(Officer Name)" — the actual
# closing-signature pattern. Deliberately stricter than a loose two-
# capitalized-words search: an early version of this regex matched things
# like "Technical Training" or "Signal Training" from ordinary unit names
# anywhere in a sentence, which would flag a false signature zone on
# nearly every paragraph. Requiring the WHOLE line to be just the
# parenthesized name avoids that.
OFFICER_NAME_LINE = re.compile(r"^\(([A-Z][a-zA-Z\.\s]{2,30})\)$")

RANK_KEYWORDS = ("Lt Col", "Col", "Maj Gen", "Comdt", "GSO-1", "GSO 1", "Senior Instructor", "Brig", "Capt", "Gen")

SIGNATURE_ZONE_HEIGHT_PX = 140

# Block labels PPStructureV3 produces that we treat as "printed text".
# Table is handled separately since its block_content is reconstructed HTML.
# NOTE: verify this set against your installed version — see module docstring.
TEXT_LIKE_TYPES = {"text", "title", "doc_title", "paragraph_title", "figure_title", "list", "header"}


# 200 DPI is enough for scanned correspondence and cuts Paddle inference time
# versus 300 DPI on CPU-only machines.
PDF_RENDER_DPI = 200


def _pdf_to_images(file_path: str, dpi: int = PDF_RENDER_DPI) -> list[Path]:
    """Renders every page of a PDF to a uniquely-named PNG at the given DPI.

    Filenames include a uuid so concurrent/retried jobs on the same
    directory never collide on the same temp file (this previously caused
    a PermissionError when a prior handle on a fixed filename was still
    open during a retry or a hot-reload).
    """
    doc = fitz.open(file_path)
    job_tag = uuid.uuid4().hex[:8]
    image_paths = []
    for page_number in range(len(doc)):
        pix = doc[page_number].get_pixmap(dpi=dpi)
        img_path = Path(file_path).parent / f"_tmp_idp_{job_tag}_page_{page_number}.png"
        pix.save(img_path)
        image_paths.append(img_path)
    doc.close()
    return image_paths


@lru_cache(maxsize=1)
def _get_engines():
    """
    Lazily imports and constructs the PaddleOCR engine. Lazy so that
    importing this module doesn't require paddleocr installed unless this
    pipeline actually runs.
    """
    from paddleocr import PPStructureV3

    layout_engine = PPStructureV3(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        enable_mkldnn=False,  # Paddle 3.x + oneDNN CPU bug: PIR executor can't
                              # convert certain ops' double-array attributes.
                              # See PaddlePaddle/Paddle#77340 and
                              # PaddlePaddle/PaddleOCR#17955/#18162.
        use_seal_recognition=False,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_textline_orientation=False,
        use_table_recognition=True,
    )
    return layout_engine


def _find_signature_zones(full_page_text_blocks: list[dict]) -> list[dict]:
    """
    Scans already-extracted text blocks for a printed "(Officer Name)" line
    immediately followed by a rank line, and proposes a signature zone
    directly above the name. Requires BOTH conditions (not just a loose
    word match) to avoid false positives on ordinary unit names like
    "Technical Training Regiment" elsewhere in the document.

    Does NOT attempt to read the signature itself — just flags where one
    likely is, since actual pen signatures are unreliable to OCR/ICR and
    the officer's identity is already captured from this printed text.
    """
    zones = []

    # Blocks are already sorted top-to-bottom by the caller's later sort,
    # but we need that order NOW to check "the next block down" — so sort
    # a local copy by y-position first.
    ordered = sorted(full_page_text_blocks, key=lambda b: b["bbox"][1])

    for idx, block in enumerate(ordered):
        text = (block.get("text") or "").strip()
        name_match = OFFICER_NAME_LINE.match(text)
        if not name_match:
            continue

        next_text = ordered[idx + 1]["text"] if idx + 1 < len(ordered) else ""
        if not any(rank in next_text for rank in RANK_KEYWORDS):
            continue

        x1, y1, x2, y2 = block["bbox"]
        signature_bbox = [x1, max(0, y1 - SIGNATURE_ZONE_HEIGHT_PX), x2, y1]

        zones.append({
            "type": "signature_box",
            "content": "[Signature Detected Above Officer Name]",
            "bbox": signature_bbox,
            "officer_name": name_match.group(1).strip(),
        })
    return zones


def _process_page(layout_engine, image_path: Path, page_number: int) -> dict:
    """
    Runs the full pipeline on one page image:
    1. PPStructureV3 layout + OCR + table parsing in one call
    2. Table blocks -> HTML content (already reconstructed by PPStructureV3)
    3. Text-like blocks -> printed text (already extracted by PPStructureV3)
    4. Signature anchor scan over the extracted text blocks
    5. Spatial sort (top to bottom) and assembly
    """
    print(f"[IDP] Processing page {page_number}: {image_path.name}", flush=True)
    output = layout_engine.predict(
        input=str(image_path),
        use_table_recognition=True,
        use_table_orientation_classify=True,
    )
    res = next(iter(output))  # one image in -> one result out
    parsing_res_list = res.json["res"]["parsing_res_list"]

    blocks = []

    for item in parsing_res_list:
        label = (item.get("block_label") or "").lower()
        bbox = item.get("block_bbox", [0, 0, 0, 0])
        content = item.get("block_content", "") or ""

        if label == "table":
            blocks.append({
                "category": "table",
                "content": content,
                "bbox": bbox,
            })

        elif label in TEXT_LIKE_TYPES:
            blocks.append({
                "category": "printed_text",
                "content": content,
                "bbox": bbox,
                "text": content,  # kept for signature-anchor scanning below
                "_region_type": label,  # kept internally for the scan filter
            })

        else:
            # figure, image, stamp-like noise, etc. — flagged but not processed
            blocks.append({
                "category": "other",
                "content": None,
                "bbox": bbox,
            })

    # Signature anchor scan runs over the text-like blocks we just extracted
    text_blocks_for_scan = [b for b in blocks if b["category"] == "printed_text"]
    signature_zones = _find_signature_zones(text_blocks_for_scan)
    for zone in signature_zones:
        zone["category"] = "signature"
        zone.pop("type", None)
    blocks.extend(signature_zones)

    # Clean up internal-only keys before returning
    for b in blocks:
        b.pop("text", None)
        b.pop("_region_type", None)

    # Spatial sort: top to bottom by the block's y1 coordinate
    blocks.sort(key=lambda b: b["bbox"][1])

    clean_text = "\n".join(
        b["content"] for b in blocks
        if b["category"] == "printed_text" and b["content"]
    )

    # Metadata extraction (dates, reference numbers) on this page's text —
    # reuses the already-validated patterns from metadata_service.py rather
    # than duplicating that regex logic here.
    dates = _extract_dates(clean_text)
    page_metadata = {
        "dates": dates,
        "reference_numbers": _extract_ref_numbers(clean_text),
    }

    return {
        "page": page_number,
        "blocks": blocks,
        "clean_text": clean_text,
        "metadata": page_metadata,
    }


def _process_pdf_fitz(file_path: str) -> list[dict]:
    doc = fitz.open(file_path)
    pages = []
    try:
        for page_idx, page in enumerate(doc):
            text_blocks_raw = page.get_text("blocks")
            tables = page.find_tables()

            blocks = []
            page_text_lines = []
            table_bboxes = []

            for tab in tables:
                tb_bbox = [round(c, 1) for c in tab.bbox]
                table_bboxes.append(tb_bbox)
                df = tab.extract()
                html_rows = []
                for row in df:
                    cells = [f"<td>{(cell or '').strip()}</td>" for cell in row]
                    html_rows.append(f"<tr>{''.join(cells)}</tr>")
                table_html = f"<table>{''.join(html_rows)}</table>"
                blocks.append({
                    "category": "table",
                    "content": table_html,
                    "bbox": tb_bbox,
                })

            for b in text_blocks_raw:
                x0, y0, x1, y1, text, block_no, block_type = b
                text_str = text.strip()
                if not text_str or block_type != 0:
                    continue
                bbox = [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]
                inside_table = any(
                    x0 >= tb[0] - 2 and y0 >= tb[1] - 2 and x1 <= tb[2] + 2 and y1 <= tb[3] + 2
                    for tb in table_bboxes
                )
                if not inside_table:
                    blocks.append({
                        "category": "printed_text",
                        "content": text_str,
                        "bbox": bbox,
                        "text": text_str,
                    })
                    page_text_lines.append(text_str)

            text_blocks_for_scan = [b for b in blocks if b["category"] == "printed_text"]
            signature_zones = _find_signature_zones(text_blocks_for_scan)
            for zone in signature_zones:
                zone["category"] = "signature"
                zone.pop("type", None)
            blocks.extend(signature_zones)

            for b in blocks:
                b.pop("text", None)

            blocks.sort(key=lambda b: b["bbox"][1])

            clean_text = "\n".join(page_text_lines)
            page_metadata = {
                "dates": _extract_dates(clean_text),
                "reference_numbers": _extract_ref_numbers(clean_text),
            }

            pages.append({
                "page": page_idx + 1,
                "blocks": blocks,
                "clean_text": clean_text,
                "metadata": page_metadata,
            })
    finally:
        doc.close()
    return pages


def run_idp_pipeline(file_path: str, file_type: str, progress_callback=None) -> dict:
    """
    Entry point. Returns a structured result:
      {
        "pages": [ { "page": 1, "blocks": [...], "clean_text": "..." }, ... ],
        "clean_text": "<all pages concatenated>"
      }
    """
    print(f"[IDP] Starting pipeline for {file_path} ({file_type})", flush=True)

    if file_type.lower() == "pdf":
        try:
            fitz_pages = _process_pdf_fitz(file_path)
            full_text = "\n\n".join(p["clean_text"] for p in fitz_pages if p.get("clean_text"))
            if full_text.strip():
                if progress_callback:
                    try:
                        progress_callback(len(fitz_pages), len(fitz_pages))
                    except Exception:
                        pass
                print(f"[IDP FAST] PyMuPDF extracted {len(fitz_pages)} page(s), {len(full_text)} chars in <0.05s", flush=True)
                return {
                    "pages": fitz_pages,
                    "clean_text": full_text,
                }
        except Exception:
            print(f"[IDP FAST FALLBACK] PyMuPDF fast extraction skipped, trying OCR: {traceback.format_exc()}", flush=True)

        image_paths = _pdf_to_images(file_path)
    else:
        image_paths = [Path(file_path)]

    layout_engine = _get_engines()

    total_pages = len(image_paths)
    pages = []
    try:
        for i, img_path in enumerate(image_paths):
            current_page_num = i + 1
            if progress_callback:
                try:
                    progress_callback(current_page_num, total_pages)
                except Exception as p_err:
                    print(f"[IDP PROGRESS CALLBACK ERROR] {p_err}", flush=True)

            try:
                page_result = _process_page(layout_engine, img_path, current_page_num)
                pages.append(page_result)
            except Exception:
                print(f"[IDP ERROR] page={current_page_num}\n{traceback.format_exc()}")
                pages.append({
                    "page": current_page_num,
                    "blocks": [],
                    "clean_text": "",
                    "error": "Failed to process this page — see server logs.",
                })
    finally:
        if file_type.lower() == "pdf":
            for p in image_paths:
                p.unlink(missing_ok=True)

    full_text = "\n\n".join(p["clean_text"] for p in pages if p.get("clean_text"))

    print(f"[IDP] Finished {file_path}: {len(pages)} page(s), {len(full_text)} chars", flush=True)

    return {
        "pages": pages,
        "clean_text": full_text,
    }