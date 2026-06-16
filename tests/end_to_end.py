"""
End-to-end test: verify fastpdf can extract text and images from real PDFs.
"""
import sys
from pathlib import Path

def test_extraction(pdf_path: str) -> bool:
    """Test that fastpdf can extract from a PDF without errors."""
    import fastpdf

    try:
        blocks, images = fastpdf.extract(pdf_path, include_images=True)
    except Exception as e:
        print(f"  FAIL: extraction error: {e}")
        return False

    if not blocks and not images:
        print(f"  WARN: no content extracted (may be image-only or empty PDF)")
        return True  # Not necessarily an error

    # Verify structure
    total_chars = 0
    total_lines = 0
    total_spans = 0

    for block in blocks:
        if "lines" not in block:
            print(f"  FAIL: block missing 'lines' key")
            return False
        for line in block["lines"]:
            total_lines += 1
            if "spans" not in line:
                print(f"  FAIL: line missing 'spans' key")
                return False
            for span in line["spans"]:
                total_spans += 1
                if "text" not in span:
                    print(f"  FAIL: span missing 'text' key")
                    return False
                if "bbox" not in span:
                    print(f"  FAIL: span missing 'bbox' key")
                    return False
                if "font" not in span:
                    print(f"  FAIL: span missing 'font' key")
                    return False
                total_chars += len(span["text"])

    print(f"  OK: {len(blocks)} blocks, {total_lines} lines, {total_spans} spans, {total_chars} chars, {len(images)} images")

    # Verify bboxes are reasonable (non-zero, positive dimensions)
    for block in blocks:
        for line in block["lines"]:
            for span in line["spans"]:
                bbox = span["bbox"]
                if len(bbox) != 4:
                    print(f"  FAIL: bbox should have 4 elements, got {len(bbox)}")
                    return False
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    # Allow zero-size spans (e.g., spaces)
                    if span["text"].strip():
                        print(f"  WARN: zero-size bbox for non-empty text: '{span['text'][:20]}'")

    return True


def run_e2e_tests(test_dir: str):
    """Run end-to-end tests on all PDFs in a directory."""
    test_dir = Path(test_dir)
    pdf_files = sorted(test_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in {test_dir}")
        return False

    print(f"Running end-to-end tests on {len(pdf_files)} PDFs")
    print("=" * 60)

    passed = 0
    failed = 0

    for pdf_path in pdf_files:
        print(f"\nTesting: {pdf_path.name}")
        if test_extraction(str(pdf_path)):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(pdf_files)}")

    return failed == 0


if __name__ == "__main__":
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "test_data"
    success = run_e2e_tests(test_dir)
    sys.exit(0 if success else 1)
