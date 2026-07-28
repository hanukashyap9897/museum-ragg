"""Quick end-to-end smoke test: upload -> IDP start -> poll result."""
import json
import sys
import time
import uuid
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
API = os.getenv("API_URL", "https://museum-ai-2-0-1-rag.onrender.com")
TEST_FILE = ROOT / "test_page_standalone.png"
MAX_POLLS = 600
POLL_INTERVAL = 2


def upload_file(path: Path) -> str:
    boundary = uuid.uuid4().hex
    data = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(f"{API}/upload/document", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read())
    return payload["id"]


def start_idp(doc_id: str) -> dict:
    req = urllib.request.Request(f"{API}/idp/start/{doc_id}", method="POST", data=b"")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def poll_result(doc_id: str) -> dict:
    with urllib.request.urlopen(f"{API}/idp/result/{doc_id}") as resp:
        return json.loads(resp.read())


def main() -> int:
    if not TEST_FILE.exists():
        print(f"Missing test file: {TEST_FILE}")
        return 1

    doc_id = upload_file(TEST_FILE)
    print(f"upload ok: {doc_id}", flush=True)

    start = start_idp(doc_id)
    print(f"start ok: {start}", flush=True)

    for i in range(MAX_POLLS):
        result = poll_result(doc_id)
        status = result.get("status")
        print(f"poll {i}: {status}", flush=True)

        if status in ("completed", "failed"):
            pages = (result.get("result") or {}).get("pages") or []
            print(f"pages: {len(pages)}")
            if pages:
                page = pages[0]
                print(f"page1 clean_text len: {len(page.get('clean_text', ''))}")
                print(f"page1 blocks: {len(page.get('blocks', []))}")
                if page.get("blocks"):
                    print(f"first block keys: {list(page['blocks'][0].keys())}")
            if status == "failed":
                print(f"error: {result.get('error')}")
                return 1
            return 0

        time.sleep(POLL_INTERVAL)

    print("TIMEOUT")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
