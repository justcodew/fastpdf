#!/bin/bash
# Memory leak check for fastpdf using valgrind (Linux) or leaks (macOS)
# Usage: ./scripts/check_memory.sh [pdf_path]

set -e

PDF_PATH="${1:-test_data/2604.11578v1.pdf}"

echo "Memory check for fastpdf"
echo "PDF: $PDF_PATH"
echo ""

# Build test binary with debug symbols
cargo build --release 2>/dev/null

# Create a simple test binary that exercises the extraction
TEST_BINARY="target/release/fastpdf_memtest"

cat > /tmp/fastpdf_memtest.rs << 'EOF'
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    let path = args.get(1).map(|s| s.as_str()).unwrap_or("test.pdf");

    let options = fastpdf_core::ExtractOptions {
        page_parallel: false,
        file_parallel: false,
        include_images: true,
        gpu: false,
        batch_size: 0,
    };

    // Run extraction multiple times to detect leaks
    for i in 0..5 {
        match fastpdf_core::extract(path, &options) {
            Ok(result) => {
                let total_chars: usize = result.pages.iter()
                    .map(|p| p.blocks.iter()
                        .map(|b| b.lines.iter()
                            .map(|l| l.spans.iter()
                                .map(|s| s.text.len())
                                .sum::<usize>())
                            .sum::<usize>())
                        .sum::<usize>())
                    .sum();
                let total_images: usize = result.pages.iter().map(|p| p.images.len()).sum();
                eprintln!("Run {}: {} chars, {} images", i, total_chars, total_images);
            }
            Err(e) => {
                eprintln!("Run {}: Error: {}", i, e);
            }
        }
    }
    eprintln!("All runs completed.");
}
EOF

# Build the test binary
echo "Building test binary..."
cargo build --release --example memtest 2>/dev/null || {
    echo "Note: Create examples/memtest.rs for proper memory testing"
    echo "Or use: cargo test --release with valgrind/leaks"
}

# Detect platform and run appropriate tool
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Running macOS leaks tool..."
    if [ -f "$TEST_BINARY" ]; then
        leaks --atExit -- "$TEST_BINARY" "$PDF_PATH" 2>&1 | head -50
    else
        echo "Running leaks on test suite..."
        MallocStackLogging=1 cargo test --release 2>/dev/null
        leaks fastpdf_core 2>&1 | head -50 || echo "No leaks found or leaks tool unavailable"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Running valgrind..."
    if command -v valgrind &> /dev/null; then
        if [ -f "$TEST_BINARY" ]; then
            valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes \
                "$TEST_BINARY" "$PDF_PATH" 2>&1 | tail -30
        else
            echo "Running valgrind on test suite..."
            cargo test --release 2>/dev/null
            valgrind --leak-check=full target/release/deps/fastpdf_core-* 2>&1 | tail -30
        fi
    else
        echo "valgrind not found. Install with: sudo apt install valgrind"
    fi
else
    echo "Unsupported platform: $OSTYPE"
    echo "Use valgrind (Linux) or leaks (macOS) manually"
fi
