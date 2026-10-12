"""Enforce the product's 2 GB artifact limit; no model evaluation."""

import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("path", type=Path)
args = parser.parse_args()
if not args.path.exists():
    raise SystemExit(f"Artifact does not exist: {args.path}")
size = (
    sum(path.stat().st_size for path in args.path.rglob("*") if path.is_file())
    if args.path.is_dir()
    else args.path.stat().st_size
)
print(f"{args.path}: {size:,} bytes")
if size >= 2_000_000_000:
    raise SystemExit(
        "Artifact exceeds the 2 GB release limit. Remove duplicated/build-only resources."
    )
