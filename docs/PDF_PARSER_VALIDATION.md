# Automotive PDF parser validation — 2026-10-14

DocBridge's lightweight native-text parser now passes all 38 manually inspected
extraction assertions in the selected Chinese automotive sample. The previous
parser passes 25; Docling Standard CPU passes 36; MinerU Basic CPU passes 31.
This establishes parity on these specific cases, not a universal ranking or a
claim of parity on natural scanned books, formulas or untested layouts.

## Inputs and reference engines

Four public documents provide 449 pages: Bosch KT660 (24), TI TCAN1575-Q1
(130), BYD SEAL Chinese owner manual (281), and a historical MEE vehicle protocol
draft (14). Original URLs, sizes and SHA-256 values are pinned in
[AUTOMOTIVE_PDF_CORPUS.json](AUTOMOTIVE_PDF_CORPUS.json); source context is in
[AUTOMOTIVE_PDF_SOURCES.md](AUTOMOTIVE_PDF_SOURCES.md).
The MEE document is a historical parsing fixture, not current regulatory advice.

All four have native text. The direct comparison uses identical, hash-matched
11-page subsets: Bosch 3/5/18, TI 7/42/100, BYD 45/80/250, MEE 7/8 (original
one-based pages). Source pages were rendered and visually inspected. Assertions
are pinned in [PDF_PARSER_GOLD.json](PDF_PARSER_GOLD.json); they check reading
order, complete paragraphs, table-cell relationships and technical identifiers,
signed numbers and units. They are curated regressions, not an overall accuracy
percentage or random sample. Full documents were parsed to check runtime and
completion; their entire contents have not been manually certified.

Reference configurations:

- Docling-slim 2.138.0, Standard CPU, Heron layout, accurate TableFormer,
  selective Tesseract Chinese/English OCR, four CPU threads. See
  [PDF_REFERENCE_SETUP.md](PDF_REFERENCE_SETUP.md).
- MinerU 4.0.12, DocVortex 0.5.16, ONNX Runtime 1.31.0, Basic CPU, native-text
  mode. This does **not** compare MinerU Standard or Advanced. See
  [MINERU_REFERENCE_SETUP.md](MINERU_REFERENCE_SETUP.md).

No translation API, external LLM inference or reference translation was used. Each
engine is scored against the source assertions; upstream output is not repaired
by the scoring adapters. HTML/JSON cell spans are expanded as declared by the
engine. Normalization removes whitespace and applies NFKC/minus variants only.

## Changes and observed errors

| Case | Previous failure | Implemented behavior |
| --- | --- | --- |
| Bosch narrow columns | Left and right paragraphs mixed; instruction order broke | Infer a supported whitespace gutter and use it consistently for lines and page ordering |
| Native overprint | Repeated glyphs duplicated text | Remove colocated identical glyphs before extraction |
| TI electrical table | MIN/TYP/MAX values collapsed into one cell | Partition native glyphs by header column bounds, only when every glyph is retained |
| BYD open table cells | Values in cells with missing border geometry disappeared | Recover unclaimed native glyphs inside established column/row bounds |
| Picture OCR | Caption/screenshot text interrupted a native paragraph | Keep OCR attached to its image while preserving segments and source geometry |
| Numbered instructions | Hanging-indent continuation became a separate sentence | Merge compatible wrapped lines within the same column |
| Repeating margins | Headers/footers polluted Markdown and translation context | Mark furniture without deleting source segments; retain bottom technical specifications |

Docling's two failed assertions concern Bosch column order and a TI typical-value
cell relationship. MinerU Basic's seven failed assertions concern the TI
MIN/TYP/MAX table. These engine differences should not be extrapolated beyond
this fixture.

One suspicious TI condition was checked at high zoom: the original really says
`12V ≤ VCANL ≤ +12V` without a leading minus. DocBridge retains the printed
source rather than guessing a corrected engineering value.

PDF adapter version is now **5**. Old parse caches require a fresh PDF job;
historical export-only access remains supported. Office parsing and the Argos
translation policy are unchanged by this update. Original images and all margin
segments remain in the saved document. Markdown omits classified furniture;
PDF-to-DOCX still reconstructs the page content and may differ in layout/fonts.

## Reproduce the assertions

After extracting the pinned subsets with each engine, run:

```bash
.venv/bin/python scripts/score-pdf-parsers.py docbridge PATH_TO_DOCUMENT_DIRECTORIES
.venv/bin/python scripts/score-pdf-parsers.py docling PATH_TO_RAW_JSON_DIRECTORY
.venv/bin/python scripts/score-pdf-parsers.py mineru PATH_TO_RAW_MIDDLE_JSON_DIRECTORY
```

DocBridge input directories contain `DOCUMENT_ID/document.json`; reference JSON
files use `DOCUMENT_ID.json`. `--output REPORT.json` saves the complete case
results. The scorer reads the tracked gold file and does not modify extraction.
Public PDFs, rendered pages, extracted full copyrighted text and reference model
caches remain in ignored local test data rather than being redistributed.

## Sequential same-input CPU measurements

Linux x86_64, Intel Core i5-13500H, Python 3.12.13. Each engine ran separately
without another parser/build active. Reference weights were cached locally; the
first file includes model initialization, subsequent files reuse the converter.
DocBridge/baseline use a fresh process per file, with imports outside the parse
timer. All four engines consumed exactly the same subset SHA-256 values.

| Engine | Assertions | Total parse seconds (11 pages) | Peak process RSS (MiB) |
| --- | ---: | ---: | ---: |
| baseline | 25/38 | 9.136 | 88.9 |
| docbridge | 38/38 | 10.070 | 88.8 |
| docling | 36/38 | 115.111 | 1696.6 |
| mineru | 31/38 | 38.973 | 1726.5 |

The new native parser adds about one second over the previous parser on these
11 pages while fixing 13 assertions. This is not a promise of speedup over the
old parser. It remains substantially faster and smaller in process memory than
the tested reference configurations on this fixture. Different OCR coverage and
model initialization affect cost; none of these times include translation,
installation, downloads or JSON/Markdown export. RSS excludes child OCR/render
workers and is not total machine memory. DocBridge uses Linux VmHWM; references
use process ru_maxrss high-water. This is a single observed run, not a statistical
latency distribution or end-to-end UI timing.

Docling's small-region orientation-detection warnings did not fail conversion:
all four files returned SUCCESS with empty conversion errors. The comparison
uses Standard CPU for Docling and **Basic CPU only** for MinerU.

## Full-document verification

The final source processed all four documents without parser exceptions:

| Document | Pages | Parse seconds | Peak process RSS (MiB) |
| --- | ---: | ---: | ---: |
| Bosch KT660 | 24 | 32.040 | 152.9 |
| TI TCAN1575 | 130 | 49.481 | 199.1 |
| BYD SEAL | 281 | 141.826 | 146.9 |
| MEE protocol draft | 14 | 2.255 | 74.4 |

Total: 449 pages, 225.602 parse seconds. Parsing includes native extraction,
image OCR and image extraction; it excludes translation, JSON save and Markdown
export. Part of this stress run overlapped regression tests/build, so these
numbers describe successful full-document processing rather than isolated
cross-engine throughput. RSS is Linux `/proc/self/status` VmHWM for the parser
process; Tesseract subprocess memory is excluded.

The suite passed **148 tests with one skip**. Final spec and standards reviews
found no remaining actionable findings after fixing technical values incorrectly
classified as a repeating footer. Two real-PDF regression cases retain both
changing (12/24 V) and identical (12/12 V) bottom-of-page specifications.

The freshly built Linux app ran the actual spawned worker on all 11 sample
pages: exit 0, PDF adapter 5, no translation provider, **38/38 assertions passed**.
Its source segments and complete block trees matched development output exactly
for all four files. The newly built wheel contains the same parser source bytes.
Machine-readable evidence is in [PDF_PARSER_RESULTS.json](PDF_PARSER_RESULTS.json).

To collect a new native parse report, use:

```bash
.venv/bin/python scripts/benchmark-pdf-parser.py INPUT.pdf --output OUTPUT_DIRECTORY
```

The benchmark writes source-language Markdown, canonical document JSON, source
and code hashes, elapsed parse time and Linux process peak RSS. Installation,
translation and output serialization are outside the parse timer.

## Actual Linux package

The full offline Linux app includes the existing Argos Chinese→English model,
CPU runtime, Tesseract and Chinese/English language packs. It includes neither
Docling/MinerU reference environment nor their model weights. Installed logical
file size including README, validation docs and third-party notices is recorded
in `PDF_PARSER_RESULTS.json` and enforced below **2,000,000,000 bytes** by
`scripts/check-size.py`. This limit is checked on the directory, not merely on a
compressed archive. The frozen parser verification above used this newly built
executable. Cross-platform Windows/macOS builds are not verified by this run.

## Limits

Natural scanned automotive books have not been verified in this corpus. Existing
synthetic scanned-page tests validate the OCR path, not general scan accuracy.
Complex formulas, borderless tables without usable column geometry, diagrams and
bad encodings remain uncertain. Image OCR still uses Tesseract and retains a
warning; the original image is kept for inspection. This work does not promise
pixel-identical PDF-to-Word output. An online LLM can translate extracted text
later, but missing source structure cannot be assumed recoverable by translation.

The production app retains pdfplumber/PDFium/Tesseract and adds no layout model
weights or reference runtime dependencies. Docling and MinerU environments and
models are isolated comparison tools and are excluded from the app bundle.
