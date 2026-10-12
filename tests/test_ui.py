from PySide6.QtWidgets import QApplication

from converter.ui import MainWindow


def test_desktop_import_review_and_modes(word_file, store, provider, tmp_path, monkeypatch):
    from converter.pipeline import Pipeline

    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.add_paths([str(word_file)])
    assert window.job_table.rowCount() == 1
    assert window.mode_combo.count() == 3
    job = store.list()[0]["id"]
    Pipeline(store).run(job, provider, "both", tmp_path / "output")
    window.load_review(job)
    assert window.review_table.rowCount() > 0
    window.review_table.item(0, 2).setText("User reviewed heading")
    window.save_review()
    assert store.load_document(job).segments[0].target == "User reviewed heading"
    assert store.get(job)["exports"]["office"]["status"] == "stale"
    window.show()
    app.processEvents()
    window.close()


def test_importing_batch_keeps_all_files_selected(word_file, store, tmp_path, monkeypatch):
    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.add_paths([str(word_file), str(word_file)])
    assert len(window.selected_ids()) == 2
    window.refresh_jobs()
    assert len(window.selected_ids()) == 2
    app.processEvents()
    window.close()
