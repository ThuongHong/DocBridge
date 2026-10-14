# MinerU Basic CPU reference

This reference runs the unmodified upstream engine on the exact same 11-page
automotive Chinese subsets as DocBridge and Docling. It is **MinerU Basic**, not
Standard or Advanced. Upstream Basic uses small OCR/layout/formula/table models;
Standard adds a VLM. Therefore a Basic score cannot establish parity with all
MinerU tiers. [Official tier documentation](https://opendatalab.github.io/MinerU/usage/tiers/).

## Environment and reproduction

Installed on the existing Linux CPU host in an isolated virtual environment:
MinerU **4.0.12**, DocVortex **0.5.16**, ONNX Runtime **1.31.0**, Python 3.12.
The application environment, source, and distribution are not modified by this
reference. No documents are uploaded, no paid API is used, and no external LLM/VLM model
is downloaded or run.

```sh
.venv/bin/python -m venv .test-data/mineru-reference
.test-data/mineru-reference/bin/pip install 'mineru==4.0.12'
MINERU_HOME="$PWD/.test-data/mineru-reference-home" \
  .test-data/mineru-reference/bin/mineru-kit models download \
  --tier basic --small-backend onnx --source huggingface
MINERU_HOME="$PWD/.test-data/mineru-reference-home" \
  .test-data/mineru-reference/bin/mineru-kit models verify \
  --tier basic --small-backend onnx
MINERU_HOME="$PWD/.test-data/mineru-reference-home" \
  MINERU_MODEL_SOURCE=local MINERU_MODEL_SMALL_BACKEND=onnx \
  .test-data/mineru-reference/bin/python .test-data/mineru_run.py
```

The official managed download fetched 13 files and verified
`MinerU-4_models_onnx: ok`. The model root occupies approximately 819 MiB; the
isolated base environment approximately 805 MiB. These are filesystem sizes,
**not** a measured distributable app size. Neither is added to DocBridge.
[Model management](https://opendatalab.github.io/MinerU/usage/model_source/).

The runner calls the public stateless SDK `parse(..., tier="basic",
ocr_mode="txt")`, explicitly preserving the native PDF text mode, and writes
raw Middle JSON, Structured Content JSON and Markdown. It uses a main guard
because upstream starts multiprocessing PDF render workers. SDK page selection
defaults to all pages; the inputs themselves are the fixed 2/3-page subsets.
[SDK contract](https://opendatalab.github.io/MinerU/usage/sdk_api/).

Results are in `.test-data/mineru-outputs/`; `metrics.json` records source SHA-256,
per-file elapsed parse time and process peak RSS. The first file includes cold
model initialization; later files reuse caches/models. Downloads and environment
installation are excluded. Concurrent app work may affect timing; warm isolated
measurements are required before making a throughput claim.

Middle JSON preserves page indices, ordered semantic blocks and geometry;
table-body content contains upstream HTML. A scoring adapter may decode HTML
rowspan/colspan and strip formatting tags but must not repair extracted text,
reorder engine blocks, reconstruct omitted tables, or read the source PDF to
improve the score. [Output protocol](https://opendatalab.github.io/MinerU/reference/output_files/).

## Measured extraction results

The first CPU batch completed all 11 pages successfully. The independent
visually checked gold assertions score **31/38** using raw engine Middle JSON.
`.test-data/mineru_score.py` expands only actual HTML rowspan/colspan and reads
text content. It writes `.test-data/mineru-outputs/score.json` and does not alter
the shared DocBridge/Docling scoreboard.

| Input subset | Pages | Parse seconds |
| --- | ---: | ---: |
| Bosch KT660 | 3 | 24.662 |
| BYD SEAL | 3 | 7.860 |
| MEE protocol | 2 | 5.895 |
| TI TCAN1575 | 3 | 11.782 |

Total parse time is 50.200 seconds; peak main-process RSS is 1,769,940 KiB.
PDF rendering workers are excluded from that process RSS. The first document
includes cold initialization. A DocBridge full-document extraction was also
active, so these observations are not isolated throughput measurements.

All seven failed assertions are on the TI electrical-characteristics table:
upstream Basic merges minimum/typical/maximum columns into one cell and combines
overlapping native text in test conditions. Raw HTML contains, for example,
`<td>最小值典型值最大值</td>` followed by a single `75 133` value cell. The
adapter deliberately does not invent separate numeric columns. Bosch, BYD and
MEE assertions pass in this sample. This small selected-page result is not a
whole-book or natural scanned-document benchmark and does not compare MinerU
Standard/Advanced.

## Final isolated comparison

A later sequential run with cached models and no competing parser/build is
recorded in [PDF_PARSER_VALIDATION.md](PDF_PARSER_VALIDATION.md) and
[PDF_PARSER_RESULTS.json](PDF_PARSER_RESULTS.json). It supersedes the initial
contended timings above for the same-input speed comparison.
