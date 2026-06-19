#!/bin/bash
# Generate flamegraph for flashpdf extraction
# Usage: ./scripts/flamegraph.sh [pdf_path]
#
# Prerequisites:
#   cargo install flamegraph
#   # On macOS: instruments -s requires Xcode CLI tools
#   # On Linux: perf must be available

set -e

PDF_PATH="${1:-test_data/2604.11578v1.pdf}"
OUTPUT_DIR="target/flamegraph"
mkdir -p "$OUTPUT_DIR"

echo "Generating flamegraph for: $PDF_PATH"
echo "Output directory: $OUTPUT_DIR"

# Run criterion benchmark with profiling support
cargo bench --bench extraction -- --profile-time 5

# Generate flamegraph using cargo-flamegraph
if command -v flamegraph &> /dev/null; then
    echo "Running flamegraph..."
    CARGO_PROFILE_BENCH_DEBUG=true cargo flamegraph \
        --bench extraction \
        -- --bench "full_extract_single_page" \
        --profile-time 10 \
        -o "$OUTPUT_DIR/flashpdf_flamegraph.svg"
    echo "Flamegraph saved to: $OUTPUT_DIR/flashpdf_flamegraph.svg"
else
    echo "flamegraph not found. Install with: cargo install flamegraph"
    echo "Alternatively, use criterion's built-in profiling:"
    echo "  cargo bench --bench extraction -- --profile-time 10"
fi
