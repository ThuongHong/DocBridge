"""Install pinned Chinese/English OCR data for the local development environment."""

import argparse
import hashlib
import urllib.request
from pathlib import Path

REVISION = "87416418657359cb625c412a48b6e1d6d41c29bd"
CHECKSUMS = {
    "chi_sim": "a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730",
    "chi_tra": "529c5b5797d64b126065cd55f2bb4c7fd7b15790798091b1ff259941a829330b",
    "eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
}
parser = argparse.ArgumentParser()
parser.add_argument("--directory", type=Path, default=Path("assets/tesseract"))
args = parser.parse_args()
(args.directory / "tessdata").mkdir(parents=True, exist_ok=True)
base = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{REVISION}"
for language, expected in CHECKSUMS.items():
    target = args.directory / "tessdata" / f"{language}.traineddata"
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
        continue
    data = urllib.request.urlopen(f"{base}/{language}.traineddata", timeout=60).read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(
            f"Checksum verification failed for {language}; existing file left unchanged"
        )
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(target)
license_file = args.directory / "LICENSE"
if not license_file.exists():
    license_file.write_bytes(urllib.request.urlopen(f"{base}/LICENSE", timeout=30).read())
print("OCR data installed: chi_sim, chi_tra, eng. A Tesseract executable is required separately.")
