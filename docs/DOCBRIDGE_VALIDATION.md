# DocBridge validation

The 2026-10-13 performance update reuses the Argos tokenizer/model and packs
online requests against the existing context budget, with checkpoints and
progress per completed request. The local 27-segment comparison was 2.29 times
faster with identical translations; the mock online fixture fell from 16 to
6 requests. Frozen Office exports matched the previously validated files
member for member. See [performance diagnosis and measurements](PERFORMANCE_DIAGNOSIS.md)
for the benchmarks, unchanged OCR limits and resume compatibility.

The accepted UI is “Gọn một màn hình”: a document list with two task buttons,
one primary action, an icon-only Settings button, and no main Review/Glossary
tabs. Review remains available from the entry menu in its own window; Glossary
is inside Settings. Defaults remain light theme and English.

The user accepted Argos's translation-quality limitations on 2026-10-13 and
confirmed that the priority is extracting source text for a later online LLM.
The acceptance criteria are now the local parser, source-language Markdown,
format preservation/reconstruction, selected UI and naming/build behavior.
Argos is an offline smoke/format test engine, not a semantic quality gate.
No Qwen inference or external translation API was called.

## Original-language Markdown conversion

The real Qt UI and spawned worker converted six Simplified/Traditional Chinese
DOCX/PPTX/XLSX fixtures and a two-page Chinese PDF. Python network connections
were disabled. No translation provider was created, no API configuration/key was
needed, source text stayed Chinese, and segment targets stayed unset. Re-export
of a conversion uses source text, including when other jobs are translations.
Converting an already-translated job preserves its translations and checkpoints.

## Format and reconstruction

Office validation checks ZIP members, relationships, media, style parts, Word
tables and bold/italic runs, PowerPoint shape geometry, and Excel formulas,
numbers, charts and images. Outputs are rendered in LibreOffice in addition to
structural checks. See the [earlier Office cases](OFFICE_VALIDATION.md).

Native chart extraction now includes titles, series/category string caches and
literal labels. OOXML content types identify charts/drawings with custom part
filenames, with a conventional-name fallback. Simple horizontal/vertical worksheet references bind cached
labels to the existing cell segments, so a reviewed cell target also updates its
chart. DOCX/PPTX chart-linked XLSX workbooks are read and patched as nested OOXML
packages; formulas, numeric cells, styles and relationships retain their original
values. External/unmapped references are not fetched and produce a warning that
cached labels may change on refresh. Multi-level/two-dimensional references are
not synchronized automatically.

Three genuine native chart fixtures (DOCX, PPTX, XLSX) completed real local Argos
translation and LibreOffice rendering. Each retained one page, chart geometry,
numeric values 12/100, chart formula/style properties and English title/category
labels. All three output pages were visually inspected. Chart XML was compared
canonically after masking only its text fields, while styles/relationships/media
were compared byte for byte. PPTX tests additionally proved its slide XML stays
unchanged and reviewed labels match the embedded worksheet.

SmartArt source data and cached drawing paragraphs, including same-style split
runs and different XML indentation, share an exact matching text-group target.
This is covered by structural tests, not native SmartArt visual/regeneration
validation. Drawing text boxes are also extracted. Markdown exposes the text and
chart workbook data but does not render the visual chart/SmartArt. The Office
adapter version is now 4; older parsed jobs require a new job to translate while
historical export-only access is retained.

The PDF adapter now joins tightly spaced wrapped lines into paragraphs without
mixing columns or OCR paragraph IDs. It keeps source page dimensions, bounding
boxes, line positions, basic font properties, table-cell coordinates and image
dimensions. DOCX reconstruction uses portrait/landscape sections, source font
sizes and emphasis, source table widths/minimum row heights and image scales.
Page labels used for Markdown navigation are not added as fake Word headings.

The 04:00 follow-up additionally tested a two-page Chinese technical manual with
a full-width heading/note, two prose columns, and a diagram in the right column.
The real Argos output was rendered in LibreOffice and both pages were visually
inspected. Simple column bands now use borderless Word tables with a separate
gutter, keeping text and images side by side. The two columns started at the
same vertical position (142.879 pt) and retained horizontal origins of 48.1 pt
and 342.1 pt, with no words crossing the gutter in the measured body region.
The diagram retained its 100 pt width and the output retained two pages. This
does not establish fidelity for complex newspaper layouts or scanned columns.

The same manual was rasterized into a true scan-only PDF (no text layer).
Before the change, the adapter returned no assets, lost the diagram and most
table text, and fragmented the landscape voltage condition. The raster layout
helper now identifies complete rectangular grids, OCRs cells independently,
retries low-confidence cells at larger scale, and retains substantial non-text
regions. Unread or low-confidence grids retain their original bitmap rather
than silently dropping a cell. Detected text is excluded from figure crops.
OCR typography uses median word height per line, retaining large headings.
Sparse-text mode is tried only for a few narrow fragments with weak confidence,
and accepted only when confidence weighted by text length improves.

Real Tesseract + Argos verification retained two pages, a 3×2 editable Word table,
the values `12V` and `100 kPa`, and the diagram. Enlarging the voltage cell fixed
the initial OCR error `LDV`. Both rendered pages were visually inspected with
no overlaps or clipping; original-language Markdown also retained the Chinese
table and relative image link without translating its content. This is a simple
ruled scan, not proof for unruled/merged tables, photographs, noise or arbitrary
book layouts. The earlier OCR pass misread `检查` as `汐查` in the caption
and `启用` as `局用` in the voltage condition. Both known source errors were
corrected by the line/stroke retries below. The PDF adapter version is now 4; older parsed jobs
need a new job for parsing/translation, while existing export-only access works.

A two-page 420×595 / 595×420 PDF with Chinese prose, a ruled table and a diagram
was rendered as DOCX using hand-written reference translations. This verifies
layout only, not model quality. The latest reference output retains two pages,
all content, the table and the 100-point diagram width. Inter-block gaps are
slightly reduced for longer English text to use available page space; exact
pagination and complex page layouts are not guaranteed.

Visual validation exposed reused segment IDs after paragraph merging. IDs now
increase independently of the number of retained segments, and duplicate IDs
fail before source/translation mapping. A regression test covers merged first-
page text followed by a different second page, preventing silent text swaps.

## Scope of translation tests

Per the user's instruction, model tests use only the current Argos Chinese–English
model 1.9 on CPU. Qwen3.8-27B is not tested or called. Formatting checks and reference
translations are not presented as proof of model translation accuracy.
Terminology replacement does not guarantee fluent or accurate prose. The latest
provider translates complete sentences after substituting glossary terms with
ordinary English text. It verifies glossary phrase counts, protected codes,
numbers and SI units before accepting a result. If the model misspells a term,
it can retry with an acronym already supplied by that glossary entry, then
restore the full name. Existing literal acronyms and ambiguous shared acronyms
are excluded. Changed/missing/repeated terms or values trigger the protected-
fragment fallback. This removes the app-induced voltage/context error and
retains `12 V` in the negative voltage condition. The ABS/wheel-lockup example
still has model semantic errors. Text in raster images and
spreadsheet sheet names retains its original language.

The new column fixture exposed a protection bug for product codes directly
adjacent to Chinese characters: `传感器AC-123的` could become `AC- 123`.
ASCII code boundaries now protect the entire code instead of only its numeric
suffix. Two regression tests failed before the fix and pass after it. The real
Argos retest retained `AC-123`, `12 V`, and `100 kPa`, and produced the correct
voltage-check instruction. The provider fingerprint version changed accordingly;
unfinished jobs from an older fingerprint require a new job to translate, while
saved reviews and exports remain available.

Further real Argos diagnosis demonstrated an application-induced subject error:
fragmenting `防抱死制动系统不得在传感器故障时关闭。` produced an instruction
not to shut down the sensor, instead of the ABS. Keeping the sentence intact
produced `Antilock Braking System (ABS) may not be shut down in case of sensor
failure.` The ECU connection check also retained its subject and required order
(check the connection before enabling braking). The AUTOSAR sentence now reads
`Runtime Environment (RTE) connects Application Software Component (SWC) and
Basic Software (BSW).` after the acronym retry; its earlier fragmented result used
the noun `Connection` rather than a connecting verb. Eight new provider cases
cover this context preservation and term/code/unit/duplication/acronym guards.

These are specific quality improvements, not a semantic verifier. The ABS
definition still mistranslates wheel lockup as dying on wheels, and the ECU
low-voltage case uses "perform" where the source says "enable". The application
cannot identify all such semantic substitutions using token/terminology checks.

The latest full suite passed: **122 tests, 1 skipped**. All seven earlier Chinese fixtures
completed real Argos translation/export and LibreOffice rendering. Word and
PowerPoint cases stayed at one page; spreadsheets stayed at the source's three-
page print layout; the Chinese PDF retained its two pages and both page sizes.
The frozen Linux application also starts in light/English mode with two tasks,
no main tabs and four Settings sections. Its offline smoke check blocks network
connections while running the bundled Argos model.

The local UI/conversion/naming and parser/format cases are verified. The user has
accepted the observed Argos semantic limitations, so those are retained as
known model counterexamples rather than a release blocker. Complex/scanned book
layout and OCR accuracy remain documented limits of this implementation; this
validation does not certify arbitrary documents or future online providers.

### Excel text criteria: actual recalculation

A new Chinese XLSX fixture demonstrated a calculation failure: translated
worksheet labels with unchanged SUMIF/COUNTIF string criteria yielded **0, 0**
after LibreOffice `calculateAll()`, despite cached results still containing
**12, 1**. This was reproduced using the actual Argos outputs `controller` and
`Sensors`, with Python network connections blocked.

The writer now uses openpyxl's tokenizer only to classify literal criteria;
it patches their original spans without loading/saving through openpyxl or
rejoining whitespace-normalized tokens. Direct cell/column references in
SUMIF/COUNTIF/AVERAGEIF and the IFS variants synchronize with reviewed labels.
Ambiguous translations, collisions and targets that introduce criteria pattern
syntax are rejected before writing an output. Other formula functions, named or
external ranges, wildcards and computed criteria retain their original text.
Formula strings are not sent to the translation model.

The fixed real Argos result recalculates to **12, 1**; numeric `B1*2` remains
**24**, with its original formula unchanged. Both source and translated files
render to one page; inspection shows the labels fit and the numeric columns
retain their positions. Unrelated ZIP parts remain byte-identical. Seven
regression cases exercise criteria synchronization, nested functions, quoted
sheet names, escaped quotes, whitespace, review/re-export, conflicts and
unsupported strings. This is evidence for these cases, not a general formula
semantic verifier. Source-language Markdown conversion continues to retain the
original formula text.

The rebuilt frozen Linux worker also translated and exported this fixture with
network access blocked, using the bundled model. Its XLSX is byte-identical to
the validated development output, and an independent LibreOffice recalculation
returned **12, 1, 24**. The worker exited successfully. The frozen GUI/offline
smoke also passed with light/English defaults and the existing single-screen UI.

The first-party repo/documentation comparison is saved in
`docs/OFFICE_PARSING_RESEARCH.md`; it explains the run-level mapping and chart
dependency decisions as well as why a Markdown parser alone does not establish
format-preserving Office round trips.

### Office inline controls

A DOCX and PPTX fixture exposed missing explicit line breaks and Word tabs in
the extracted paragraph context and Markdown: `控制器\t传感器\n检查连接。`
was flattened into `控制器传感器检查连接。`. The reader now records the order
of text segments and inline controls separately, excludes tab-stop definitions
from visible text, and retains these controls in context. Markdown renders
explicit line breaks as `<br>` in prose and table cells; tabs remain separators.
The Office writer continues patching only text, preserving the original tab,
break, formatting and geometry XML. Adapter versions 1 and 2 reject continued
parsing/translation, while historical export-only access remains supported.

Both new Chinese fixtures completed original-language conversion without a
provider, then actual Argos translation with network disabled. The translated
Word and PowerPoint outputs each retained one page in LibreOffice. Both page
images were inspected: Word retains its tabbed labels, separate instruction
line and two-line table cell; PowerPoint retains the bold label followed by its
italic instruction on the next line. `AC-123` remains unchanged. Canonical XML
after masking only text nodes is identical; unrelated package parts are byte-
identical. Two format regression cases and the adapter-resume cases passed.
A further regression catches dangling inline segment IDs when SmartArt source
and cached text are bound; inline references now follow the retained IDs, and
the exact paragraph grouping includes explicit separators.

The frozen Linux worker also ran both fixtures through conversion with no API
configuration and through bundled Argos translation with network disabled. Its
source Markdown and translated Office/Markdown outputs match the inspected
development outputs byte for byte. Both worker processes exited successfully.

Additional probes did not establish a reliable improvement to the ABS semantic
failure. Adding wheel-lockup/steering/emergency-braking terminology or spaces
around substituted English terms can make the model omit qualifiers/terms or
produce incorrect fragments. These changes were not added to the shipped
glossary or provider. The existing 97-term default remains unchanged; the
counterexamples and raw model outputs are retained as failed quality evidence.

### Package relationships and final OCR source checks

DOCX/PPTX/XLSX readers and the XLSX writer now resolve main parts through the
package `officeDocument` relationship. Word linked headers/footers/notes and
workbook shared strings are also resolved through relationships. Three packages
with renamed main/header/footer/shared-string parts failed before this change
and now extract the same text and source Markdown as their conventional-name
counterparts, then round-trip reviewed text. Word ancillary Markdown headings
use the role (`Header`, `Footer`, etc.) rather than internal filenames.

Those three custom-name cases also ran real Argos export and LibreOffice
rendering. DOCX/PPTX stayed at one page; XLSX retained its original two-page print
layout, including its existing split chart. Four English page images were
inspected. Relationships, media and styles remain byte-identical. The new main
part names remain in the output; the writer does not rebuild packages through
a document library.

The local OCR comparison tested pinned `tessdata_best`, alternate language/line
modes, scaling and thresholding against the two known scan errors. The default
`tessdata_fast` remains: the best-model/full-page combination corrected the
caption but fragmented the voltage line and lost the retained diagram region.
No best-model files were added to the release.

Weak long lines now receive a cropped PSM-7 retry when both average and minimum
word confidence improve. Lines from a previously fragmented sparse-text region
can additionally retry with a small stroke-emphasis filter. Already-strong lines
are skipped; candidates retain the original page/paragraph/geometry anchors and
must retain existing numeric/product-code values and comparable text length.
This is an OCR quality heuristic, not a semantic verifier.

The final scan fixture now extracts `检查控制器和传感器之间的连接` and
`不得启用该功能` correctly. Real Argos export still retains two pages, the
editable 3×2 table, diagram, `12V` and `100 kPa`. Both output pages were inspected.
The body condition now reads that the function cannot be enabled below 12 V.
The unrelated ABS model mistranslation remains as accepted model-quality
evidence. Some OCR punctuation/script variants and difficult/noisy layouts can
still require source checking; no claim of perfect transcription is made.

Office and PDF adapter versions are both 4. Previous parsed revisions need a
new job for continued parsing/translation, while historical exports remain
accessible. The release does not call an online LLM; API/model configuration
and the existing provider boundary remain ready for a later online translation.

The final frozen Linux worker ran custom-name DOCX/PPTX/XLSX and the Chinese scan
through both source conversion and bundled Argos export. Network connections
were blocked. Conversion required no provider profile/key and left targets
unset; the frozen parser extracted the corrected caption/enable condition and
retained voltage/pressure values. All four formats exported both requested
translation outputs and both worker processes exited successfully. The frozen
UI/offline smoke retained light/English defaults, two tasks, zero main tabs,
four Settings sections and 97 glossary entries.

## Accepted local deliverable audit

| Requirement | Authoritative evidence |
| --- | --- |
| Office extraction and format preservation | Regular Simplified/Traditional fixtures, native chart fixtures, custom OPC parts, XML/ZIP invariants, actual LibreOffice rendering, review/re-export and criteria recalculation. Known Argos prose errors were accepted by the user. |
| PDF extraction and reconstruction | Actual text/scan/two-column manual cases; page sizes/counts, retained tables/figures, measured column geometry and inspected DOCX renders. Known caption/enable OCR errors corrected in source and frozen parser. Complex/noisy layouts remain documented limits. |
| Original-language Markdown task | Real UI/worker conversion and source-content assertions; no provider/key required, targets unchanged, image assets copied, inline controls retained. |
| Selected compact UI | Real Qt checks/screenshots and frozen smoke: no main tabs, icon Settings, Review from entry menu, Glossary in Settings; light/English defaults. |
| DocBridge naming | Project metadata, primary CLI, application/bundle/installer names and built Linux artifacts; legacy commands/data remain compatible. |
| Bounded local model testing | Current Argos 1.9.6/model 1.9 only, network-blocked workers; no Qwen inference or online translation calls. |
| Architecture in README | Mermaid diagram matches worker, parser/model/translation/export boundaries, OPC bindings and OCR line recovery. |

This audit closes the local deliverable under the user's updated acceptance of
Argos quality and priority on source parsing. It does not claim guaranteed OCR
or translation accuracy for arbitrary documents; these limits are preserved in
the README and the failed model probes.

Local ignored evidence:

- `.test-data/docbridge-ui/report.json`: real conversion UI/worker and screenshots.
- `.test-data/docbridge-argos/report.json`: real Argos UI/worker, Office/PDF outputs
  and LibreOffice renderings.
- `.test-data/pdf-layout/report.json`: reference-only PDF reconstruction case.
- `.test-data/pdf-columns/report.json`: additional real Argos two-column case,
  measured rendered geometry, translations and source/output page images.
- `.test-data/argos-context/diagnosis.json` and `verification.json`: real Argos
  before/after evidence for five glossary, subject and condition cases; the
  unchanged semantic counterexamples are retained rather than counted as passes.
- `.test-data/pdf-scan/before.json` and `report.json`: scan-only before/after
  evidence, reconstructed table/figure, OCR failures, translated/original
  Markdown outputs and rendered pages.
- `.test-data/office-drawings/report.json`: three real Argos native chart cases,
  nested XLSX data, English labels and rendered Office outputs.
- `.test-data/excel-formulas/report.json`: real Argos labels, old-criteria control,
  LibreOffice recalculation, formulas, original/translated page renderings.
- `.test-data/office-breaks/report.json`: actual Argos Word/PowerPoint exports,
  original-language Markdown, context controls and rendered pages.
- `.test-data/argos-context/terminology-probe.json` and
  `natural-spacing-probe.json`: failed terminology/preprocessing experiments,
  including dropped conditions and altered domain terms; no production change.
- `.test-data/office-parts/report.json`: custom OPC filenames, source conversion,
  actual Argos exports and four rendered English pages.
- `.test-data/tesseract-quality/*.json`: model provenance and rejected OCR
  alternatives, line/stroke comparisons and final source-character evidence.
- `.test-data/final-frozen/report.json`: final frozen worker, four input formats,
  source snapshots, output statuses and corrected scan source text.

## Naming and compatibility

The application, package distribution, primary command, portable build and
Windows installer use DocBridge. The internal `converter` module/command and
`CONVERTER_*` overrides remain compatible. Existing data and keyring entries
can be read; deleting a key removes both old and new service entries. Store
migration preserves history while adding the translation/conversion task field.
