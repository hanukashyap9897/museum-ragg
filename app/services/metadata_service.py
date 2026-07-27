"""
Metadata extraction service.

Rule-based (regex + pattern matching) approach — no ML model, no new
heavy installs. Works directly on the OCR/ICR text already stored on a
Document row.

This is tuned first for military correspondence style documents (like
your training-conference memos), since that's your primary source
material, but the date/keyword extraction generalizes to most documents.
"""

import re
from collections import Counter

# --- Patterns ---

# Matches dates like "04 Apr 26", "04 Apr 2026", "dt 04 Apr 26", "20 Jan 2026"
DATE_PATTERN = re.compile(
    r"\b(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{2,4})\b",
    re.IGNORECASE,
)

# Matches military reference/file numbers like "1735010L/00018/G/T-1/Trg Conf/2025"
# or "04123/SIGS 1 (SD)" — alphanumeric segments joined by slashes
REF_NUMBER_PATTERN = re.compile(
    r"\b[A-Z0-9]{3,}(?:/[A-Z0-9()\- ]{1,20}){1,6}\b"
)

# Matches "(Officer Name) Rank" signature blocks, e.g. "(Bitan Chaki)\nLt Col"
OFFICER_PATTERN = re.compile(
    r"\(([A-Z][a-zA-Z\.\s]{2,40})\)\s*\n?\s*"
    r"(Lt Col|Col|Maj Gen|Brig|Major|Capt|Lt|Gen|Sub Maj|Hav|Sep)",
)

# Matches common unit/regiment/HQ naming patterns
UNIT_PATTERN = re.compile(
    r"\b(\d+\s+(?:Technical Training Regiment|Signal Training Centre|TTR|MTR|CTTB)"
    r"|HQ\s+\d+\s+[A-Za-z ]+"
    r"|HQ\s+[A-Z][A-Za-z& ]{3,40})\b"
)

# Words to ignore when extracting keywords — common military/admin boilerplate
STOPWORDS = {
    "the", "and", "for", "pl", "info", "action", "necessary", "this", "with",
    "from", "your", "our", "are", "is", "was", "be", "to", "of", "in", "on",
    "at", "by", "as", "or", "an", "a", "it", "that", "which", "will", "wef",
    "ref", "dt", "no", "hq", "sig", "sigs", "copy", "encls", "internal",
}


def _extract_dates(text: str) -> list[str]:
    matches = DATE_PATTERN.findall(text)
    # Normalize to "DD Mon YYYY"-ish strings, dedupe while preserving order
    seen = []
    for day, mon, year in matches:
        year_norm = year if len(year) == 4 else f"20{year}"
        date_str = f"{day} {mon.title()} {year_norm}"
        if date_str not in seen:
            seen.append(date_str)
    return seen


def _extract_years(dates: list[str]) -> list[str]:
    years = set()
    for d in dates:
        m = re.search(r"\d{4}", d)
        if m:
            years.add(m.group())
    return sorted(years)


def _extract_ref_numbers(text: str) -> list[str]:
    matches = REF_NUMBER_PATTERN.findall(text)
    # Filter out short/low-signal matches — a real reference number has a
    # slash AND at least one digit (excludes routing labels like "ASIGMA/ZIMBRA")
    return list(dict.fromkeys(
        m.strip() for m in matches
        if "/" in m and len(m) > 8 and any(c.isdigit() for c in m)
    ))[:15]


def _extract_officers(text: str) -> list[dict]:
    results = []
    for name, rank in OFFICER_PATTERN.findall(text):
        name = name.strip()
        entry = {"name": name, "rank": rank}
        if entry not in results:
            results.append(entry)
    return results


def _extract_units(text: str) -> list[str]:
    matches = UNIT_PATTERN.findall(text)
    cleaned = [m.strip() for m in matches if len(m.strip()) > 3]
    return list(dict.fromkeys(cleaned))[:15]


def _extract_keywords(text: str, top_n: int = 15) -> list[str]:
    words = re.findall(r"[A-Za-z]{4,}", text.lower())
    words = [w for w in words if w not in STOPWORDS]
    counts = Counter(words)
    return [word for word, _ in counts.most_common(top_n)]


def _extract_subject(text: str) -> str | None:
    """
    Looks for a short, ALL-CAPS-ish line early in the document — military
    memos consistently put the subject line in caps on its own line
    (e.g. 'SIGS QRTLY TRG CONF'). Skips routing/letterhead lines like
    'BY ASIGMA/ZIMBRA' or lines containing reference numbers.
    """
    skip_prefixes = ("BY ", "THROUGH ", "TELE", "FROM", "TO ", "INFO")
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if not (5 <= len(stripped) <= 60 and stripped == stripped.upper()):
            continue
        if not any(c.isalpha() for c in stripped):
            continue
        if stripped in {"LIST A", "RESTRICTED", "PRIORITY"}:
            continue
        if stripped.startswith(skip_prefixes):
            continue
        if "/" in stripped or any(c.isdigit() for c in stripped):
            continue
        return stripped
    return None


def extract_metadata(text: str) -> dict:
    """
    Main entry point. Takes raw OCR/ICR text and returns a structured
    metadata dict matching the fields your architecture calls for:
    year, keywords, plus officer/unit/date/reference details.
    """
    if not text or not text.strip():
        return {
            "dates": [], "years": [], "reference_numbers": [],
            "officers": [], "units": [], "keywords": [], "subject": None,
        }

    dates = _extract_dates(text)

    return {
        "dates": dates,
        "years": _extract_years(dates),
        "reference_numbers": _extract_ref_numbers(text),
        "officers": _extract_officers(text),
        "units": _extract_units(text),
        "keywords": _extract_keywords(text),
        "subject": _extract_subject(text),
    }
