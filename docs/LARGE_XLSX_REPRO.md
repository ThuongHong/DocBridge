# Large Excel offline translation reproduction

Tested locally on 2026-10-13 with Argos Translate 1.9.6, the existing
Chinese-English 1.9 package, CPU inference, and Python network connections
disabled. No online translation or Qwen inference was used.

## Fixture

`chinese-large-3sheets.xlsx` is **41,118,652 bytes / 39.21 MiB**, with three
worksheets: 控制器测试, 故障诊断 and 标定记录. It exceeds 30 MB and 30 MiB.
It is a generated test workbook, not a proprietary Bosch document.

Each sheet has 100 Chinese test cells covering shared strings, inline strings,
direct `t="str"` values and mixed bold/italic runs. Titles, headers, notes,
merged and hidden cells provide additional plain-text cases. There are
624 ordinary Chinese-bearing cells in total, including the 300 explicit cases.

The bulk load consists of 7,500 deterministic encoded diagnostic-record strings
stored in literal string formulas, plus numeric records. This keeps the fixture
large through actual worksheet contents rather than ZIP padding or pictures.
It exercises a large XML package, **not 30 MB of unique Chinese inference text**.
The workbook has 10 ZIP members and 106,784,600 uncompressed bytes.

The base workbook/data were authored with artifact-tool. Unsupported explicit
OOXML test encodings were added at package level without changing the displayed
case text. Source SHA-256 and cell manifests are retained with the fixture.

## Reproduced failure

| Observation | Previous reader, adapter 4 | Fixed reader, adapter 5 |
| --- | ---: | ---: |
| Extracted segments | 300 | 999 |
| Explicit test cells missing from extraction | 75 | 0 |
| Ordinary cells still containing Chinese after export | 399 | 0 |
| Document reports complete | Yes | Yes |

All 399 remaining ordinary cells in the baseline used `t="str"` with direct
`<v>` text and **no formula**. Examples include `控制器测试!A1`, `A3`, `B3`,
and `C3`, as well as 75 explicit column-B cases. The reader treated them as
literals instead of translation segments. Argos never received their text,
so completion counted only the extracted subset and did not reveal the omission.

This is a parser coverage bug reproduced under the reported conditions; without
the original company workbook it does not prove every earlier failure had this
cause. Microsoft's OpenXML SDK explicitly demonstrates a text cell using
`CellValues.String` and `CellValue("Microsoft")` without a formula.
[Microsoft CellValue example](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.cellvalue)

## Fix and verification

- Extract non-formula `t="str"` / `<v>` values, including blank values, with their
  sheet/cell anchors and source context.
- Write the translated text back into the original `<v>`, retaining the cell
  type and style. Continue excluding formula caches from translation.
- Let Argos handle long segments with its existing internal splitter. A separate
  pipeline regression reproduced unwanted spaces inserted into a long ASCII
  direct-string value when it was split/rejoined despite requiring no translation;
  the value now passes through verbatim.
- Advance the Office adapter to 5. **Import the source as a new job** after this
  update: an older cached document lacks the omitted segments. Historical
  export-only access remains supported. The shared Office adapter version means
  older DOCX/PPTX parse caches also require a fresh job for translation.
- Final review also advanced the Argos translation-policy fingerprint to 5.
  This blocks resume of older partly translated PDF jobs across the changed
  long-segment splitting policy. Completed historical jobs still support
  export-only access; online provider fingerprints are unchanged.

The same unchanged 39.21 MiB source was processed before and after the fix.
The fixed development pipeline completed in 32.13 seconds. The rebuilt frozen
Linux worker completed in 19.53 seconds after the final fingerprint fix; these runs use different parse/checkpoint
instrumentation and should not be interpreted as a throughput comparison.
Frozen and development exports matched every uncompressed ZIP member. The
packaged worker stored the current Argos policy fingerprint.

The result retains all three sheets, rich-run properties, merged cells and hidden
row/column metadata. All **7,806 formula cells**, their cached values, **15,300
numeric cells** and **7,671 blank cells** were unchanged. Styles, workbook,
relationships and other package parts were compared byte for byte; the source
hash was unchanged.

LibreOffice opened both source and result and rendered each to six PDF pages.
The main output page for each worksheet was visually inspected. Argos still
produces awkward translations and mixed-run spacing; longer English text can
clip at the existing column widths. Formatting was preserved rather than
manually changing the test output to hide these limitations.

There are still **six Chinese formula-result caches**, `F5` and `F6` on each
sheet, from `IF(...,"正常","故障")` and `="已完成"`. Those formulas and results
were intentionally left unchanged. Sheet names also retain their original
language. These are distinct from the ordinary-cell extraction bug.

Three new regression tests failed before their fixes and pass afterward, covering
direct strings, blank strings, formula-cache exclusion, and package preservation.
An additional cache-version case verifies that adapter-4 documents require
reparsing, and a PDF regression checks the old Argos profile is rejected before
inference while historical export remains available. Full suite: **136 passed,
1 skipped**; Ruff and whitespace checks pass.

## Evidence

Fixture and raw reports live under `.test-data/large-xlsx/`:

- `outputs/large-xlsx-repro/chinese-large-3sheets.xlsx`: original test workbook.
- `baseline-report.json`, `fixed-report.json`: per-cell results and timing.
- `untranslated-before-after.csv`: the 399 previously missed cells and their
  before/after exported text.
- `fixed-output/chinese-large-3sheets.en.xlsx`: translated result.
- `frozen-report.json`: actual packaged-worker validation.
- `rendered/` and `render-report.json`: native Office rendering evidence.

Reproduction: `.venv/bin/python .test-data/large-xlsx/run_local.py baseline`
loads the previous reader from commit `7aca8ff` in an isolated diagnostic module
and fails the final cell-coverage assertion. `... run_local.py fixed` uses the
current reader and passes. These commands do not reset the checkout or call APIs.
