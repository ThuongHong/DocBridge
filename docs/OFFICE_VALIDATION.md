# Chinese Office translation and Review UX validation

Tested locally on 2026-10-13 using Argos Translate 1.9.6, Chinese–English
model 1.9, and CPU inference with Python network connections blocked.
The six inputs are generated fixtures, not third-party automotive documents.

| Input | Translated segments | Office + Markdown export | LibreOffice pages, source → English |
| --- | ---: | --- | --- |
| Simplified Chinese DOCX | 13 | Passed | 1 → 1 |
| Traditional Chinese DOCX | 13 | Passed | 1 → 1 |
| Simplified Chinese PPTX | 7 | Passed | 1 → 1 |
| Traditional Chinese PPTX | 7 | Passed | 1 → 1 |
| Simplified Chinese XLSX | 7 | Passed | 3 → 3 |
| Traditional Chinese XLSX | 7 | Passed | 3 → 3 |

Fixtures exercise Word headers, footers, tables and mixed bold/italic runs;
PowerPoint text boxes, tables, pictures and speaker notes; and Excel shared
strings, rich text, formulas, numeric values, charts and pictures. ZIP members,
relationships, media, styles and chart parts were checked for preservation.
Word formatting, PowerPoint shape geometry and Excel formulas/numbers were
also checked through the corresponding document libraries.

All twelve source/result files rendered successfully in LibreOffice. Word and
PowerPoint examples retained their single-page layouts. The Excel example
already printed across three pages before translation, splitting pictures and
charts at page boundaries; the longer English cell text also clips at the
existing column boundary. The app does not automatically resize columns or
reflow Office layouts.

## Translation limitations observed

- Raster image text remains Chinese; translating embedded pictures requires OCR
  and an image replacement workflow.
- Excel sheet names and chart text remain Chinese. Chart objects are retained
  in Office output but are not exported as Markdown charts.
- Extracted segments contain no remaining Chinese ideographs, but this is not
  a translation accuracy check. Argos mistranslates the voltage sentence as
  `AC-123 _Other Organiser 12 V` and produces awkward technical prose.
- Mixed runs retain their original boundaries; a translated `Note:` followed
  by another run can appear without a separating space.

## Review navigation regression

Previously, only the explicit Review action loaded the document. Clicking the
Review tab after translation left it empty because tab changes did not load
the selected job. Worker completion also did not populate an already-open
Review tab.

The tab now loads the selected document after the worker stops, prioritizing
the focused selected row. Opening Review during translation populates it on
completion. Switching away and back preserves unsaved edits at the same
revision. Starting a translation for the reviewed job saves edits first.

Two regression tests cover tab navigation, unsaved edits and worker completion.
A separate run using the real Qt window, child worker and Argos model opened
Review during translation and displayed all 13 Word segments automatically
after completion (6.57 seconds). The full suite passed: 62 tests, 1 skipped.

Review is a manual segment editor, with source/translation comparison and
warnings. Saving increments the stored document revision and marks previous
exports stale. Re-export writes the edited results without calling the model;
retranslating selected segments calls the configured translation provider.
There is no automatic second-model quality review.

Raw inputs, outputs, translations, rendered PDFs and the real-worker report
are available under the ignored `.test-data/office-validation/` directory.
`dist/office-test-results.zip` contains the six inputs and results, Markdown,
rendered previews, reports and local validation runners.
