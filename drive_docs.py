"""
Fetches the sales enablement docs (playbook, ICP, battlecards, etc.) from the
shared Google Drive folder and caches them locally as markdown.

The folder is shared as "anyone with the link can view", so a plain Drive API
key is enough — no OAuth or service account needed.

Run directly to (re)populate data/enablement/:
    python drive_docs.py
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

DRIVE_API_KEY = os.getenv("GOOGLE_DRIVE_API_KEY")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
ENABLEMENT_DIR = Path(__file__).resolve().parent / "data" / "enablement"


def list_folder_files() -> list[dict]:
    resp = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        params={
            "q": f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            "key": DRIVE_API_KEY,
            "fields": "files(id,name,mimeType)",
            "pageSize": 100,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("files", [])


def download_file(file_id: str, mime_type: str) -> str:
    if mime_type == "application/vnd.google-apps.document":
        # Native Google Doc — export as plain text.
        resp = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
            params={"mimeType": "text/plain", "key": DRIVE_API_KEY},
            timeout=15,
        )
    else:
        # Already a flat file (markdown, txt, etc.) — download directly.
        resp = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"alt": "media", "key": DRIVE_API_KEY},
            timeout=15,
        )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def sync_enablement_docs() -> list[str]:
    """Downloads every file in the Drive folder into data/enablement/. Returns filenames written."""
    ENABLEMENT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for f in list_folder_files():
        content = download_file(f["id"], f["mimeType"])
        name = f["name"] if f["name"].endswith((".md", ".txt")) else f["name"] + ".md"
        out_path = ENABLEMENT_DIR / name
        out_path.write_text(content, encoding="utf-8")
        written.append(name)
    return written


if __name__ == "__main__":
    files = sync_enablement_docs()
    print(f"Synced {len(files)} docs to {ENABLEMENT_DIR}:")
    for name in sorted(files):
        print(f"  - {name}")
