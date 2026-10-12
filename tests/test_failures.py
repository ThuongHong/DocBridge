from pathlib import Path

import pytest

from converter.models import file_hash
from converter.pipeline import Paused, Pipeline


def test_partial_export_preserves_success_and_retry_does_not_translate(
    word_file, store, provider, tmp_path, monkeypatch
):
    job = store.add(word_file)
    pipeline = Pipeline(store)
    original = __import__("converter.pipeline", fromlist=["write_office"]).write_office

    def fail(*args):
        raise OSError("disk write failure")

    monkeypatch.setattr("converter.pipeline.write_office", fail)
    result = pipeline.run(job, provider, "both", tmp_path / "output")
    assert result["office"]["status"] == "failed"
    assert result["markdown"]["status"] == "done"
    assert store.get(job)["status"] == "partial"
    calls = provider.calls
    monkeypatch.setattr("converter.pipeline.write_office", original)
    pipeline.run(job, None, "office", tmp_path / "output", export_only=True)
    assert provider.calls == calls


def test_failed_batch_is_resumable(word_file, store, provider, tmp_path):
    job = store.add(word_file)
    provider.batch_chars = 30
    method = provider.translate

    def fail_second(segments, glossary):
        if provider.calls == 1:
            raise RuntimeError("provider interrupted")
        return method(segments, glossary)

    provider.translate = fail_second
    with pytest.raises(RuntimeError):
        Pipeline(store).run(job, provider, "both", tmp_path / "output")
    checkpoint = store.load_document(job)
    saved = {s.id: s.target for s in checkpoint.segments if s.target is not None}
    assert saved and not checkpoint.complete()
    provider.translate = method
    Pipeline(store).run(job, provider, "both", tmp_path / "output")
    result = store.load_document(job).by_id()
    assert all(result[sid].target == value for sid, value in saved.items())
    assert store.get(job)["status"] == "done_warnings"


def test_pause_has_no_false_completion(word_file, store, provider, tmp_path):
    job = store.add(word_file)

    def pause():
        raise Paused()

    Pipeline(store, control=pause).run(job, provider, "both", tmp_path / "output")
    assert store.get(job)["status"] == "paused"
    assert provider.calls == 0
    assert not (tmp_path / "output").exists()


def test_original_is_not_overwritten(word_file, store, provider, tmp_path):
    before = file_hash(word_file)
    job = store.add(word_file)
    output = tmp_path / "output"
    output.mkdir()
    existing = output / (word_file.stem + ".en.docx")
    existing.write_text("USER FILE", encoding="utf-8")
    result = Pipeline(store).run(job, provider, "office", output)
    assert existing.read_text() == "USER FILE"
    assert Path(result["office"]["path"]).name.endswith(".en-1.docx")
    assert file_hash(word_file) == before


def test_changed_source_blocks_resume(word_file, store, provider, tmp_path):
    job = store.add(word_file)
    pipeline = Pipeline(store)
    pipeline.parse(job, "eng")
    Path(store.get(job)["source"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="đổi"):
        pipeline.run(job, provider, "markdown", tmp_path / "output")
    assert provider.calls == 0


def test_pdf_source_review_invalidates_previous_translation(text_pdf, store, provider, tmp_path):
    job = store.add(text_pdf)
    Pipeline(store).run(job, provider, "both", tmp_path / "output", ocr_language="eng")
    doc = store.load_document(job)
    sid = doc.segments[0].id
    store.revise(job, {}, {sid: "Corrected OCR"})
    assert store.load_document(job).by_id()[sid].target is None
    assert store.get(job)["exports"]["office"]["status"] == "stale"
