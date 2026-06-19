"""
PyMuPDF comparison test: extract text from PDFs using both flashpdf and PyMuPDF,
then compare block/line/span counts, bbox accuracy, and text consistency.
"""
import json
import os
import sys
import time
from pathlib import Path

def extract_with_pymupdf(pdf_path: str) -> dict:
    """Extract using PyMuPDF (fitz)."""
    import fitz

    doc = fitz.open(pdf_path)
    pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        images = []

        for img in page.get_images(full=True):
            xref = img[0]
            images.append({
                "xref": xref,
                "width": img[2],
                "height": img[3],
            })

        pages.append({
            "blocks": blocks,
            "images": images,
        })

    doc.close()
    return {"pages": pages}


def extract_with_flashpdf(pdf_path: str) -> dict:
    """Extract using flashpdf."""
    import flashpdf

    blocks, images = flashpdf.extract(pdf_path, include_images=True)
    return {
        "pages": [{
            "blocks": blocks,
            "images": images,
        }]
    }


def count_elements(result: dict) -> dict:
    """Count blocks, lines, spans, chars in extraction result."""
    stats = {"blocks": 0, "lines": 0, "spans": 0, "chars": 0, "images": 0}

    for page in result["pages"]:
        for block in page["blocks"]:
            stats["blocks"] += 1
            if "lines" in block:
                for line in block["lines"]:
                    stats["lines"] += 1
                    if "spans" in line:
                        for span in line["spans"]:
                            stats["spans"] += 1
                            stats["chars"] += len(span.get("text", ""))
            elif "lines" in block:
                # PyMuPDF format
                for line in block["lines"]:
                    stats["lines"] += 1
                    for span in line["spans"]:
                        stats["spans"] += 1
                        stats["chars"] += len(span.get("text", ""))
        stats["images"] += len(page.get("images", []))

    return stats


def extract_text(result: dict) -> str:
    """Extract all text from result."""
    texts = []
    for page in result["pages"]:
        for block in page["blocks"]:
            if "lines" in block:
                for line in block["lines"]:
                    if "spans" in line:
                        for span in line["spans"]:
                            texts.append(span.get("text", ""))
    return "\n".join(texts)


def compare_results(pymupdf_result: dict, flashpdf_result: dict, pdf_name: str) -> dict:
    """Compare extraction results from both engines."""
    pymupdf_stats = count_elements(pymupdf_result)
    flashpdf_stats = count_elements(flashpdf_result)

    pymupdf_text = extract_text(pymupdf_result)
    flashpdf_text = extract_text(flashpdf_result)

    # Calculate differences
    block_diff = abs(pymupdf_stats["blocks"] - flashpdf_stats["blocks"])
    line_diff = abs(pymupdf_stats["lines"] - flashpdf_stats["lines"])
    span_diff = abs(pymupdf_stats["spans"] - flashpdf_stats["spans"])
    char_diff = abs(pymupdf_stats["chars"] - flashpdf_stats["chars"])

    block_pct = (block_diff / max(pymupdf_stats["blocks"], 1)) * 100
    line_pct = (line_diff / max(pymupdf_stats["lines"], 1)) * 100
    span_pct = (span_diff / max(pymupdf_stats["spans"], 1)) * 100

    # Text similarity using SequenceMatcher (handles insertions/deletions)
    import difflib
    pymupdf_clean = pymupdf_text.replace(" ", "").replace("\n", "")
    flashpdf_clean = flashpdf_text.replace(" ", "").replace("\n", "")
    matcher = difflib.SequenceMatcher(None, pymupdf_clean, flashpdf_clean)
    text_similarity = matcher.ratio() * 100

    # Also compute word-level overlap
    pymupdf_words = set(pymupdf_text.lower().split())
    flashpdf_words = set(flashpdf_text.lower().split())
    if pymupdf_words:
        word_overlap = len(pymupdf_words & flashpdf_words) / len(pymupdf_words) * 100
    else:
        word_overlap = 0.0

    return {
        "pdf": pdf_name,
        "pymupdf": pymupdf_stats,
        "flashpdf": flashpdf_stats,
        "differences": {
            "block_count_pct": round(block_pct, 2),
            "line_count_pct": round(line_pct, 2),
            "span_count_pct": round(span_pct, 2),
            "text_similarity_pct": round(text_similarity, 2),
            "word_overlap_pct": round(word_overlap, 2),
        }
    }


def run_comparison(test_dir: str, output_file: str = None):
    """Run comparison on all PDFs in a directory."""
    test_dir = Path(test_dir)
    pdf_files = sorted(test_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in {test_dir}")
        return

    print(f"Found {len(pdf_files)} PDF files")
    print("=" * 60)

    results = []
    total_pymupdf_time = 0
    total_flashpdf_time = 0

    for pdf_path in pdf_files:
        pdf_name = pdf_path.name
        print(f"\nTesting: {pdf_name}")

        # PyMuPDF extraction
        try:
            start = time.perf_counter()
            pymupdf_result = extract_with_pymupdf(str(pdf_path))
            pymupdf_time = time.perf_counter() - start
            total_pymupdf_time += pymupdf_time
            print(f"  PyMuPDF: {pymupdf_time:.3f}s")
        except Exception as e:
            print(f"  PyMuPDF error: {e}")
            continue

        # flashpdf extraction
        try:
            start = time.perf_counter()
            flashpdf_result = extract_with_flashpdf(str(pdf_path))
            flashpdf_time = time.perf_counter() - start
            total_flashpdf_time += flashpdf_time
            print(f"  flashpdf: {flashpdf_time:.3f}s")
        except Exception as e:
            print(f"  flashpdf error: {e}")
            continue

        # Compare
        comparison = compare_results(pymupdf_result, flashpdf_result, pdf_name)
        comparison["timing"] = {
            "pymupdf_sec": round(pymupdf_time, 4),
            "flashpdf_sec": round(flashpdf_time, 4),
            "speedup": round(pymupdf_time / max(flashpdf_time, 0.0001), 2),
        }
        results.append(comparison)

        d = comparison["differences"]
        print(f"  Block diff:   {d['block_count_pct']:.1f}%")
        print(f"  Line diff:    {d['line_count_pct']:.1f}%")
        print(f"  Span diff:    {d['span_count_pct']:.1f}%")
        print(f"  Text sim:     {d['text_similarity_pct']:.1f}%")
        print(f"  Word overlap: {d['word_overlap_pct']:.1f}%")

    # Summary
    if results:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        avg_block = sum(r["differences"]["block_count_pct"] for r in results) / len(results)
        avg_line = sum(r["differences"]["line_count_pct"] for r in results) / len(results)
        avg_span = sum(r["differences"]["span_count_pct"] for r in results) / len(results)
        avg_text = sum(r["differences"]["text_similarity_pct"] for r in results) / len(results)
        avg_word = sum(r["differences"]["word_overlap_pct"] for r in results) / len(results)

        print(f"PDFs tested:         {len(results)}")
        print(f"Avg block diff:      {avg_block:.1f}%")
        print(f"Avg line diff:       {avg_line:.1f}%")
        print(f"Avg span diff:       {avg_span:.1f}%")
        print(f"Avg text similarity: {avg_text:.1f}%")
        print(f"Avg word overlap:    {avg_word:.1f}%")
        print(f"Total PyMuPDF time: {total_pymupdf_time:.3f}s")
        print(f"Total flashpdf time: {total_flashpdf_time:.3f}s")
        if total_flashpdf_time > 0:
            print(f"Overall speedup:    {total_pymupdf_time / total_flashpdf_time:.2f}x")

        # Save results
        if output_file:
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "test_data"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "comparison_results.json"
    run_comparison(test_dir, output_file)
