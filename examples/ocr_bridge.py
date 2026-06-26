"""Send each scanned page of a PDF through Tesseract OCR.

Detects scanned pages via `page.is_scanned`, pulls their image bytes via
`get_images()`, and shells out to `tesseract` for OCR. Non-scanned pages
fall through to flashpdf's text extraction.

Requires the `tesseract` binary on PATH (`brew install tesseract`).

Usage:
    python ocr_bridge.py scanned.pdf > output.txt
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import flashpdf


def ocr_image(img_bytes: bytes, ext: str) -> str:
    suffix = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "tif": ".tif",
              "tiff": ".tif"}.get(ext.lower(), ".img")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(img_bytes)
        path = Path(f.name)
    try:
        out = subprocess.run(
            ["tesseract", str(path), "-", "-l", "eng"],
            check=True, capture_output=True, text=True,
        )
        return out.stdout
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf")
    args = ap.parse_args()

    doc = flashpdf.open(args.pdf)
    for i in range(len(doc)):
        page = doc[i]
        if not page.is_scanned:
            sys.stdout.write(page.get_text("text"))
            sys.stdout.write("\n")
            continue
        # For scanned docs, get_images() typically yields one full-page image.
        for img in page.get_images():
            text = ocr_image(img["image"], img.get("ext", "jpeg"))
            sys.stdout.write(text)
        sys.stdout.write(f"\n[--- page {i + 1} OCR'd ---]\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
