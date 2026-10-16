import json
import shutil
from pathlib import Path

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel

from converter.config import load_preferences, save_preferences
from converter.glossary import default_glossary
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


def test_settings_switch_language_and_theme_without_losing_review(
    word_file, store, provider, tmp_path, monkeypatch
):
    from converter.pipeline import Pipeline

    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    assert window.theme == "light" and window.language == "en"
    assert window.windowTitle() == "DocBridge"
    assert app.palette().color(QPalette.ColorRole.Window).lightness() > 200
    assert window.centralWidget() == window.documents_page
    assert window.settings_tabs.count() == 4
    assert window.settings_tabs.widget(3) == window.glossary_page
    assert window.settings_button.accessibleName() == "Settings"
    window.settings_button.click()
    assert window.settings_dialog.isVisible()
    window.add_paths([word_file])
    job = window.selected_ids()[0]
    Pipeline(store).run(job, provider, "both", tmp_path / "output")
    window.load_review(job)
    window.review_table.item(0, 2).setText("Unsaved reviewed heading")
    window.key_edit.setText("session-only-secret")
    window.language_combo.setCurrentIndex(window.language_combo.findData("vi"))
    window.theme_combo.setCurrentIndex(window.theme_combo.findData("dark"))
    assert window.add_button.text() == "Thêm tài liệu"
    assert window.review_table.item(0, 2).text() == "Unsaved reviewed heading"
    assert window.selected_ids() == [job]
    assert app.palette().color(QPalette.ColorRole.Window).lightness() < 100
    window.settings_dialog.close()
    window.close()
    preferences = load_preferences()
    assert preferences["language"] == "vi" and preferences["theme"] == "dark"
    assert "session-only-secret" not in json.dumps(preferences)
    reopened = MainWindow(store.root)
    assert reopened.language == "vi" and reopened.theme == "dark"
    reopened.language_combo.setCurrentIndex(reopened.language_combo.findData("en"))
    assert reopened.add_button.text() == "Add documents"
    reopened.close()


def test_folder_imports_supported_nested_files_and_skips_outputs_and_locks(
    word_file, slides_file, spreadsheet, text_pdf, store, tmp_path, monkeypatch
):
    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "import"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    for source in (word_file, slides_file, spreadsheet, text_pdf):
        shutil.copy2(source, nested / source.name.upper())
    (folder / "notes.txt").write_text("Ignore me")
    (folder / "~$lock.docx").write_text("Ignore me")
    output = folder / "translated"
    output.mkdir()
    shutil.copy2(word_file, output / "previous.docx")
    window = MainWindow(store.root)
    window.output_edit.setText(str(output))
    monkeypatch.setattr(
        "converter.ui.QFileDialog.getExistingDirectory", lambda *args: str(folder)
    )
    window.add_folder_action.trigger()
    assert window.job_table.rowCount() == 4
    assert len(window.selected_ids()) == 4
    assert {Path(job["name"]).suffix.lower() for job in store.list()} == {
        ".docx", ".pptx", ".xlsx", ".pdf"
    }
    window.set_busy(True)
    assert not window.add_folder_action.isEnabled()
    window.set_busy(False)
    app.processEvents()
    window.close()


def test_glossary_migration_overrides_and_deletions_persist(store, tmp_path, monkeypatch):
    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    defaults = default_glossary()
    source = next(iter(defaults))
    save_preferences({"glossary": {source: "Project-specific term"}})
    window = MainWindow(store.root)
    assert len(window.glossary()) == len(defaults)
    assert window.glossary()[source] == "Project-specific term"
    window.glossary_table.removeRow(0)
    assert window.persist_preferences()
    window.close()
    reopened = MainWindow(store.root)
    assert len(reopened.glossary()) == len(defaults) - 1
    reopened.restore_automotive_glossary()
    assert len(reopened.glossary()) == len(defaults)
    reopened.glossary_enabled.setChecked(False)
    assert reopened.glossary() == {}
    reopened.close()
    assert len(load_preferences()["glossary"]) == len(defaults)
    app.processEvents()


def test_online_settings_save_api_url_model_and_custom_auth(store, tmp_path, monkeypatch):
    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.service_name_edit.setText("Company API")
    window.endpoint_edit.setText("https://example.com/openai/v1/")
    window.model_edit.setText("company-model")
    window.key_edit.setText("session-secret")
    window.auth_header_edit.setText("api-key")
    window.auth_prefix_edit.setText("")
    window.timeout_spin.setValue(240)
    window.context_window_spin.setValue(32768)
    window.token_margin_spin.setValue(1024)
    window.concurrent_spin.setValue(2)
    assert window.save_provider_settings(True)
    assert window.profile.endpoint == "https://example.com/openai/v1/chat/completions"
    assert window.provider_combo.itemText(0) == "Company API"
    saved = (tmp_path / "preferences/provider.json").read_text()
    assert "session-secret" not in saved
    window.close()
    reopened = MainWindow(store.root)
    assert reopened.endpoint_edit.text() == window.profile.endpoint
    assert reopened.model_edit.text() == "company-model"
    assert reopened.auth_header_edit.text() == "api-key"
    assert reopened.auth_prefix_edit.text() == ""
    assert reopened.timeout_spin.value() == 240
    assert reopened.context_window_spin.value() == 32768
    assert reopened.token_margin_spin.value() == 1024
    assert reopened.concurrent_spin.value() == 2
    reopened.auth_enabled.setChecked(False)
    assert reopened.save_provider_settings(True)
    assert reopened.profile.auth_header == ""
    assert any("https://www.argosopentech.com/argospm/index/" in label.text()
               for label in reopened.settings_dialog.findChildren(QLabel))
    app.processEvents()
    reopened.close()


def test_compact_main_actions_preserve_import_review_export_and_running_controls(
    word_file, store, provider, tmp_path, monkeypatch
):
    from converter.pipeline import Pipeline

    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.show()
    assert window.operation_combo.group.button(0).text() == "Translate to English"
    assert window.operation_combo.group.button(1).text() == "Convert to Markdown"
    assert window.job_stack.currentWidget() == window.empty_page
    assert not window.start_button.isEnabled()
    assert not window.cancel_button.isVisible()
    window.add_paths([word_file])
    assert window.job_stack.currentWidget() == window.job_table
    assert window.start_button.isEnabled()
    job = window.selected_ids()[0]
    Pipeline(store).run(job, provider, "both", tmp_path / "output")
    window.refresh_jobs()
    window.review_button.trigger()
    assert window.review_id == job
    calls = []
    monkeypatch.setattr(window, "start_jobs", lambda export_only=False: calls.append(export_only))
    window.export_button.trigger()
    assert calls == [True]
    window.review_dialog.close()
    window.set_busy(True)
    assert not window.start_button.isVisible()
    assert window.pause_button.isVisible()
    assert window.cancel_button.isVisible()
    assert not window.export_button.isEnabled()
    window.set_busy(False)
    assert window.start_button.isVisible()
    assert not window.pause_button.isVisible()
    app.processEvents()
    window.close()


def test_review_dialog_loads_selected_document_and_preserves_edits(
    word_file, store, provider, tmp_path, monkeypatch
):
    from converter.pipeline import Pipeline

    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.add_paths([word_file])
    job = window.selected_ids()[0]
    Pipeline(store).run(job, provider, "both", tmp_path / "output")
    window.refresh_jobs()
    assert window.selected_ids() == [job]
    window.review_button.trigger()
    app.processEvents()
    assert window.review_id == job
    assert window.review_table.rowCount() > 0
    assert window.review_dialog.isVisible()
    window.review_table.item(0, 2).setText("Unsaved review change")
    window.open_selected_review()
    assert window.review_table.item(0, 2).text() == "Unsaved review change"
    window.review_dialog.close()
    assert store.load_document(job).segments[0].target == "Unsaved review change"
    window.open_selected_review()
    assert window.review_table.item(0, 2).text() == "Unsaved review change"
    window.close()


def test_worker_finish_refreshes_an_open_review_without_opening_it_automatically(
    word_file, store, provider, tmp_path, monkeypatch
):
    from converter.pipeline import Pipeline

    class ExitedWorker:
        def join(self, timeout=None):
            pass

        def is_alive(self):
            return False

    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.add_paths([word_file])
    job = window.selected_ids()[0]
    Pipeline(store).run(job, provider, "both", tmp_path / "output")
    window.finish_process()
    assert not window.review_dialog.isVisible()
    window.open_selected_review()
    window.process = ExitedWorker()
    window.set_busy(True)
    updated = store.load_document(job)
    updated.segments[0].target = "Updated by worker"
    updated.revision += 1
    store.save_document(job, updated)
    window.finish_process()
    app.processEvents()
    assert window.review_id == job
    assert window.review_table.rowCount() > 0
    assert window.review_table.item(0, 2).text() == "Updated by worker"
    window.close()


def test_convert_task_hides_translation_options_and_persists_glossary_on_settings_close(
    word_file, store, tmp_path, monkeypatch
):
    from converter.pipeline import Pipeline

    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.show()
    window.operation_combo.setCurrentIndex(window.operation_combo.findData("convert"))
    assert not window.provider_combo.isVisible()
    assert not window.mode_combo.isVisible()
    assert window.start_button.text() == "Convert to Markdown"
    assert "original language" in window.privacy_label.text()
    window.open_settings()
    window.settings_tabs.setCurrentWidget(window.glossary_page)
    window.glossary_table.item(0, 1).setText("Edited in Settings")
    window.settings_dialog.close()
    assert "Edited in Settings" in load_preferences()["glossary"].values()
    window.add_paths([word_file])
    job = window.selected_ids()[0]
    window.refresh_jobs()
    assert window.job_table.item(0, 1).text() == "Markdown"
    Pipeline(store).run(job, None, "markdown", tmp_path / "output", operation="convert")
    window.refresh_jobs()
    window.open_selected_review()
    assert window.review_table.isColumnHidden(2)
    assert not window.retranslate_button.isVisible()
    assert "测试文本" in window.markdown_preview.toPlainText()
    window.review_dialog.close()
    window.operation_combo.setCurrentIndex(window.operation_combo.findData("translate"))
    assert window.provider_combo.isVisible()
    assert window.mode_combo.isVisible()
    app.processEvents()
    window.close()


def test_right_click_review_targets_one_entry_from_a_selected_batch(
    word_file, store, provider, tmp_path, monkeypatch
):
    from converter.pipeline import Pipeline

    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.add_paths([word_file, word_file])
    for job in window.selected_ids():
        Pipeline(store).run(job, provider, "both", tmp_path / "output")
    window.refresh_jobs()
    assert len(window.selected_ids()) == 2
    clicked = window.job_table.item(0, 0)
    job_id = window.selected_ids()[0]
    monkeypatch.setattr(window.more_menu, "exec", lambda point: window.review_button.trigger())
    window.open_job_menu(window.job_table.visualItemRect(clicked).center())
    app.processEvents()
    assert window.selected_ids() == [job_id]
    assert window.review_id == job_id
    assert window.review_dialog.isVisible()
    window.close()


def test_progress_burst_yields_to_gui_and_coalesces_table_refreshes(
    word_file, store, monkeypatch, tmp_path
):
    import queue

    monkeypatch.setenv("DOCBRIDGE_DATA_DIR", str(tmp_path / "preferences"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.timer.stop()
    window.add_paths([word_file])
    job = window.selected_ids()[0]
    window.events = queue.Queue()
    for done in range(500):
        window.events.put({"kind": "progress", "id": job, "message": "Đang dịch",
                           "done": done + 1, "total": 500})
    refreshes = []
    refresh = window.refresh_jobs

    def tracked_refresh():
        refreshes.append(True)
        refresh()

    monkeypatch.setattr(window, "refresh_jobs", tracked_refresh)
    window.poll()
    assert len(refreshes) == 1
    assert 0 < window.events.qsize() < 500
    assert 0 < window.progress_bar.value() < 500
    while not window.events.empty():
        window.poll()
    assert window.progress_bar.value() == 500
    assert window.selected_ids() == [job]
    app.processEvents()
    window.close()


def test_dead_worker_backlog_is_processed_before_finishing(word_file, store, monkeypatch, tmp_path):
    import queue
    from types import SimpleNamespace

    monkeypatch.setenv("DOCBRIDGE_DATA_DIR", str(tmp_path / "preferences"))
    QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    window.timer.stop()
    window.add_paths([word_file])
    job = window.selected_ids()[0]
    window.events = queue.Queue()
    window.process = SimpleNamespace(is_alive=lambda: False, join=lambda **_: None)
    window.set_busy(True)
    for done in range(150):
        window.events.put({"kind": "progress", "id": job, "message": "Đang dịch",
                           "done": done + 1, "total": 150})
    window.events.put({"kind": "job_finished", "id": job})
    window.events.put({"kind": "finished"})
    window.poll()
    assert window.process is not None and window.busy
    while not window.events.empty():
        window.poll()
    assert window.process is None and not window.busy
    assert not window.progress_messages
    assert window.progress_bar.value() == 100
    window.poll()
    assert not window.progress_messages
    window.close()


def test_excel_layout_choice_defaults_readable_and_persists(store, tmp_path, monkeypatch):
    monkeypatch.setenv('CONVERTER_DATA_DIR', str(tmp_path / 'preferences'))
    app = QApplication.instance() or QApplication([])
    window = MainWindow(store.root)
    assert window.excel_layout_combo.currentData() == 'readable'
    assert window.excel_layout_combo.itemText(0) == 'Readable'
    window.excel_layout_combo.setCurrentIndex(window.excel_layout_combo.findData('preserve'))
    assert load_preferences()['excel_layout'] == 'preserve'
    window.language_combo.setCurrentIndex(window.language_combo.findData('vi'))
    assert window.excel_layout_combo.itemText(0) == 'Dễ đọc'
    window.close()
    again = MainWindow(store.root)
    assert again.excel_layout_combo.currentData() == 'preserve'
    app.processEvents()
    again.close()
