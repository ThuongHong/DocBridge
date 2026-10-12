# Argos offline models

Download packages from the [Argos Translate Package Index](https://www.argosopentech.com/argospm/index/).
Choose Chinese → English (zh → en); this project originally uses
`translate-zh_en-1_9.argosmodel`.

For development, place the package in this directory, set `CONVERTER_ARGOS_MODEL`,
or choose it in **⚙ Settings → Offline & OCR → Offline model**. The Settings panel
also includes the download link. Offline translation requires the Argos runtime
(`converter-desktop[offline]`). Do not commit model files to Git.

Windows packaging installs a supplied local model into the application bundle.
The build does not download a model automatically. A selected user package is
installed into an isolated application cache and takes precedence over a bundled
model. The source package's content hash is included in the job profile so a
translation cannot silently resume with a different selected model.
