from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from pathlib import Path

from .models import SUPPORTED, Document


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "jobs.sqlite3"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', provider TEXT NOT NULL DEFAULT '',
                profile TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL DEFAULT 'both',
                output_dir TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                exports TEXT NOT NULL DEFAULT '{}',
                created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def add(self, source: Path) -> str:
        source = source.resolve()
        if source.suffix.lower() not in SUPPORTED:
            raise ValueError("Chỉ hỗ trợ DOCX, PPTX, XLSX và PDF.")
        if not source.is_file():
            raise ValueError("Không tìm thấy file nguồn.")
        job_id = uuid.uuid4().hex
        directory = self.job_dir(job_id)
        directory.mkdir(parents=True)
        copy = directory / ("source" + source.suffix.lower())
        shutil.copy2(source, copy)
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs(id,name,source) VALUES (?,?,?)", (job_id, source.name, str(copy))
            )
        return job_id

    def job_dir(self, job_id: str) -> Path:
        # Internal ids are hex UUIDs. Never allow an imported value to escape the store.
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise ValueError("Job ID không hợp lệ.")
        return self.root / "jobs" / job_id

    def document_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "document.json"

    def get(self, job_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Không tìm thấy job.")
        result = dict(row)
        result["exports"] = json.loads(result["exports"])
        return result

    def list(self) -> list[dict]:
        with self.connect() as db:
            ids = [
                row[0] for row in db.execute("SELECT id FROM jobs ORDER BY created DESC,rowid DESC")
            ]
        return [self.get(job_id) for job_id in ids]

    def update(self, job_id: str, **changes):
        allowed = {"status", "provider", "profile", "mode", "output_dir", "error", "exports"}
        if not set(changes) <= allowed:
            raise ValueError("Unknown job fields")
        if "exports" in changes:
            changes["exports"] = json.dumps(changes["exports"], ensure_ascii=False)
        with self.connect() as db:
            clause = ",".join(f"{key}=?" for key in changes)
            db.execute(
                f"UPDATE jobs SET {clause},updated=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
                [*changes.values(), job_id],
            )

    def save_document(self, job_id: str, doc: Document):
        doc.save(self.document_path(job_id))

    def load_document(self, job_id: str) -> Document:
        return Document.load(self.document_path(job_id))

    def revise(
        self, job_id: str, translations: dict[str, str], sources: dict[str, str] | None = None
    ):
        doc = self.load_document(job_id)
        lookup = doc.by_id()
        for sid, text in translations.items():
            if sid not in lookup:
                raise ValueError("Segment không tồn tại.")
            if not text.strip() and lookup[sid].source.strip():
                raise ValueError("Bản dịch không được để trống.")
            lookup[sid].target = text
        if sources:
            if doc.format != "pdf":
                raise ValueError("Chỉ cho sửa text nguồn OCR/PDF.")
            for sid, text in sources.items():
                if lookup[sid].source != text:
                    lookup[sid].source = text
                    lookup[sid].context = text
                    # A source correction invalidates its translation unless explicitly reviewed.
                    if sid not in translations:
                        lookup[sid].target = None
        doc.revision += 1
        self.save_document(job_id, doc)
        exports = self.get(job_id)["exports"]
        for value in exports.values():
            if isinstance(value, dict) and value.get("status") == "done":
                value["status"] = "stale"
        self.update(job_id, status="review", exports=exports, error="")

    def recover(self):
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET status='paused' WHERE status IN ('parsing','translating','exporting')"
            )

    def delete(self, job_id: str):
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
        with self.connect() as db:
            db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
