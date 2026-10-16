from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import OrderedDict
from contextlib import closing
from pathlib import Path

from .markdown import render_markdown
from .models import OUTPUT_MODES, Document, Segment, file_hash
from .office import OFFICE_ADAPTER_VERSION, read_office, write_office
from .pdf import PDF_ADAPTER_VERSION, read_pdf, write_pdf_docx
from .providers import TranslationError, split_text
from .store import Store


class Paused(Exception):
    pass


class Cancelled(Exception):
    pass


class Pipeline:
    def __init__(self, store: Store, progress=None, control=None):
        self.store = store
        self.progress = progress or (lambda *args: None)
        self.control = control or (lambda: None)

    def parse(self, job_id: str, ocr_language: str) -> Document:
        source = Path(self.store.get(job_id)["source"])
        saved = self.store.document_path(job_id)
        if saved.exists():
            doc = self.store.load_document(job_id)
            version = PDF_ADAPTER_VERSION if source.suffix.lower() == ".pdf" else OFFICE_ADAPTER_VERSION
            if file_hash(source) != doc.source_hash or doc.adapter_version != version:
                raise ValueError("File nguồn hoặc adapter đã đổi; cần tạo job mới.")
            return doc
        self.store.update(job_id, status="parsing", error="")
        self.progress(job_id, "Đang phân tích tài liệu", 0, 0)
        assets = self.store.job_dir(job_id) / "assets"
        self.control()
        if source.suffix.lower() == ".pdf":
            doc = read_pdf(
                source,
                assets,
                language=ocr_language,
                progress=lambda message: self.progress(job_id, message, 0, 0),
                control=self.control,
            )
        else:
            doc = read_office(source, assets)
        self.store.save_document(job_id, doc)
        return doc

    def translate(self, job_id: str, provider, glossary: dict, ocr_language: str) -> Document:
        doc = self.parse(job_id, ocr_language)
        job = self.store.get(job_id)
        profile = provider.fingerprint(glossary)
        if (
            job["profile"]
            and job["profile"] != profile
            and any(s.target is not None and s.target != s.source for s in doc.segments)
        ):
            raise ValueError(
                "Provider/model/glossary đã đổi. Tạo job mới để dịch; bản review cũ được giữ."
            )
        self.store.update(job_id, status="translating", profile=profile, error="")
        if hasattr(provider, "set_control"):
            provider.set_control(self.control)
        if not doc.segments:
            raise ValueError("Không trích xuất được text. Hãy kiểm tra file hoặc kết quả OCR.")
        pending = [s for s in doc.segments if s.target is None]
        pending_count = len(pending)
        aliases = {}
        # Job-local reuse is scoped by the full provider/model/glossary fingerprint
        # and exact context/style. Never seed it from reviewed per-cell targets.
        # Bound both key count and key text; independent cell Segment objects remain.
        if doc.format == "xlsx":
            representatives, keys, key_chars = [], OrderedDict(), 0
            for index, segment in enumerate(pending):
                if index % 4096 == 0:
                    self.control()
                key = (profile, segment.source, segment.context,
                       json.dumps(segment.style, sort_keys=True))
                prior = keys.get(key)
                if prior is not None:
                    keys.move_to_end(key)
                    aliases.setdefault(prior.id, []).append(segment)
                else:
                    representatives.append(segment)
                    size = sum(len(value) for value in key)
                    if size <= 4 * 1024 * 1024:
                        while keys and (len(keys) >= 4096 or key_chars + size > 4 * 1024 * 1024):
                            old_key, _ = keys.popitem(last=False)
                            key_chars -= sum(len(value) for value in old_key)
                        keys[key] = segment
                        key_chars += size
            pending = representatives
        # Clear the parsing label before packing or waiting for the first API
        # response; neither step necessarily produces a completed segment yet.
        self.progress(job_id, "Đang dịch", len(doc.segments) - pending_count, len(doc.segments))
        # Batch limits include the surrounding context and never rely on output mode.
        batches, current, count = [], [], 0
        for segment in pending:
            size = len(segment.source) + min(len(segment.context), 2000)
            if current and count + size > provider.batch_chars:
                batches.append(current)
                current, count = [], 0
            current.append(segment)
            count += size
        if current:
            batches.append(current)
        if hasattr(provider, "translate_batches"):
            # Online provider owns token/output packing and bounded concurrency.
            batches = [pending] if pending else []

        def checkpoint(values):
            for sid, text in values.items():
                if sid not in batch_ids or sid in result:
                    raise TranslationError("Provider trả về thiếu/trùng segment.")
                if not isinstance(text, str) or not text.strip():
                    raise TranslationError("Provider trả về đoạn rỗng.")
            result.update(values)
            for sid, text in values.items():
                lookup[sid].target = text
                for duplicate in aliases.get(sid, []):
                    duplicate.target = text
            doc.revision += 1
            self.store.save_document(job_id, doc)
            done = sum(s.target is not None for s in doc.segments)
            self.progress(job_id, "Đang dịch", done, len(doc.segments))

        lookup = doc.by_id()
        for batch in batches:
            self.control()
            # Extremely long XML text nodes are split for translation, not for Office mapping.
            result = {}
            batch_ids = {segment.id for segment in batch}
            normal = [
                s for s in batch
                if getattr(provider, "handles_long_segments", False)
                or len(s.source) <= provider.batch_chars // 2
            ]
            if normal:
                if hasattr(provider, "translate_batches"):
                    with closing(provider.translate_batches(normal, glossary)) as parts:
                        for part in parts:
                            checkpoint(part)
                else:
                    checkpoint(provider.translate(normal, glossary))
            for segment in batch:
                if segment in normal:
                    continue
                chunks = split_text(segment.source, max(100, provider.batch_chars // 3))
                values = []
                for i, chunk in enumerate(chunks):
                    self.control()
                    item = Segment(f"{segment.id}_{i}", chunk, context=chunk)
                    values.append(provider.translate([item], glossary)[item.id])
                checkpoint({segment.id: " ".join(values)})
            if set(result) != {segment.id for segment in batch}:
                raise TranslationError("Provider trả về thiếu/trùng segment.")
        self.store.update(job_id, status="review")
        self.control()
        return doc

    def run(
        self,
        job_id: str,
        provider,
        mode: str,
        output_dir: Path,
        glossary: dict | None = None,
        ocr_language="chi_sim+chi_tra+eng",
        export_only=False,
        operation="translate",
        excel_layout="preserve",
    ):
        if operation not in {"translate", "convert"}:
            raise ValueError("Tác vụ không hợp lệ.")
        if operation == "convert":
            mode = "markdown"
        if mode not in OUTPUT_MODES:
            raise ValueError("Chế độ xuất không hợp lệ.")
        self.store.update(job_id, operation=operation, mode=mode, output_dir=str(output_dir), error="")
        try:
            if export_only:
                doc = self.store.load_document(job_id)
            elif operation == "convert":
                doc = self.parse(job_id, ocr_language)
            else:
                doc = self.translate(job_id, provider, glossary or {}, ocr_language)
            if operation != "convert" and not doc.complete():
                raise ValueError("Còn đoạn chưa dịch; tiếp tục dịch trước khi xuất.")
            return self.export(job_id, doc, mode, output_dir, source=operation == "convert", excel_layout=excel_layout)
        except Paused:
            self.store.update(job_id, status="paused")
            return {}
        except Cancelled:
            self.store.update(job_id, status="cancelled")
            return {}
        except Exception as exc:
            self.store.update(job_id, status="failed", error=str(exc))
            raise

    def export(
        self, job_id: str, doc: Document, mode: str, output_dir: Path, *, source=False, excel_layout="preserve"
    ) -> dict:
        if source:
            mode = "markdown"
        if file_hash(Path(doc.source_path)) != doc.source_hash:
            raise ValueError("File nguồn đã thay đổi; tạo job mới trước khi xuất.")
        self.store.update(job_id, status="exporting")
        self.progress(job_id, "Đang xuất file", len(doc.segments), len(doc.segments))
        output_dir.mkdir(parents=True, exist_ok=True)
        job = self.store.get(job_id)
        stem = Path(job["name"]).stem + ("" if source else ".en")
        basename = stem
        requested = [kind for kind in ["office", "markdown"] if mode in {kind, "both"}]
        result = {
            kind: {"status": "pending" if kind in requested else "not_requested"}
            for kind in ["office", "markdown"]
        }
        ext = ".docx" if doc.format == "pdf" else "." + doc.format
        # Allocate one basename for Both; existing user files are never overwritten.
        suffixes = [ext if kind == "office" else ".md" for kind in requested]
        index = 1
        while (
            any((output_dir / (basename + suffix)).exists() for suffix in suffixes)
            or (output_dir / (basename + ".assets")).exists()
        ):
            basename = stem + f"-{index}"
            index += 1
        for kind in requested:
            self.control()
            target = output_dir / (basename + (ext if kind == "office" else ".md"))
            descriptor, temporary = tempfile.mkstemp(
                dir=output_dir, prefix=".converter-", suffix=target.suffix
            )
            os.close(descriptor)
            asset_target = output_dir / (basename + ".assets")
            temp_assets = None
            try:
                if kind == "office":
                    writer = write_pdf_docx if doc.format == "pdf" else write_office
                    if doc.format == "pdf":
                        writer(doc, Path(temporary))
                    else:
                        writer(doc, Path(temporary), excel_layout=excel_layout)
                    if doc.coverage:
                        self.store.save_document(job_id, doc)
                else:
                    text = render_markdown(doc, asset_target.name, source=source)
                    if doc.format == "xlsx" and not source:
                        from .excel_coverage import audit_markdown, coverage_warning

                        coverage = audit_markdown(doc, text)
                        if doc.coverage:
                            doc.coverage["markdown"] = coverage
                        else:
                            doc.coverage = {**coverage, "output": "markdown"}
                        warning = coverage_warning(coverage).replace("Excel coverage:", "Excel Markdown coverage:")
                        doc.warnings = [w for w in doc.warnings if not w.startswith("Excel Markdown coverage:")]
                        doc.warnings.append(warning)
                        self.store.save_document(job_id, doc)
                    if doc.assets:
                        temp_assets = Path(
                            tempfile.mkdtemp(dir=output_dir, prefix=".converter-assets-")
                        )
                        for name, path in doc.assets.items():
                            shutil.copy2(path, temp_assets / Path(name).name)
                        os.rename(temp_assets, asset_target)
                    Path(temporary).write_text(text, encoding="utf-8")
                os.replace(temporary, target)
                result[kind] = {"status": "done", "path": str(target), "revision": doc.revision}
            except Exception as exc:
                if kind == "markdown" and asset_target.exists():
                    shutil.rmtree(asset_target)
                result[kind] = {"status": "failed", "error": str(exc)}
            finally:
                Path(temporary).unlink(missing_ok=True)
                if temp_assets and temp_assets.exists():
                    shutil.rmtree(temp_assets)
            # Persist success before attempting the second exporter or honoring pause/cancel.
            self.store.update(job_id, exports=result)
        failed = [item["error"] for item in result.values() if item["status"] == "failed"]
        state = (
            "partial"
            if failed and any(item["status"] == "done" for item in result.values())
            else "failed"
            if failed
            else "done_warnings"
            if doc.warnings or any(s.warning for s in doc.segments)
            else "done"
        )
        self.store.update(job_id, status=state, exports=result, error="\n".join(failed))
        return result

    def report(self, job_id: str, target: Path):
        from .models import atomic_text

        doc = self.store.load_document(job_id)
        job = self.store.get(job_id)
        atomic_text(
            target,
            json.dumps(
                {
                    "source": job["name"],
                    "revision": doc.revision,
                    "warnings": doc.warnings,
                    "exports": job["exports"],
                    "segments": len(doc.segments),
                    "coverage": doc.coverage,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
