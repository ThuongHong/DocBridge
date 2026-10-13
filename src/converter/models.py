from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SUPPORTED = {".docx", ".pptx", ".xlsx", ".pdf"}
OUTPUT_MODES = {"office", "markdown", "both"}


@dataclass
class Segment:
    id: str
    source: str
    anchor: dict = field(default_factory=dict)
    target: str | None = None
    context: str = ""
    style: dict = field(default_factory=dict)
    warning: str = ""

    @property
    def text(self) -> str:
        return self.source if self.target is None else self.target


@dataclass
class Block:
    kind: str
    segments: list[str] = field(default_factory=list)
    children: list[Block] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> Block:
        return cls(
            kind=data["kind"],
            segments=data.get("segments", []),
            children=[cls.from_dict(child) for child in data.get("children", [])],
            meta=data.get("meta", {}),
        )


@dataclass
class Document:
    source_path: str
    source_hash: str
    format: str
    segments: list[Segment] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assets: dict[str, str] = field(default_factory=dict)
    revision: int = 0
    adapter_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Document:
        return cls(
            **{key: value for key, value in data.items() if key not in {"segments", "blocks"}},
            segments=[Segment(**item) for item in data.get("segments", [])],
            blocks=[Block.from_dict(item) for item in data.get("blocks", [])],
        )

    def save(self, path: Path) -> None:
        atomic_text(path, json.dumps(self.to_dict(), ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, path: Path) -> Document:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def by_id(self) -> dict[str, Segment]:
        lookup = {segment.id: segment for segment in self.segments}
        if len(lookup) != len(self.segments):
            raise ValueError("Segment IDs trùng; tạo job mới để phân tích lại.")
        return lookup

    def add_segment(self, text: str, anchor: dict, **kwargs) -> Segment:
        if not hasattr(self, "_next_segment_id"):
            self._next_segment_id = 1 + max(
                (int(s.id[1:]) for s in self.segments if s.id.startswith("s") and s.id[1:].isdigit()),
                default=-1,
            )
        segment = Segment(f"s{self._next_segment_id:06d}", text, anchor, **kwargs)
        self._next_segment_id += 1
        self.segments.append(segment)
        return segment

    def complete(self) -> bool:
        return all(segment.target is not None for segment in self.segments)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, content: str) -> None:
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".converter-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
