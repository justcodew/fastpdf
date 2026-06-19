#!/bin/bash
# Download sample PDFs for testing flashpdf
# Covers: plain text, mixed content, scanned, tables, CJK, damaged

set -e

TEST_DIR="test_data"
mkdir -p "$TEST_DIR"

echo "Collecting test PDFs into $TEST_DIR/"
echo ""

# Function to download if not exists
download() {
    local url="$1"
    local filename="$2"
    if [ ! -f "$TEST_DIR/$filename" ]; then
        echo "Downloading: $filename"
        curl -sL -o "$TEST_DIR/$filename" "$url" || {
            echo "  Failed to download $filename"
            rm -f "$TEST_DIR/$filename"
        }
    else
        echo "Already exists: $filename"
    fi
}

# Plain text papers (arxiv)
download "https://arxiv.org/pdf/2604.11578v1" "arxiv_2604.11578.pdf"
download "https://arxiv.org/pdf/2301.00234v1" "arxiv_2301.00234.pdf"
download "https://arxiv.org/pdf/2303.08774v4" "arxiv_2303.08774.pdf"

# Mixed content (from public domain sources)
download "https://www.w3.org/WAI/WCAG21/Techniques/pdf/img/table-word.pdf" "table_sample.pdf"
download "https://www.africau.edu/images/default/sample.pdf" "simple_sample.pdf"

echo ""
echo "Test PDF collection complete."
echo "Files in $TEST_DIR/:"
ls -lh "$TEST_DIR/"*.pdf 2>/dev/null || echo "No PDFs found"
echo ""
echo "NOTE: For comprehensive testing, manually add PDFs covering:"
echo "  - Scanned documents (image-only PDFs)"
echo "  - CJK (Chinese/Japanese/Korean) documents"
echo "  - Corrupted/damaged PDFs (for recovery testing)"
echo "  - Forms and interactive PDFs"
echo "  - Large documents (100+ pages)"
