"""Include installed package license texts and bundled resource notices in the release."""

import argparse
import importlib.metadata
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
texts = []
for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata.get("Name", "")):
    name = dist.metadata.get("Name", "unknown")
    texts.append(f"\n{'=' * 72}\n{name} {dist.version}\n")
    for entry in dist.files or []:
        if any(token in entry.name.lower() for token in ["license", "copying", "notice"]):
            path = Path(dist.locate_file(entry))
            if path.is_file() and path.stat().st_size < 2_000_000:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
for directory in [
    Path("build/argos-packages"),
    Path(os.environ.get("CONVERTER_BUNDLE_TESSERACT", "assets/tesseract")),
]:
    if directory.exists():
        for path in directory.rglob("*"):
            if path.is_file() and any(
                token in path.name.lower() for token in ["license", "copying", "notice", "readme"]
            ):
                texts.append(
                    f"\n{path.name}\n" + path.read_text(encoding="utf-8", errors="replace")
                )
args.output.write_text("\n".join(texts), encoding="utf-8")
