# Docling CPU reference for Chinese automotive PDFs

This is a benchmark-only environment, not a DocBridge dependency or a proposed bundled parser. It does not invoke a translation provider, external LLM, a VLM or a paid API. The reference uses the actual PDF subsets in `.test-data/automotive-pdf/samples/`, with source/subset hashes and original-page mappings retained. It must be evaluated against manually inspected source pages, not assumed correct because it is a well-known engine.

## Primary-source configuration

Docling's official installation guide supports CPU-only PyTorch and Tesseract CLI. The standard PDF pipeline includes layout analysis and table structure extraction. This experiment selects that standard pipeline, rather than the native-only or VLM pipeline. [Installation](https://docling-project.github.io/docling/getting_started/installation/), [pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/).

`DocumentConverter.convert` accepts `page_range`; the supplied range covers every page of each identical subset PDF. The resulting DoclingDocument JSON includes provenance bounding boxes and structured table cells; Markdown is an additional export for human inspection. [Converter API](https://docling-project.github.io/docling/reference/document_converter/), [DoclingDocument](https://docling-project.github.io/docling/concepts/docling_document/).

Selected original pages are Bosch KT660 3/5/18, TI TCAN157x-Q1 7/42/100, BYD SEAL 45/80/250, and MEE communication protocol 7/8. These are eleven native-text pages, not a natural scanned corpus. Sources and complete-document hashes are recorded in `AUTOMOTIVE_PDF_CORPUS.json`.

## Isolated environment and reproduction

Environment: Python 3.12.13; `docling-slim[standard]` 2.138.0; docling-core 2.101.1; docling-parse 7.22.3; docling-ibm-models 4.0.3; CPU torch 2.5.1+cpu / torchvision 0.20.1+cpu; transformers 4.57.6; system Tesseract 5.5.3. Complete frozen dependencies are saved under `.test-data/pdf-reference/requirements-frozen.txt`. The `docling-slim` name does not mean a native-only conversion: the **standard extra** and its trained layout/table models are installed and used.

CPU options use four inference threads, `OMP_NUM_THREADS=4`, native PDF text plus selective Tesseract OCR (`chi_sim`, `chi_tra`, `eng`), `force_full_page_ocr=False`, and table extraction enabled with default accurate mode. No image-description/code/formula enrichment models are enabled. All effective options are saved in the report.

```sh
.venv/bin/python -m venv --system-site-packages .test-data/pdf-reference/venv
.test-data/pdf-reference/venv/bin/python -m pip install 'torch==2.5.1+cpu' 'torchvision==0.20.1+cpu' --index-url https://download.pytorch.org/whl/cpu
.test-data/pdf-reference/venv/bin/python -m pip install 'docling-slim[standard]==2.138.0' 'torch==2.5.1+cpu' 'torchvision==0.20.1+cpu' 'transformers==4.57.6'
OMP_NUM_THREADS=4 .test-data/pdf-reference/venv/bin/python .test-data/pdf-reference/run_docling.py
```

The environment is isolated from `.venv` and `dist`. A venv created by another venv's Python does not inherit the parent venv's installed torch packages; CPU wheels therefore install in the reference venv. `HF_HOME` points to `.test-data/pdf-reference/hf-cache`, keeping reference model downloads separate from production. The model snapshot manifest records paths, revisions and sizes.

Tesseract's reference-only data directory `.test-data/pdf-reference/tessdata/` contains system `configs/` and `tessconfigs/`, symlinks to the application's three language weights, and system `osd.traineddata`. This matters because Docling requests TSV output: pointing `TESSDATA_PREFIX` directly at the application's weights-only directory omitted the `configs/tsv` file and yielded plain text rather than TSV. No application assets were changed by this reference setup.

## Measurements and limitations

Outputs are `.test-data/pdf-reference/outputs/{document_id}.json` and `.md`; `report.json` records conversion status, durations, item counts, hashes, options and cumulative process peak RSS. Model manifest is `.test-data/pdf-reference/model-manifest.json`.

Timing begins before `convert`, ends after conversion and before exporting JSON/Markdown. Imports and converter construction are recorded separately. Initial model download occurred during the retained TSV-failure run. Thus the successful report's first conversion includes pipeline initialization with cached weights, not downloading; later conversions reuse the initialized converter. A fresh process with cached weights is an initialization-inclusive run, not an in-process warm run. Root parser work can contend for CPU during setup, so these initial times are diagnostic and must not be presented as an isolated throughput comparison.

Initial dependency failure is retained in `dependency-failure-report.json`: unconstrained transformers 5.19.0 imports require `torch.accelerator`, absent from torch 2.5.1. Pinning transformers 4.57.6 satisfies installed package metadata and allows the standard models to load. The subsequent TSV configuration failure is retained separately in `tesseract-config-failure-report.json`. These failed runs are setup failures, not evidence of extraction quality.

Downloaded layout/table snapshots currently total **530,000,694 bytes** (approximately 505.45 MiB), covering Heron layout and Docling TableFormer assets. The unoptimized isolated Python environment is approximately 1.6 GiB before models; these sizes are **not** a production bundle estimate. The existing approximately 1.43 GB DocBridge bundle has limited remaining budget, so full Docling cannot be added without measured dependency deduplication and a new release-size check.

Extraction results and benchmark figures should be read from the raw reports and the root's manually scored benchmark. Neither successful conversion nor complete Markdown output proves faithful reading order, table reconstruction or Chinese technical-symbol preservation.

Initial successful reference run, with the timing qualifications above:

| Subset | Pages | Conversion seconds | Tables | Text items |
|---|---:|---:|---:|---:|
| Bosch KT660 | 3 | 27.66 | 2 | 191 |
| TI TCAN157x-Q1 | 3 | 38.86 | 7 | 74 |
| BYD SEAL | 3 | 28.58 | 1 | 51 |
| MEE protocol | 2 | 24.84 | 4 | 10 |

All four conversions returned `SUCCESS` with empty conversion-error lists. Selective OCR emitted orientation-detection warnings for small image regions; the conversion still completed. Cumulative peak RSS reached 1,789,692 KiB (approximately 1.71 GiB). This is CPU extraction time only, excludes translation, and is not a controlled speed claim against DocBridge. Initial visual/text inspection raises possible technical-symbol and span-duplication concerns in tables; verify them against the source before selecting an engine.

## Final isolated comparison

A later sequential run with cached models and no competing parser/build is
recorded in [PDF_PARSER_VALIDATION.md](PDF_PARSER_VALIDATION.md) and
[PDF_PARSER_RESULTS.json](PDF_PARSER_RESULTS.json). It supersedes the initial
contended timings above for the same-input speed comparison.
