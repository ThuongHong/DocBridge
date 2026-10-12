"""Load the bundled, editable terminology starter pack."""

import json
from importlib.resources import files


def automotive_pack() -> dict:
    resource = files("converter").joinpath("data/automotive_glossary.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def default_glossary() -> dict[str, str]:
    return {term["source"]: term["target"] for term in automotive_pack()["terms"]}
