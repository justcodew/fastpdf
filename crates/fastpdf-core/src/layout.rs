/// Layout analysis: cluster chars → spans → lines → blocks.
///
/// Uses geometric proximity and font/size/color matching to group characters
/// into semantically meaningful text structures compatible with PyMuPDF output.
use crate::parser::content_stream::{CharInfo, TextBlock, TextLine, TextSpan};
use smallvec::SmallVec;

// ─── Layout parameters (tunable) ───

/// Maximum horizontal gap between chars in the same span (as fraction of font size).
const SPAN_GAP_FACTOR: f64 = 0.3;
/// Maximum vertical distance between spans in the same line (as fraction of font size).
const LINE_VERT_FACTOR: f64 = 0.5;
/// Minimum vertical gap between lines to start a new block (as fraction of font size).
const BLOCK_GAP_FACTOR: f64 = 1.5;

/// Cluster extracted characters into spans, lines, and blocks.
///
/// Input: flat list of CharInfo from content stream scanning.
/// Output: hierarchical TextBlock → TextLine → TextSpan structure.
pub fn cluster_chars(chars: &[CharInfo], font: &str, font_size: f64, color: u32) -> Vec<TextBlock> {
    if chars.is_empty() {
        return Vec::new();
    }

    // Step 1: Group chars into spans (same font, geometrically adjacent)
    let spans = build_spans(chars, font, font_size, color);

    // Step 2: Group spans into lines (vertically aligned)
    let lines = build_lines(spans, font_size);

    // Step 3: Group lines into blocks (large vertical gaps)
    build_blocks(lines, font_size)
}

/// Build spans from consecutive characters with similar position.
fn build_spans(chars: &[CharInfo], font: &str, font_size: f64, color: u32) -> Vec<TextSpan> {
    if chars.is_empty() {
        return Vec::new();
    }

    let mut spans = Vec::new();
    let mut current_chars: SmallVec<[CharInfo; 16]> = SmallVec::new();
    current_chars.push(chars[0].clone());
    let max_gap = font_size * SPAN_GAP_FACTOR;

    for i in 1..chars.len() {
        let prev = &chars[i - 1];
        let curr = &chars[i];

        // Same line check: vertical distance within threshold
        let vert_dist = (curr.bbox[1] - prev.bbox[1]).abs();
        let horiz_gap = curr.bbox[0] - prev.bbox[2]; // gap between prev right and curr left

        if vert_dist < font_size * LINE_VERT_FACTOR && horiz_gap < max_gap && horiz_gap > -font_size * 0.5 {
            // Same span
            current_chars.push(curr.clone());
        } else {
            // Flush current span and start new one
            spans.push(make_span(current_chars, font, font_size, color));
            current_chars = SmallVec::new();
            current_chars.push(curr.clone());
        }
    }

    spans.push(make_span(current_chars, font, font_size, color));
    spans
}

fn make_span(chars: SmallVec<[CharInfo; 16]>, font: &str, font_size: f64, color: u32) -> TextSpan {
    let text: String = chars.iter().map(|c| c.c).collect();
    let bbox = compute_bbox(&chars);
    TextSpan {
        text,
        font: font.to_string(),
        size: font_size,
        color,
        bbox,
        chars: chars.into_vec(),
    }
}

/// Build lines from spans with similar vertical position.
fn build_lines(spans: Vec<TextSpan>, font_size: f64) -> Vec<TextLine> {
    if spans.is_empty() {
        return Vec::new();
    }

    // Sort spans by vertical position (y), then by horizontal position (x)
    let mut sorted = spans;
    sorted.sort_by(|a, b| {
        let ya = a.bbox[1];
        let yb = b.bbox[1];
        ya.partial_cmp(&yb)
            .unwrap()
            .then_with(|| a.bbox[0].partial_cmp(&b.bbox[0]).unwrap())
    });

    let mut lines: Vec<TextLine> = Vec::new();
    let mut current_spans: Vec<TextSpan> = vec![sorted[0].clone()];
    let line_threshold = font_size * LINE_VERT_FACTOR;

    for i in 1..sorted.len() {
        let prev_y = current_spans.last().unwrap().bbox[1];
        let curr_y = sorted[i].bbox[1];

        if (curr_y - prev_y).abs() < line_threshold {
            current_spans.push(sorted[i].clone());
        } else {
            lines.push(make_line(current_spans));
            current_spans = vec![sorted[i].clone()];
        }
    }

    lines.push(make_line(current_spans));
    lines
}

fn make_line(spans: Vec<TextSpan>) -> TextLine {
    // Sort spans within line by x position
    let mut sorted = spans;
    sorted.sort_by(|a, b| a.bbox[0].partial_cmp(&b.bbox[0]).unwrap());
    let bbox = compute_bbox_from_spans(&sorted);
    TextLine { bbox, spans: sorted }
}

/// Build blocks from lines with large vertical gaps.
fn build_blocks(lines: Vec<TextLine>, font_size: f64) -> Vec<TextBlock> {
    if lines.is_empty() {
        return Vec::new();
    }

    let block_threshold = font_size * BLOCK_GAP_FACTOR;
    let mut blocks: Vec<TextBlock> = Vec::new();
    let mut current_lines: Vec<TextLine> = vec![lines[0].clone()];

    for i in 1..lines.len() {
        let prev_bottom = current_lines.last().unwrap().bbox[3];
        let curr_top = lines[i].bbox[1];
        let gap = curr_top - prev_bottom;

        if gap > block_threshold {
            blocks.push(make_block(current_lines));
            current_lines = vec![lines[i].clone()];
        } else {
            current_lines.push(lines[i].clone());
        }
    }

    blocks.push(make_block(current_lines));
    blocks
}

fn make_block(lines: Vec<TextLine>) -> TextBlock {
    let bbox = compute_bbox_from_lines(&lines);
    TextBlock { bbox, lines }
}

// ─── BBox helpers ───

fn compute_bbox(chars: &[CharInfo]) -> [f64; 4] {
    if chars.is_empty() {
        return [0.0, 0.0, 0.0, 0.0];
    }
    let mut x0 = f64::MAX;
    let mut y0 = f64::MAX;
    let mut x1 = f64::MIN;
    let mut y1 = f64::MIN;
    for c in chars {
        x0 = x0.min(c.bbox[0]);
        y0 = y0.min(c.bbox[1]);
        x1 = x1.max(c.bbox[2]);
        y1 = y1.max(c.bbox[3]);
    }
    [x0, y0, x1, y1]
}

fn compute_bbox_from_spans(spans: &[TextSpan]) -> [f64; 4] {
    if spans.is_empty() {
        return [0.0, 0.0, 0.0, 0.0];
    }
    let mut x0 = f64::MAX;
    let mut y0 = f64::MAX;
    let mut x1 = f64::MIN;
    let mut y1 = f64::MIN;
    for s in spans {
        x0 = x0.min(s.bbox[0]);
        y0 = y0.min(s.bbox[1]);
        x1 = x1.max(s.bbox[2]);
        y1 = y1.max(s.bbox[3]);
    }
    [x0, y0, x1, y1]
}

fn compute_bbox_from_lines(lines: &[TextLine]) -> [f64; 4] {
    if lines.is_empty() {
        return [0.0, 0.0, 0.0, 0.0];
    }
    let mut x0 = f64::MAX;
    let mut y0 = f64::MAX;
    let mut x1 = f64::MIN;
    let mut y1 = f64::MIN;
    for l in lines {
        x0 = x0.min(l.bbox[0]);
        y0 = y0.min(l.bbox[1]);
        x1 = x1.max(l.bbox[2]);
        y1 = y1.max(l.bbox[3]);
    }
    [x0, y0, x1, y1]
}

// ─── Tests ───

#[cfg(test)]
mod tests {
    use super::*;

    fn make_char(c: char, x: f64, y: f64, w: f64, h: f64) -> CharInfo {
        CharInfo { c, bbox: [x, y, x + w, y + h] }
    }

    #[test]
    fn test_single_span() {
        let chars = vec![
            make_char('H', 100.0, 700.0, 7.0, 12.0),
            make_char('i', 107.0, 700.0, 5.0, 12.0),
        ];
        let blocks = cluster_chars(&chars, "Helvetica", 12.0, 0);
        assert_eq!(blocks.len(), 1);
        assert_eq!(blocks[0].lines.len(), 1);
        assert_eq!(blocks[0].lines[0].spans.len(), 1);
        assert_eq!(blocks[0].lines[0].spans[0].text, "Hi");
    }

    #[test]
    fn test_two_lines() {
        let chars = vec![
            make_char('A', 100.0, 700.0, 7.0, 12.0),
            make_char('B', 100.0, 680.0, 7.0, 12.0),
        ];
        let blocks = cluster_chars(&chars, "Helvetica", 12.0, 0);
        assert_eq!(blocks.len(), 1);
        assert_eq!(blocks[0].lines.len(), 2);
    }

    #[test]
    fn test_two_blocks() {
        let chars = vec![
            make_char('A', 100.0, 700.0, 7.0, 12.0),
            // Large vertical gap → new block
            make_char('B', 100.0, 650.0, 7.0, 12.0),
        ];
        let blocks = cluster_chars(&chars, "Helvetica", 12.0, 0);
        assert_eq!(blocks.len(), 2);
    }

    #[test]
    fn test_empty_input() {
        let chars = vec![];
        let blocks = cluster_chars(&chars, "Helvetica", 12.0, 0);
        assert!(blocks.is_empty());
    }

    #[test]
    fn test_span_gap_break() {
        // Two words with a large gap → two spans
        let chars = vec![
            make_char('H', 100.0, 700.0, 7.0, 12.0),
            make_char('i', 107.0, 700.0, 5.0, 12.0),
            // gap
            make_char('W', 150.0, 700.0, 8.0, 12.0),
            make_char('o', 158.0, 700.0, 6.0, 12.0),
        ];
        let blocks = cluster_chars(&chars, "Helvetica", 12.0, 0);
        assert_eq!(blocks.len(), 1);
        assert_eq!(blocks[0].lines.len(), 1);
        assert_eq!(blocks[0].lines[0].spans.len(), 2);
        assert_eq!(blocks[0].lines[0].spans[0].text, "Hi");
        assert_eq!(blocks[0].lines[0].spans[1].text, "Wo");
    }
}
