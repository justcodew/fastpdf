# Development History

Quick-reference timeline of completed work. One line per feature, grouped by release.
Full details per release: [CHANGELOG.md](../CHANGELOG.md). Forward plan: [ROADMAP.md](ROADMAP.md).

## v0.7.0 — 2026-06-27 — 规模化验证

- **tracing 集成**：`flashpdf.set_log_level("debug"|"trace"|...)` + `RUST_LOG=flashpdf_core=debug`
- **`docs/PERFORMANCE.md`**：latency 表、API 决策树、调参指南、flamegraph 跑法
- **Tiny-file perf**：实测 0.012ms（vs fitz 0.226ms，19x 更快），已超 0.15ms 目标
- 关键路径加 tracing span：`Document::from_mmap` / `extract_doc`
- Skipped：4.1 外部语料下载（用户决定跳过）

## v0.6.0 — 2026-06-27 — 精度深挖

- **竖排文本聚类**：`layout::cluster_rotated_chars` 通过 bbox (x,y) 转置 → 标准聚类 → 转回。修复 90°/270° 旋转文本每个字自成一行
- **`docs/CHAR_SIM_AUDIT.md`**：PyMuPDF 165-PDF corpus 残差分类（match 20% / partial 22% / low 21% / both_empty 18% / flash_empty_type0 9% / flash_empty_other 8% / acroform 2%）
- 主导残差：Type0 Identity-H 无 `/ToUnicode`（需 font-program 解析，与 zero-rendering 设计冲突，未来增强）
- Type3 字体走通用 `/ToUnicode` 路径，缺失时 `diagnostics.type3_char_count` 计数

## v0.5.0 — 2026-06-27 — 适用面扩大

- **加密 PDF 解密**：RC4（V1/V2 R=2/3）+ AES-128-CBC（V4 R=4），空用户密码快速路径
- 修复两个核心 bug：
  1. HexString ASCII vs 二进制字节（`extract_id_first` + `crypto::get_padded_bytes` 加 hex_decode）
  2. per-object key 用 3-byte obj_num（spec §7.6.2，常见 4-byte 实现陷阱）
- **Inline `/Encrypt<<...>>` 检测**：fitz/Acrobat 形式，通过 `encrypt_present` + `trailer_offset` 字段，Document 重新解析 trailer
- **`is_linearized`**：检查首对象 `/Linearized 1`（PDF §F.2）
- **结构化错误**：`ParseError::At { inner, offset, context }`，`parse_object_at` 关键路径附加字节偏移 + ±16 字节上下文
- **`examples/`**：`rag_index.py` / `markdown_export.py` / `ocr_bridge.py` / `toc_to_yaml.py`
- **`docs/MIGRATION_FROM_FITZ.md`**：API 对照表 + flags=0 stub 说明 + 加密/渲染/注解 fallback

## v0.4.0 — 2026-06-27 — fitz 功能补全

- **`doc.metadata`**：fitz 兼容 dict（title/author/.../format/encryption/size），UTF-16BE + PDFDocEncoding + hex string + literal escape 解码
- **`page.get_links()` + `extract_links()`**：Uri/Goto/Named/Launch/GotoR 链接，corpus 146/150 与 fitz 一致
- **`span["flags"]`**：fitz bitmask（italic=2, serif=4, mono=8, bold=16），从 `/FontDescriptor /Flags` + 名称启发式推断
- **`doc.get_toc()`**：DFS 遍历 `/Outlines`，周期安全；Named dest 通过 `/Names /Dests` Name Tree 解析
  - `simple=True` → `[[level, title, page], ...]`
  - `simple=False` → 富 dict（kind/uri/to_point/name）
- **`flashpdf` CLI**（基于 click）：`extract <pdf...>` + `--pages 0,1,5-8` 子集 + `--output-dir` 批量

## v0.1.x – v0.3.x — 基础设施

- 自研 PDF 解析器（object / xref table + stream / content stream / ObjStm）
- 字体处理：`/ToUnicode` CMap / Encoding differences / Type0 CID / Type3 / TrueType
- 布局分析：cluster_chars → spans → lines → blocks；XY-cut reading order；column detection
- 图像提取：FlateDecode / LZWDecode / ASCII85 / RunLength / DCT / JPX
- 并行化：page-parallel（rayon）+ file-parallel（`extract_many`）
- fitz 风格 `open()` API：eager 提取，`doc[i].get_text("dict"|"text"|"blocks")`
- PyPI 发布 + GitHub Actions（tag 触发 Build Wheels，PR 触发 CI lint/test）

## 关键设计决策

| 决策 | 理由 |
|---|---|
| 仅解析，不渲染 | zero-rendering 是核心性能优势；Type3 字形渲染、AcroForm 字段值留给 fitz/pikepdf |
| mmap + `Box::leak` 零拷贝 | 解析器借用 mmap，cached objects 用 leak 拿 `'static` lifetime |
| 空用户密码 fast-path | 覆盖"加密但可读"的绝大多数场景；非空密码/AES-256 返回清晰错误 |
| spec-correct 3-byte obj_num | PDF §7.6.2 明确要求；常见 4-byte 实现会静默破坏解密 |
| `ParseError::At` 包装而非全 enum 改造 | 向后兼容 `Message(String)`，按需附加 offset |
| 跳过 4.1 外部语料 | 用户决定；现有 PyMuPDF corpus 已能定位主导残差 |

## 测试 & CI

- `cargo test -p flashpdf-core --lib`：90 测试全过
- `cargo clippy --workspace --all-targets -- -D warnings`：零 warning
- `cargo fmt --all --check`：强制 rustfmt
- GitHub Actions：CI（macos/ubuntu/windows × lint+test）+ Build Wheels（tag 触发 → PyPI）
