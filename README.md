# Converter

A Windows desktop application for Chinese-to-English document translation.
Choose **Office only**, **Markdown only**, or **both**. Both exports use the same
reviewed translation; changing the output mode does not translate the document again.

| Input | Office output | Markdown output |
| --- | --- | --- |
| DOCX | DOCX with text patched in the original OOXML package | Markdown and images |
| PPTX | PPTX with frames, styles, and objects preserved | Markdown organized by slide, with images |
| XLSX | XLSX with formulas, charts, and images preserved | Markdown organized by sheet, with tables and images |
| Text-based or scanned PDF | Reconstructed DOCX | Markdown, tables, and images |

## Run the development version

Requires Python 3.12 x64:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m converter
```

On Linux or macOS, use `.venv/bin/python` instead. Application data is stored in
`%LOCALAPPDATA%\Converter` on Windows. Set `CONVERTER_DATA_DIR` to override this location.
The desktop interface currently uses Vietnamese labels.

### Online translation

The developer sets the **full endpoint URL** and fixed model ID in
`config/provider.json`. The endpoint must end in `/v1/chat/completions`.
Authentication header and prefix fields accommodate the service's requirements.
Do not store an API key in this file. During development, use the ignored
`config/provider.local.json` or select a configuration file through
`CONVERTER_PROVIDER_CONFIG`. Release builds bundle `config/provider.json`.

Users enter only their API key in Settings. Keys are stored using Windows
Credential Manager. If the operating system keyring is unavailable, the key can
be used temporarily for the current session. The connection check sends a short
test sentence and may incur a provider charge. The repository does not contain
a configured endpoint or model ID; supply these before using a real online service.

### Offline translation with Argos

Use the existing `translate-zh_en-1_9.argosmodel` package. For development:

```powershell
.venv\Scripts\python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -e ".[offline]"
$env:CONVERTER_ARGOS_MODEL = "D:\Models\translate-zh_en-1_9.argosmodel"
.venv\Scripts\python -m converter
```

Alternatively, place the package in `assets/models/`. It is installed locally
once. The application does not query the package index or download a replacement
model. Release builds bundle the installed model, so end users do not need to
configure Argos. The chosen model is accepted as a project requirement; no model
selection or benchmarking step is required.

### Scanned PDFs and OCR

Development installations need Tesseract on PATH with the `chi_sim`, `chi_tra`,
and `eng` language packs. Set `CONVERTER_TESSERACT` to select an executable.
Windows releases bundle Tesseract and its language packs in `assets/tesseract/`.
Pages with a text layer are read directly; scanned pages use OCR. Images inside
text-based PDFs are processed separately when needed. Review allows source
PDF/OCR text to be corrected before translation resumes.

If Tesseract is already installed, run `python scripts/setup-ocr.py` to prepare
local language packs. The script downloads from a pinned upstream revision and
verifies SHA-256 checksums.

## Usage

1. Drag and drop documents or add files, then select the rows to process.
2. Choose online or offline translation, an output mode, and a destination folder.
3. Click Translate/Resume (`Dịch file đã chọn / Tiếp tục`). Pause and cancel take
   effect after the current request or batch. Completed batches are saved so work
   can resume after restarting the application.
4. Open Review to edit individual translations. Previously exported files are
   marked as stale when their translation changes.
5. Click Re-export reviewed translation (`Xuất lại bản đã review`). This requires
   neither an API key nor new translation requests.

History, source copies, checkpoints, and assets are stored in the application
data directory. Removing a job from history deletes its internal data, while
leaving original documents and exported files intact. Existing output names are
preserved by adding a suffix to new files. If one exporter fails in Both mode,
the successful output is retained and the other error is reported separately.

## Format limitations

- Word and PowerPoint retain text runs, styles, images, tables, and relationships.
  Longer translations may change pagination or overflow text frames. Groups with
  different styles are translated separately, using paragraph context online;
  sentences with complex mixed formatting need review.
- XLSX retains formulas and numeric cells. Shared strings are cloned per cell
  when different translations are needed. Sheet names and chart/SmartArt text
  are not translated. Charts and SmartArt remain in Office files but are not
  exported as images in Markdown; the application reports these limitations.
- PDF-to-DOCX reconstructs content rather than reproducing the original layout
  or fonts exactly. Ruled tables are extracted; scanned or unruled tables and
  complex layouts need review.
- Legacy DOC/PPT/XLS, macros, encrypted files, and digitally signed Office files
  are not supported in this version.
- Markdown preserves representable document structure, not all Office formatting.

## Build for Windows

Prepare Windows x64, Python 3.12, the existing Argos package, and a complete
Tesseract distribution including its executable, DLLs, license files, and language
packs. Configure the provider before building. API keys are not included in builds.

```powershell
.\scripts\build-windows.ps1 `
  -ModelPath "D:\Models\translate-zh_en-1_9.argosmodel" `
  -TesseractPath "D:\Tesseract-OCR"
```

The script installs the CPU runtime and local Argos package, builds
`dist\Converter` using PyInstaller, and enforces an installed footprint below
2 GB. If Inno Setup 6 is on PATH or supplied through `-IsccPath`, it also creates
`dist\Converter-Setup-0.1.0.exe` and checks the installer size. Qt uses
Essentials/Widgets without WebEngine. Release distributions include
`THIRD_PARTY_NOTICES.txt`. Builds are unsigned; code signing and automatic updates
are not implemented.

After building, run `Converter.exe` on a clean Windows machine and exercise
online/offline translation, Chinese scanned PDFs, and all three output modes.
The cloud development environment runs Linux; Windows builds and installers
must be validated on Windows before release.

## Application checks

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check src tests scripts
```

Tests cover OOXML round trips, retained styles and media, cell-specific shared
strings, formulas/charts/images, all output modes, review/re-export, resume,
HTTP errors, placeholder validation, PDF tables, scanned-page OCR, and offscreen
UI startup. Fixture providers and mock HTTP validate application behavior, not
Argos model quality or connectivity to the production translation service.
The scanned OCR test runs when Tesseract and a suitable test font are available.

See [docs/DESIGN.md](docs/DESIGN.md) for the detailed design (in Vietnamese).
