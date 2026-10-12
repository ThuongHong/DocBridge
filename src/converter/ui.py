from __future__ import annotations

import multiprocessing as mp
import queue
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .config import (
    ProviderConfig,
    data_root,
    get_api_key,
    load_preferences,
    save_preferences,
    set_api_key,
)
from .markdown import render_markdown
from .pipeline import Pipeline
from .store import Store
from .worker import run_jobs, test_online

STATUS = {
    "pending": "Chờ dịch",
    "parsing": "Đang phân tích",
    "translating": "Đang dịch",
    "review": "Cần review",
    "exporting": "Đang xuất",
    "done": "Hoàn thành",
    "done_warnings": "Hoàn thành · có cảnh báo",
    "paused": "Tạm dừng",
    "cancelled": "Đã hủy",
    "failed": "Lỗi",
    "partial": "Xuất được một phần",
}
MODE_NAMES = {"office": "Chỉ Office", "markdown": "Chỉ Markdown", "both": "Cả hai"}


class MainWindow(QMainWindow):
    def __init__(self, root: Path | None = None):
        super().__init__()
        self.setWindowTitle("Converter — Trung → Anh")
        self.resize(1180, 800)
        self.setAcceptDrops(True)
        self.store = Store(root or data_root())
        self.store.recover()
        self.preferences = load_preferences()
        self.profile = ProviderConfig.load()
        self.api_key = get_api_key()
        self.process = None
        self.connection_process = None
        self.events = None
        self.connection_events = None
        self.context = mp.get_context("spawn")
        self.pause_event = None
        self.cancel_event = None
        self.review_id = None
        self.review_doc = None
        self.progress_messages = {}
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.build_documents()
        self.build_review()
        self.build_glossary()
        self.build_settings()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        self.refresh_jobs()
        self.statusBar().showMessage("Sẵn sàng. Chọn file và chế độ xuất để bắt đầu.")

    def button(self, label, callback, layout):
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def build_documents(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        self.add_button = self.button("Thêm file", self.add_files, toolbar)
        self.review_button = self.button("Review bản dịch", self.open_selected_review, toolbar)
        self.button("Mở kết quả", self.open_outputs, toolbar)
        self.delete_button = self.button("Xóa khỏi lịch sử", self.delete_jobs, toolbar)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.job_table = QTableWidget(0, 4)
        self.job_table.setHorizontalHeaderLabels(
            ["Tài liệu", "Đầu ra Office", "Trạng thái", "Kết quả / lỗi"]
        )
        self.job_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.job_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.job_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.job_table.horizontalHeader().setStretchLastSection(True)
        self.job_table.setColumnWidth(0, 250)
        self.job_table.setColumnWidth(1, 140)
        self.job_table.setColumnWidth(2, 190)
        self.job_table.cellDoubleClicked.connect(lambda *_: self.open_selected_review())
        layout.addWidget(self.job_table)
        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItem(self.profile.name, "online")
        self.provider_combo.addItem("Offline — Argos Trung → Anh", "offline")
        self.provider_combo.setCurrentIndex(
            1 if self.preferences.get("provider") == "offline" else 0
        )
        self.provider_combo.currentIndexChanged.connect(self.update_privacy_label)
        form.addRow("Dịch Trung → Anh:", self.provider_combo)
        self.privacy_label = QLabel()
        form.addRow("", self.privacy_label)
        self.mode_combo = QComboBox()
        for mode, name in MODE_NAMES.items():
            self.mode_combo.addItem(name, mode)
        self.mode_combo.setCurrentIndex(
            max(0, self.mode_combo.findData(self.preferences.get("mode", "both")))
        )
        form.addRow("Xuất:", self.mode_combo)
        form.addRow("", QLabel("PDF → Office là DOCX dựng lại. Office đầu vào giữ định dạng gốc."))
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit(
            self.preferences.get("output_dir", str(Path.home() / "Documents/Translations"))
        )
        output_row.addWidget(self.output_edit)
        self.button("Chọn thư mục", self.choose_output, output_row)
        form.addRow("Lưu vào:", output_row)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.start_button = self.button("Dịch file đã chọn / Tiếp tục", self.start_jobs, actions)
        self.export_button = self.button(
            "Xuất lại bản đã review", lambda: self.start_jobs(export_only=True), actions
        )
        self.pause_button = self.button("Tạm dừng", self.pause_jobs, actions)
        self.cancel_button = self.button("Hủy", self.cancel_jobs, actions)
        layout.addLayout(actions)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        self.tabs.addTab(page, "Tài liệu & lịch sử")
        self.update_privacy_label()
        self.set_busy(False)

    def build_review(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.review_title = QLabel("Chọn một tài liệu trong danh sách để review.")
        layout.addWidget(self.review_title)
        self.warning_view = QTextBrowser()
        self.warning_view.setMaximumHeight(100)
        layout.addWidget(self.warning_view)
        toolbar = QHBoxLayout()
        self.review_search = QLineEdit()
        self.review_search.setPlaceholderText("Tìm trong nguồn / bản dịch")
        self.review_search.textChanged.connect(self.filter_review)
        toolbar.addWidget(self.review_search)
        self.review_filter = QComboBox()
        self.review_filter.addItems(["Tất cả", "Chưa dịch", "Có cảnh báo"])
        self.review_filter.currentIndexChanged.connect(self.filter_review)
        toolbar.addWidget(self.review_filter)
        self.save_review_button = self.button("Lưu sửa đổi", self.save_review, toolbar)
        self.retranslate_button = self.button(
            "Dịch lại đoạn chọn", self.retranslate_selected, toolbar
        )
        self.button("Xuất báo cáo", self.export_report, toolbar)
        layout.addLayout(toolbar)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.review_table = QTableWidget(0, 4)
        self.review_table.setHorizontalHeaderLabels(["Vị trí", "Nguồn", "Bản dịch", "Cảnh báo"])
        self.review_table.setColumnWidth(0, 120)
        self.review_table.setColumnWidth(1, 390)
        self.review_table.setColumnWidth(2, 390)
        self.review_table.horizontalHeader().setStretchLastSection(True)
        self.review_table.setWordWrap(True)
        self.review_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.review_table.itemSelectionChanged.connect(self.preview_pdf_region)
        splitter.addWidget(self.review_table)
        preview_row = QWidget()
        preview_layout = QHBoxLayout(preview_row)
        self.markdown_preview = QTextBrowser()
        self.markdown_preview.setOpenExternalLinks(False)
        self.markdown_preview.anchorClicked.connect(lambda url: None)
        preview_layout.addWidget(self.markdown_preview)
        self.pdf_preview = QLabel("Preview PDF khi chọn đoạn.")
        self.pdf_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pdf_preview.setMinimumWidth(250)
        preview_layout.addWidget(self.pdf_preview)
        splitter.addWidget(preview_row)
        splitter.setSizes([400, 200])
        layout.addWidget(splitter)
        self.tabs.addTab(page, "Review")

    def build_glossary(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel("Thuật ngữ cố định: nhập tiếng Trung và bản dịch tiếng Anh tương ứng.")
        )
        self.glossary_table = QTableWidget(0, 2)
        self.glossary_table.setHorizontalHeaderLabels(["Tiếng Trung", "Tiếng Anh"])
        self.glossary_table.horizontalHeader().setStretchLastSection(True)
        self.glossary_table.setColumnWidth(0, 400)
        for source, target in self.preferences.get("glossary", {}).items():
            row = self.glossary_table.rowCount()
            self.glossary_table.insertRow(row)
            self.glossary_table.setItem(row, 0, QTableWidgetItem(source))
            self.glossary_table.setItem(row, 1, QTableWidgetItem(target))
        layout.addWidget(self.glossary_table)
        actions = QHBoxLayout()
        self.button(
            "Thêm thuật ngữ",
            lambda: self.glossary_table.insertRow(self.glossary_table.rowCount()),
            actions,
        )
        self.button("Xóa dòng chọn", self.delete_glossary_rows, actions)
        self.button("Lưu thuật ngữ", self.persist_preferences, actions)
        layout.addLayout(actions)
        layout.addWidget(
            QLabel("Đổi glossary khi đang dịch dở: tạo job mới để giữ nhất quán bản dịch.")
        )
        self.tabs.addTab(page, "Thuật ngữ")

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        form.addRow("Dịch vụ:", QLabel(self.profile.name))
        self.key_edit = QLineEdit(self.api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Nhập API key của bạn")
        form.addRow("API key:", self.key_edit)
        actions = QHBoxLayout()
        self.button("Lưu key", self.save_key, actions)
        self.button("Xóa key", self.clear_key, actions)
        self.connection_button = self.button("Kiểm tra kết nối", self.test_connection, actions)
        form.addRow("", actions)
        self.key_status = QLabel()
        form.addRow("", self.key_status)
        form.addRow(
            "",
            QLabel("Key được lưu trong kho mật khẩu Windows. Có thể dùng key tạm trong phiên này."),
        )
        form.addRow(
            "", QLabel("Kiểm tra kết nối gửi một câu thử ngắn, có thể được dịch vụ tính phí.")
        )
        self.ocr_language = QComboBox()
        self.ocr_language.addItem("Trung giản thể + phồn thể + Anh", "chi_sim+chi_tra+eng")
        self.ocr_language.addItem("Trung giản thể + Anh", "chi_sim+eng")
        self.ocr_language.addItem("Trung phồn thể + Anh", "chi_tra+eng")
        self.ocr_language.addItem("Anh (tài liệu thử)", "eng")
        self.ocr_language.setCurrentIndex(
            max(
                0,
                self.ocr_language.findData(
                    self.preferences.get("ocr_language", "chi_sim+chi_tra+eng")
                ),
            )
        )
        form.addRow("OCR:", self.ocr_language)
        layout.addLayout(form)
        layout.addStretch()
        self.tabs.addTab(page, "Cài đặt")

    def update_privacy_label(self):
        self.privacy_label.setText(
            "Nội dung được gửi đến dịch vụ online đã cấu hình."
            if self.provider_combo.currentData() == "online"
            else "Dịch trên máy bằng Argos; nội dung không gửi đến API."
        )

    def error(self, message):
        QMessageBox.warning(self, "Converter", str(message))

    def selected_ids(self):
        return [
            self.job_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in sorted({index.row() for index in self.job_table.selectedIndexes()})
        ]

    def refresh_jobs(self):
        selected = set(self.selected_ids())
        self.job_table.setRowCount(0)
        for job in self.store.list():
            row = self.job_table.rowCount()
            self.job_table.insertRow(row)
            name = QTableWidgetItem(job["name"])
            name.setData(Qt.ItemDataRole.UserRole, job["id"])
            ext = Path(job["name"]).suffix.upper().lstrip(".")
            output = "DOCX dựng lại" if ext == "PDF" else ext
            state = self.progress_messages.get(job["id"], STATUS.get(job["status"], job["status"]))
            results = []
            for kind, value in job["exports"].items():
                if value.get("status") == "done":
                    results.append(f"{MODE_NAMES[kind]}: {Path(value['path']).name}")
                elif value.get("status") == "stale":
                    results.append(f"{MODE_NAMES[kind]}: cần xuất lại")
            for col, item in enumerate(
                [
                    name,
                    QTableWidgetItem(output),
                    QTableWidgetItem(state),
                    QTableWidgetItem(job["error"] or " · ".join(results)),
                ]
            ):
                self.job_table.setItem(row, col, item)
            if job["id"] in selected:
                self.job_table.selectionModel().select(
                    self.job_table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

    def add_paths(self, paths):
        if self.process:
            return
        added = []
        for path in paths:
            try:
                added.append(self.store.add(Path(path)))
            except Exception as exc:
                self.error(exc)
        self.refresh_jobs()
        self.job_table.clearSelection()
        for row in range(self.job_table.rowCount()):
            if self.job_table.item(row, 0).data(Qt.ItemDataRole.UserRole) in added:
                self.job_table.selectionModel().select(
                    self.job_table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Thêm tài liệu", "", "Documents (*.docx *.pptx *.xlsx *.pdf)"
        )
        self.add_paths(paths)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.process:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "Thư mục kết quả", self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def glossary(self):
        result = {}
        for row in range(self.glossary_table.rowCount()):
            source = self.glossary_table.item(row, 0)
            target = self.glossary_table.item(row, 1)
            if source and source.text().strip():
                if not target or not target.text().strip():
                    raise ValueError("Thuật ngữ phải có cả nguồn và bản dịch.")
                result[source.text().strip()] = target.text().strip()
        return result

    def persist_preferences(self):
        try:
            self.preferences.update(
                {
                    "provider": self.provider_combo.currentData(),
                    "mode": self.mode_combo.currentData(),
                    "output_dir": self.output_edit.text(),
                    "ocr_language": self.ocr_language.currentData(),
                    "glossary": self.glossary(),
                }
            )
            save_preferences(self.preferences)
            self.statusBar().showMessage("Đã lưu cài đặt.")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def set_busy(self, busy):
        for button in [
            self.start_button,
            self.export_button,
            self.add_button,
            self.delete_button,
            self.review_button,
        ]:
            button.setEnabled(not busy)
        self.pause_button.setEnabled(busy)
        self.cancel_button.setEnabled(busy)
        if hasattr(self, "save_review_button"):
            self.save_review_button.setEnabled(not busy)
            self.retranslate_button.setEnabled(not busy)
            self.review_table.setEnabled(not busy)

    def start_jobs(self, export_only=False):
        if self.process:
            return
        ids = self.selected_ids()
        if not ids:
            self.error("Chọn ít nhất một file trong danh sách.")
            return
        if not self.output_edit.text().strip():
            self.error("Chọn thư mục kết quả.")
            return
        if not self.persist_preferences():
            return
        if export_only and self.review_id in ids and not self.save_review():
            return
        self.api_key = self.key_edit.text().strip()
        try:
            if not export_only and self.provider_combo.currentData() == "online":
                self.profile.validate()
                if not self.api_key:
                    raise ValueError("Nhập API key trong Cài đặt hoặc chọn Offline.")
            if export_only:
                for job_id in ids:
                    if (
                        not self.store.document_path(job_id).exists()
                        or not self.store.load_document(job_id).complete()
                    ):
                        raise ValueError("Chọn bản dịch đã hoàn thành để xuất lại.")
            self.events = self.context.Queue()
            self.pause_event = self.context.Event()
            self.cancel_event = self.context.Event()
            options = {
                "provider": self.provider_combo.currentData(),
                "profile": asdict(self.profile),
                "mode": self.mode_combo.currentData(),
                "output_dir": self.output_edit.text(),
                "glossary": self.glossary(),
                "ocr_language": self.ocr_language.currentData(),
                "export_only": export_only,
            }
            self.process = self.context.Process(
                target=run_jobs,
                args=(
                    str(self.store.root),
                    ids,
                    options,
                    self.api_key,
                    self.events,
                    self.pause_event,
                    self.cancel_event,
                ),
            )
            self.process.start()
            self.set_busy(True)
            self.progress_bar.setRange(0, 0)
        except Exception as exc:
            self.process = None
            self.error(exc)

    def pause_jobs(self):
        if self.pause_event:
            self.pause_event.set()
            self.statusBar().showMessage(
                "Sẽ tạm dừng sau request/batch đang xử lý; tiến độ được giữ."
            )

    def cancel_jobs(self):
        if self.cancel_event:
            self.cancel_event.set()
            self.statusBar().showMessage("Đang hủy; bản dịch đã hoàn thành vẫn được giữ.")

    def finish_process(self):
        if self.process:
            self.process.join(timeout=0.05)
            if self.process.is_alive():
                return
        self.process = None
        self.set_busy(False)
        self.progress_messages.clear()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.refresh_jobs()
        self.statusBar().showMessage("Đã lưu tiến độ. Xem trạng thái và kết quả trong danh sách.")

    def poll(self):
        if self.events:
            while True:
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                if event["kind"] == "progress":
                    self.progress_messages[event["id"]] = event["message"]
                    self.statusBar().showMessage(event["message"])
                    if event["total"]:
                        self.progress_bar.setRange(0, event["total"])
                        self.progress_bar.setValue(event["done"])
                    self.refresh_jobs()
                elif event["kind"] == "error":
                    self.statusBar().showMessage(event["message"])
                elif event["kind"] == "job_finished":
                    self.progress_messages.pop(event["id"], None)
                    self.refresh_jobs()
                elif event["kind"] == "finished":
                    self.finish_process()
        if self.process and not self.process.is_alive():
            # Includes native worker crashes that cannot send a final queue event.
            self.store.recover()
            self.finish_process()
        if self.connection_events:
            try:
                event = self.connection_events.get_nowait()
            except queue.Empty:
                event = None
            if event:
                self.key_status.setText(event["message"])
            if self.connection_process and not self.connection_process.is_alive():
                self.connection_process.join()
                self.connection_process = None
                self.connection_events = None
                self.connection_button.setEnabled(True)

    def open_selected_review(self):
        if self.process:
            return
        ids = self.selected_ids()
        if len(ids) != 1:
            self.error("Chọn một file để review.")
            return
        try:
            self.load_review(ids[0])
            self.tabs.setCurrentIndex(1)
        except Exception as exc:
            self.error(exc)

    def load_review(self, job_id):
        doc = self.store.load_document(job_id)
        self.review_id = job_id
        self.review_doc = doc
        self.review_title.setText(self.store.get(job_id)["name"] + f" · revision {doc.revision}")
        self.warning_view.setPlainText("\n".join(doc.warnings))
        self.review_table.setRowCount(0)
        for segment in doc.segments:
            row = self.review_table.rowCount()
            self.review_table.insertRow(row)
            anchor = segment.anchor
            position = (
                anchor.get("cell") or f"Page {anchor['page'] + 1}"
                if "page" in anchor
                else anchor.get("cell", Path(anchor.get("part", "")).name)
            )
            location = QTableWidgetItem(position or segment.id)
            location.setData(Qt.ItemDataRole.UserRole, segment.id)
            source = QTableWidgetItem(segment.source)
            target = QTableWidgetItem(segment.target or "")
            warning = QTableWidgetItem(segment.warning)
            for item in [location, warning] + ([] if doc.format == "pdf" else [source]):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            for col, item in enumerate([location, source, target, warning]):
                self.review_table.setItem(row, col, item)
        self.review_table.resizeRowsToContents()
        self.filter_review()
        self.pdf_preview.setVisible(doc.format == "pdf")
        self.update_markdown_preview()

    def filter_review(self):
        search = self.review_search.text().casefold()
        filter_index = self.review_filter.currentIndex()
        for row in range(self.review_table.rowCount()):
            source = self.review_table.item(row, 1).text()
            target = self.review_table.item(row, 2).text()
            warning = self.review_table.item(row, 3).text()
            visible = search in (source + target).casefold()
            visible &= filter_index != 1 or not target.strip()
            visible &= filter_index != 2 or bool(warning)
            self.review_table.setRowHidden(row, not visible)

    def save_review(self):
        if not self.review_id or self.process:
            return True
        try:
            original = self.review_doc.by_id()
            targets, sources = {}, {}
            for row in range(self.review_table.rowCount()):
                sid = self.review_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                source = self.review_table.item(row, 1).text()
                target = self.review_table.item(row, 2).text()
                if target != (original[sid].target or ""):
                    targets[sid] = target
                if source != original[sid].source:
                    sources[sid] = source
            if targets or sources:
                self.store.revise(self.review_id, targets, sources)
                self.load_review(self.review_id)
                self.refresh_jobs()
            self.statusBar().showMessage("Đã lưu review; xuất lại để nhận file cập nhật.")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def retranslate_selected(self):
        if not self.review_id or self.process:
            return
        rows = {item.row() for item in self.review_table.selectedIndexes()}
        if not rows:
            return
        if not self.save_review():
            return
        doc = self.store.load_document(self.review_id)
        lookup = doc.by_id()
        for row in rows:
            lookup[self.review_table.item(row, 0).data(Qt.ItemDataRole.UserRole)].target = None
        doc.revision += 1
        self.store.save_document(self.review_id, doc)
        exports = self.store.get(self.review_id)["exports"]
        for value in exports.values():
            if value.get("status") == "done":
                value["status"] = "stale"
        self.store.update(self.review_id, status="review", exports=exports)
        self.load_review(self.review_id)
        self.tabs.setCurrentIndex(0)
        self.job_table.clearSelection()
        for row in range(self.job_table.rowCount()):
            if self.job_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.review_id:
                self.job_table.selectRow(row)
        self.start_jobs()

    def update_markdown_preview(self):
        if self.review_doc and self.review_doc.complete():
            self.markdown_preview.document().setBaseUrl(
                QUrl.fromLocalFile(str(self.store.job_dir(self.review_id)) + "/")
            )
            self.markdown_preview.setMarkdown(render_markdown(self.review_doc, "assets"))
        else:
            self.markdown_preview.setPlainText("Markdown preview có sau khi hoàn thành bản dịch.")

    def preview_pdf_region(self):
        if not self.review_doc or self.review_doc.format != "pdf":
            return
        rows = self.review_table.selectedIndexes()
        if not rows:
            return
        from PIL import ImageDraw
        from PySide6.QtGui import QPixmap

        from .pdf import render_page

        sid = self.review_table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        anchor = self.review_doc.by_id()[sid].anchor
        try:
            image = render_page(Path(self.review_doc.source_path), anchor["page"], scale=1)
            if anchor.get("bbox"):
                ImageDraw.Draw(image).rectangle(anchor["bbox"], outline="red", width=2)
            from PIL.ImageQt import ImageQt

            pixmap = QPixmap.fromImage(ImageQt(image))
            self.pdf_preview.setPixmap(pixmap.scaled(320, 300, Qt.AspectRatioMode.KeepAspectRatio))
        except Exception:
            self.pdf_preview.setText("Không render được trang PDF.")

    def export_report(self):
        if not self.review_id:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Xuất báo cáo", "report.json", "JSON (*.json)")
        if path:
            Pipeline(self.store).report(self.review_id, Path(path))

    def open_outputs(self):
        for job_id in self.selected_ids():
            directory = self.store.get(job_id)["output_dir"]
            if directory and Path(directory).exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(directory))
                break

    def delete_jobs(self):
        if self.process:
            return
        for job_id in self.selected_ids():
            self.store.delete(job_id)
            if self.review_id == job_id:
                self.review_id = None
                self.review_doc = None
                self.review_table.setRowCount(0)
                self.warning_view.clear()
                self.markdown_preview.clear()
        self.refresh_jobs()

    def delete_glossary_rows(self):
        for row in sorted(
            {item.row() for item in self.glossary_table.selectedIndexes()}, reverse=True
        ):
            self.glossary_table.removeRow(row)

    def save_key(self):
        self.api_key = self.key_edit.text().strip()
        try:
            set_api_key(self.api_key)
            self.key_status.setText("Đã lưu key vào kho mật khẩu hệ điều hành.")
        except Exception:
            self.key_status.setText(
                "Kho mật khẩu không khả dụng; key chỉ dùng trong phiên hiện tại."
            )

    def clear_key(self):
        try:
            set_api_key("")
            self.key_edit.clear()
            self.api_key = ""
            self.key_status.setText("Đã xóa key.")
        except Exception:
            self.error("Không xóa được key trong kho mật khẩu hệ điều hành.")

    def test_connection(self):
        if self.connection_process:
            return
        self.connection_events = self.context.Queue()
        self.connection_process = self.context.Process(
            target=test_online,
            args=(asdict(self.profile), self.key_edit.text().strip(), self.connection_events),
        )
        self.connection_process.start()
        self.connection_button.setEnabled(False)
        self.key_status.setText("Đang kiểm tra kết nối…")

    def closeEvent(self, event):
        if self.process and self.process.is_alive():
            self.pause_jobs()
            self.statusBar().showMessage(
                "Đang lưu tiến độ trước khi đóng. Đóng lại sau khi worker dừng."
            )
            event.ignore()
            return
        if self.connection_process and self.connection_process.is_alive():
            self.connection_process.terminate()
            self.connection_process.join(timeout=1)
        if not self.persist_preferences():
            event.ignore()
            return
        event.accept()
