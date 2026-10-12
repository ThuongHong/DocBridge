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
    assert app.palette().color(QPalette.ColorRole.Window).lightness() > 200
    assert window.tabs.count() == 3
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
    window.tabs.setCurrentIndex(0)
    window.set_busy(True)
    assert not window.start_button.isVisible()
    assert window.pause_button.isVisible()
    assert window.cancel_button.isVisible()
    assert not window.export_button.isEnabled()
    window.set_busy(False)
    window.tabs.setCurrentIndex(0)
    assert window.start_button.isVisible()
    assert not window.pause_button.isVisible()
    app.processEvents()
    window.close()
