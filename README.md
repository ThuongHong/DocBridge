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
The desktop interface defaults to **Light** mode and **English**. Use the **⚙ Settings**
icon to switch between Light/Dark or English/Tiếng Việt. These choices are saved
and applied immediately without restarting.

### Online translation

Open **⚙ Settings → Online service** and enter a service name, **API URL**,
**model ID**, and API key. Any service that implements the OpenAI-compatible
**Chat Completions** request/response format can be configured. The URL can be a
service root, a versioned base URL such as `https://host/v1`, or a full
`/chat/completions` endpoint. Base URLs are expanded before saving; query
parameters are retained for endpoints that require them.

**Advanced options** expose the authentication header/prefix, characters per
batch, maximum output tokens, context window, token safety margin, timeout,
and retry count. For example, use
`Authorization` with `Bearer `, or `api-key` with an empty prefix. Turn off
**Use API authentication** for services that do not require a key. HTTPS is
required except for services on localhost. **Test connection** uses the current
URL and model and sends a short sentence, which may incur a provider charge.

The configuration is saved in the application's data directory as `provider.json`,
without the API key. Keys use the operating system keyring; when unavailable,
a key can be used temporarily in the current session. **Save service** validates
the configuration; closing Settings also retains incomplete configuration drafts.
Settings do not need to contain a working provider to build or use offline mode.

`config/provider.json` supplies initial defaults. If no saved user configuration
exists, `CONVERTER_PROVIDER_CONFIG` or the ignored `config/provider.local.json` can
supply development defaults. Saved user settings take precedence on subsequent
starts; passing an explicit path to `ProviderConfig.load` still selects that file.
Never put API keys in these JSON files or in a build.

### Context and output limits

Set **Context window** to the actual limit of the selected model. The initial
value of 8192 is a configuration default, not detected model metadata. Each
request reserves **Maximum output tokens** and **Safety margin** (default 512)
before allocating input space. A valid configuration leaves at least 1024
estimated input tokens for the prompt and source text.

For arbitrary providers without an exact tokenizer, the application conservatively
estimates input using the UTF-8 byte size of the full serialized messages, including
the system instruction, source text, optional context, placeholders, JSON, and chat
framing. This is an estimate rather than an exact vendor token count; it can create
more requests than a model-specific tokenizer. Runtime overflow handling remains
necessary if the configured model limit or tokenizer assumptions differ.

The online provider splits batches before sending when they exceed this budget.
If one segment is too large, optional context is removed first, then the complete
source is split without cutting glossary phrases, product codes, numbers or URLs.
API context-limit errors (recognized HTTP 400 errors or HTTP 413) and truncated
output (`finish_reason=length`) trigger further splitting. Unrelated errors retain
their normal retry/error behavior. Partial JSON is discarded, and every segment ID
and protected value must validate before a translated batch is saved. If even the
smallest source cannot fit, the app stops with an actionable error. Pause/cancel
is checked between split requests; previously saved batches remain available.

### Offline translation with Argos

Use the existing `translate-zh_en-1_9.argosmodel` package. The download link to the
[Argos Translate Package Index](https://www.argosopentech.com/argospm/index/) is also
available in **⚙ Settings → Offline & OCR**. Choose a Chinese → English
`.argosmodel` package there, or leave the field empty to use the bundled package.
The selected path is saved; selected packages are installed in an isolated local
cache so they take precedence over older models. Changes to the selected package
change the translation profile, preventing incompatible job resumes. The link does
not download a model automatically. Offline mode also requires the Argos runtime.
For development:

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
   **Add documents ▼ → Add folder** scans subfolders for DOCX, PPTX, XLSX and PDF, skips Office lock
   files (`~$...`) and the application's internal job/output directories, and selects
   all imported rows.
2. Choose online or offline translation, an output mode, and a destination folder.
   The folder icon inside the destination field opens the folder picker.
3. Click **Translate / Resume**. The primary action becomes **Pause** while running;
   **Cancel** is in the `⋯` menu. Pause and cancel take
   effect after the current request or batch. Completed batches are saved so work
   can resume after restarting the application.
4. Double-click a document or use **⋯ → Review translation** to edit translations. Previously exported files are
   marked as stale when their translation changes.
5. Choose **⋯ → Re-export reviewed translation**. This requires
   neither an API key nor new translation requests.

History, source copies, checkpoints, and assets are stored in the application
data directory. Removing a job from history deletes its internal data, while
leaving original documents and exported files intact. Existing output names are
preserved by adding a suffix to new files. If one exporter fails in Both mode,
the successful output is retained and the other error is reported separately.

## Built-in terminology

The Glossary tab starts with **97 editable automotive/Bosch/AUTOSAR term pairs**.
The Chinese phrases are curated for this app; English names are checked against
public official sources. This is not an official Bosch or AUTOSAR bilingual
glossary. See [source details](docs/GLOSSARY_SOURCES.md) or **Glossary sources**
in the app for provenance.

Search, edit, add or remove terms, and use **Apply glossary during translation**
to enable or disable replacements without losing your entries. **Add missing
automotive terms** restores absent entries and preserves custom translations.
Existing user terminology overrides a starter-pack entry with the same source;
deleted entries remain deleted after restarting. Changing the glossary during an
unfinished translation requires a new job to keep its profile consistent.

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

## Build for Linux

Use Python 3.12, install the CPU PyTorch and `[offline,build]` dependencies,
prepare the local `.argosmodel`, and run `scripts/setup-ocr.py` as described above.
Tesseract must be installed on the target Linux machine. To bundle the installed
model and runtime:

```bash
mkdir -p build/argos-packages
ARGOS_PACKAGES_DIR="$PWD/build/argos-packages" ARGOS_DEVICE_TYPE=cpu \
  .venv/bin/python -c 'from pathlib import Path; from argostranslate import package; package.install_from_path(Path("assets/models/translate-zh_en-1_9.argosmodel"))'
CONVERTER_BUNDLE_OFFLINE=1 \
CONVERTER_BUNDLE_MODELS="$PWD/build/argos-packages" \
CONVERTER_BUNDLE_TESSERACT="$PWD/assets/tesseract" \
  .venv/bin/python -m PyInstaller --noconfirm --clean packaging/converter.spec
.venv/bin/python scripts/collect-notices.py dist/Converter/THIRD_PARTY_NOTICES.txt
.venv/bin/python scripts/check-size.py dist/Converter
```

Start with `dist/Converter/Converter`. Keep `_internal` beside the executable.
For a startup and real offline inference check with Python network connections
blocked, use an isolated data directory:

```bash
QT_QPA_PLATFORM=offscreen CONVERTER_DATA_DIR="$PWD/.test-data/release-smoke" \
  dist/Converter/Converter --smoke-test "$PWD/build/release-smoke.json" --offline-smoke
```

See [actual local model results](docs/OFFLINE_SMOKE.md) for the real Chinese → English
smoke test, including translation errors that still require review. Portability
to other Linux distributions has not been validated.

## Build for Windows

Prepare Windows x64, Python 3.12, the existing Argos package, and a complete
Tesseract distribution including its executable, DLLs, license files, and language
packs. Users configure their provider in Settings after installation. API keys are
not included in builds.

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
