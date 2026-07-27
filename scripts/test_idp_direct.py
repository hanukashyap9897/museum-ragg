"""Direct IDP pipeline smoke test (no HTTP server required)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.idp_pipeline import run_idp_pipeline

TEST_FILE = ROOT / "test_page_standalone.png"


def main() -> int:
    if not TEST_FILE.exists():
        print(f"Missing test file: {TEST_FILE}")
        return 1

    print(f"Running IDP on {TEST_FILE.name}...", flush=True)
    result = run_idp_pipeline(str(TEST_FILE), "png")
    pages = result.get("pages") or []

    print(f"pages: {len(pages)}", flush=True)
    print(f"clean_text len: {len(result.get('clean_text', ''))}", flush=True)
    if pages:
        print(f"blocks on page 1: {len(pages[0].get('blocks', []))}", flush=True)
        if pages[0].get("error"):
            print(f"page error: {pages[0]['error']}", flush=True)
            return 1

    if not result.get("clean_text") and not pages[0].get("blocks"):
        print("No content extracted", flush=True)
        return 1

    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
