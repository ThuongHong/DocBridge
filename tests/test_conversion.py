import multiprocessing as mp
import sqlite3
from pathlib import Path

import pytest

from converter.pipeline import Pipeline
from converter.store import Store
from converter.worker import run_jobs


@pytest.mark.parametrize("source_fixture", ["word_file", "slides_file", "spreadsheet", "text_pdf"])
def test_conversion_exports_source_without_marking_it_translated(
    source_fixture, request, store, tmp_path
):
    source = request.getfixturevalue(source_fixture)
    job = store.add(source)
    result = Pipeline(store).run(
        job, None, "both", tmp_path / "output", ocr_language="eng", operation="convert"
    )
    output = Path(result["markdown"]["path"])
    assert output.name == source.stem + ".md"
    assert result["office"]["status"] == "not_requested"
    doc = store.load_document(job)
    assert all(segment.target is None for segment in doc.segments)
    assert store.get(job)["operation"] == "convert"
    text = output.read_text()
    assert any(segment.source.strip() in text for segment in doc.segments)
    for asset in doc.assets:
        assert (output.with_suffix(".assets") / asset).exists()


def test_convert_after_translation_uses_source_and_keeps_targets(word_file, store, provider, tmp_path):
    job = store.add(word_file)
    pipeline = Pipeline(store)
    pipeline.run(job, provider, "both", tmp_path / "output")
    before = store.load_document(job)
    calls = provider.calls
    result = pipeline.run(job, None, "markdown", tmp_path / "output", operation="convert")
    assert provider.calls == calls
    text = Path(result["markdown"]["path"]).read_text()
    assert "测试文本" in text and "English 测试文本" not in text
    assert store.load_document(job).to_dict() == before.to_dict()
    pipeline.run(job, provider, "markdown", tmp_path / "output")
    assert provider.calls == calls
    assert store.get(job)["operation"] == "translate"


def test_spawned_conversion_needs_no_provider_or_key_and_can_reexport(word_file, store, tmp_path):
    context = mp.get_context("spawn")
    job = store.add(word_file)
    for export_only in (False, True):
        events = context.Queue()
        options = {
            "operation": "convert" if not export_only else "translate",
            "provider": "online",  # No profile/key supplied; creation would fail if called.
            "mode": "both",
            "output_dir": str(tmp_path / "output"),
            "ocr_language": "eng",
            "export_only": export_only,
        }
        pause, cancel = context.Event(), context.Event()
        process = context.Process(
            target=run_jobs,
            args=(str(store.root), [job], options, "", events, pause, cancel),
        )
        try:
            process.start()
            process.join(timeout=20)
            assert not process.is_alive()
            assert process.exitcode == 0
            result = store.get(job)
            assert result["status"] == "done_warnings", result["error"]
            assert result["provider"] == ""
            assert result["exports"]["markdown"]["status"] == "done"
            assert result["exports"]["office"]["status"] == "not_requested"
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            events.close()


def test_existing_store_migrates_job_operation_without_losing_history(word_file, tmp_path):
    root = tmp_path / "legacy"
    store = Store(root)
    job = store.add(word_file)
    with sqlite3.connect(store.path) as db:
        db.execute("ALTER TABLE jobs DROP COLUMN operation")
    migrated = Store(root)
    assert migrated.get(job)["name"] == word_file.name
    assert migrated.get(job)["operation"] == "translate"
