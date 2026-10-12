from __future__ import annotations

import multiprocessing as mp
import os
import queue
from dataclasses import asdict
from html import escape
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .appearance import apply_theme, settings_icon
from .config import (
    ProviderConfig,
    data_root,
    get_api_key,
    load_preferences,
    normalize_endpoint,
    save_preferences,
    set_api_key,
)
from .glossary import automotive_pack, default_glossary
from .i18n import ENGLISH, TEMPLATES, translate
from .markdown import render_markdown
from .models import SUPPORTED
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
        if "glossary_pack_version" not in self.preferences:
            self.preferences["glossary"] = default_glossary() | self.preferences.get("glossary", {})
            self.preferences["glossary_pack_version"] = automotive_pack()["version"]
        self.language = self.preferences.get("language", "en")
        if self.language not in {"en", "vi"}:
            self.language = "en"
        self.theme = self.preferences.get("theme", "light")
        if self.theme not in {"light", "dark"}:
            self.theme = "light"
        apply_theme(self.theme)
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
        self.settings_button = QToolButton(self)
        self.settings_button.setAutoRaise(True)
        self.settings_button.setFixedSize(28, 28)
        self.settings_button.setIconSize(QSize(18, 18))
        self.settings_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.settings_button.clicked.connect(self.open_settings)
        self.tabs.setCornerWidget(self.settings_button, Qt.Corner.TopRightCorner)
        self.bind_translations()
        self.retranslate_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        self.refresh_jobs()
        self.show_status("Sẵn sàng. Chọn file và chế độ xuất để bắt đầu.")

    def button(self, label, callback, layout):
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def build_documents(self):
        page = QWidget()
        self.documents_page = page
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        title = QLabel("Danh sách tài liệu")
        font = title.font()
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)
        toolbar.addWidget(title)
        self.selection_summary = QLabel()
        toolbar.addWidget(self.selection_summary)
        toolbar.addStretch()
        self.add_button = QToolButton()
        self.add_button.setText("Thêm tài liệu")
        self.add_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.add_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.add_button.setMinimumHeight(30)
        self.add_button.clicked.connect(self.add_files)
        self.add_menu = QMenu(self)
        self.add_files_action = self.add_menu.addAction("Thêm file", self.add_files)
        self.add_folder_action = self.add_menu.addAction("Thêm thư mục", self.add_folder)
        self.add_button.setMenu(self.add_menu)
        toolbar.addWidget(self.add_button)
        self.more_button = QToolButton()
        self.more_button.setText("⋯")
        self.more_button.setAutoRaise(True)
        self.more_button.setFixedSize(28, 28)
        font = self.more_button.font()
        font.setPointSize(16)
        self.more_button.setFont(font)
        self.more_button.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(self)
        self.review_button = self.more_menu.addAction("Review bản dịch", self.open_selected_review)
        self.open_output_action = self.more_menu.addAction("Mở kết quả", self.open_outputs)
        self.export_button = self.more_menu.addAction(
            "Xuất lại bản đã review", lambda: self.start_jobs(export_only=True)
        )
        self.more_menu.addSeparator()
        self.delete_button = self.more_menu.addAction("Xóa khỏi lịch sử", self.delete_jobs)
        self.cancel_button = self.more_menu.addAction("Hủy", self.cancel_jobs)
        self.more_button.setMenu(self.more_menu)
        toolbar.addWidget(self.more_button)
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
        self.job_table.itemSelectionChanged.connect(self.update_selection_actions)
        self.job_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.job_table.customContextMenuRequested.connect(self.open_job_menu)
        self.job_stack = QStackedWidget()
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.addStretch()
        empty_title = QLabel("Thả tài liệu vào đây để bắt đầu")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = empty_title.font()
        font.setPointSize(16)
        empty_title.setFont(font)
        empty_layout.addWidget(empty_title)
        hint = QLabel("Hoặc dùng Add để chọn file hoặc cả thư mục. Hỗ trợ DOCX, PPTX, XLSX và PDF.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        empty_layout.addWidget(hint)
        empty_layout.addStretch()
        self.job_stack.addWidget(self.empty_page)
        self.job_stack.addWidget(self.job_table)
        layout.addWidget(self.job_stack, 1)

        options = QHBoxLayout()
        options.addWidget(QLabel("Dịch Trung → Anh:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem(self.profile.name, "online")
        self.provider_combo.addItem("Offline — Argos Trung → Anh", "offline")
        self.provider_combo.setCurrentIndex(1 if self.preferences.get("provider") == "offline" else 0)
        self.provider_combo.currentIndexChanged.connect(self.update_privacy_label)
        options.addWidget(self.provider_combo, 2)
        options.addSpacing(16)
        options.addWidget(QLabel("Xuất:"))
        self.mode_combo = QComboBox()
        for mode, name in MODE_NAMES.items():
            self.mode_combo.addItem(name, mode)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(
            self.preferences.get("mode", "both")
        )))
        options.addWidget(self.mode_combo, 1)
        layout.addLayout(options)
        self.privacy_label = QLabel()
        self.privacy_label.setWordWrap(True)
        layout.addWidget(self.privacy_label)
        self.mode_combo.setToolTip("PDF → Office là DOCX dựng lại. Office đầu vào giữ định dạng gốc.")
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Lưu vào:"))
        self.output_edit = QLineEdit(self.preferences.get(
            "output_dir", str(Path.home() / "Documents/Translations")
        ))
        self.output_browse_action = self.output_edit.addAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self.output_browse_action.triggered.connect(self.choose_output)
        output_row.addWidget(self.output_edit, 1)
        layout.addLayout(output_row)
        actions = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        actions.addWidget(self.progress_bar, 1)
        actions.addStretch()
        self.start_button = self.button("Dịch / Tiếp tục", self.start_jobs, actions)
        self.start_button.setMinimumSize(190, 36)
        self.start_button.setStyleSheet(
            "QPushButton { border-radius: 6px; padding: 6px 14px; }"
            "QPushButton:enabled { background: #2463a6; color: white; border: 1px solid #2463a6; }"
            "QPushButton:enabled:hover { background: #1d528d; }"
            "QPushButton:disabled { background: palette(button); color: palette(mid); "
            "border: 1px solid palette(mid); }"
        )
        self.pause_button = self.button("Tạm dừng", self.pause_jobs, actions)
        self.pause_button.setMinimumSize(190, 36)
        layout.addLayout(actions)
        self.tabs.addTab(page, "Tài liệu & lịch sử")
        self.visible_jobs = {}
        self.update_privacy_label()
        self.set_busy(False)

    def update_selection_actions(self):
        ids = self.selected_ids()
        busy = getattr(self, "busy", False)
        self.selection_summary.setText(self.tr("{selected}/{total} đã chọn").format(
            selected=len(ids), total=self.job_table.rowCount()
        ))
        self.start_button.setEnabled(bool(ids) and not busy)
        self.more_button.setEnabled(bool(ids) or busy)
        self.review_button.setEnabled(
            len(ids) == 1 and not busy and self.store.document_path(ids[0]).exists()
        )
        self.export_button.setEnabled(bool(ids) and not busy)
        self.delete_button.setEnabled(bool(ids) and not busy)
        self.open_output_action.setEnabled(any(
            self.visible_jobs.get(job_id, {}).get("output_dir") for job_id in ids
        ))

    def open_job_menu(self, point):
        item = self.job_table.itemAt(point)
        if item is None:
            return
        if item.row() not in {index.row() for index in self.job_table.selectedIndexes()}:
            self.job_table.selectRow(item.row())
        self.more_menu.exec(self.job_table.viewport().mapToGlobal(point))

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
        layout.addWidget(QLabel(
            "Bộ thuật ngữ automotive/Bosch/AUTOSAR: {count} mục có thể chỉnh sửa.".format(
                count=len(default_glossary())
            )
        ))
        self.glossary_search = QLineEdit()
        self.glossary_search.setPlaceholderText("Tìm thuật ngữ")
        self.glossary_search.textChanged.connect(self.filter_glossary)
        layout.addWidget(self.glossary_search)
        self.glossary_enabled = QCheckBox("Áp dụng thuật ngữ khi dịch")
        self.glossary_enabled.setChecked(self.preferences.get("glossary_enabled", True))
        layout.addWidget(self.glossary_enabled)
        self.glossary_table = QTableWidget(0, 2)
        self.glossary_table.setHorizontalHeaderLabels(["Tiếng Trung", "Tiếng Anh"])
        self.glossary_table.horizontalHeader().setStretchLastSection(True)
        self.glossary_table.setColumnWidth(0, 400)
        for source, target in self.preferences.get("glossary", default_glossary()).items():
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
        self.button("Khôi phục thuật ngữ automotive", self.restore_automotive_glossary, actions)
        self.button("Nguồn thuật ngữ", self.show_glossary_sources, actions)
        self.glossary_edit_buttons = [actions.itemAt(i).widget() for i in range(actions.count() - 1)]
        layout.addLayout(actions)
        layout.addWidget(
            QLabel("Đổi glossary khi đang dịch dở: tạo job mới để giữ nhất quán bản dịch.")
        )
        self.tabs.addTab(page, "Thuật ngữ")

    def build_settings(self):
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Cài đặt")
        self.settings_dialog.resize(740, 620)
        layout = QVBoxLayout(self.settings_dialog)
        self.settings_tabs = QTabWidget()
        layout.addWidget(self.settings_tabs)

        general_page = QWidget()
        general_layout = QVBoxLayout(general_page)
        general_form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Sáng", "light")
        self.theme_combo.addItem("Tối", "dark")
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.theme))
        general_form.addRow("Giao diện:", self.theme_combo)
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Tiếng Việt", "vi")
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
        general_form.addRow("Ngôn ngữ giao diện:", self.language_combo)
        general_layout.addLayout(general_form)
        general_layout.addWidget(QLabel("Ngôn ngữ giao diện không đổi ngôn ngữ dịch: Trung → Anh."))
        general_layout.addStretch()
        self.settings_tabs.addTab(general_page, "Chung")

        online_scroll = QScrollArea()
        online_scroll.setWidgetResizable(True)
        online_page = QWidget()
        online_scroll.setWidget(online_page)
        online_layout = QVBoxLayout(online_page)
        note = QLabel("Dùng dịch vụ tương thích OpenAI Chat Completions; có thể đổi nhà cung cấp và model.")
        note.setWordWrap(True)
        online_layout.addWidget(note)
        online_form = QFormLayout()
        self.service_name_edit = QLineEdit(self.tr(self.profile.name))
        self.endpoint_edit = QLineEdit(self.profile.endpoint)
        self.endpoint_edit.setPlaceholderText("https://api.example.com/v1 hoặc URL đầy đủ")
        self.model_edit = QLineEdit(self.profile.model)
        self.model_edit.setPlaceholderText("Nhập model ID do nhà cung cấp cung cấp")
        online_form.addRow("Tên dịch vụ:", self.service_name_edit)
        online_form.addRow("API URL:", self.endpoint_edit)
        online_form.addRow("Model ID:", self.model_edit)
        self.key_edit = QLineEdit(self.api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Nhập API key của bạn")
        online_form.addRow("API key:", self.key_edit)
        self.auth_enabled = QCheckBox("Dùng xác thực API")
        self.auth_enabled.setChecked(bool(self.profile.auth_header))
        online_form.addRow("", self.auth_enabled)
        show_key = QCheckBox("Hiện API key")
        show_key.toggled.connect(lambda checked: self.key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        ))
        online_form.addRow("", show_key)
        online_layout.addLayout(online_form)
        key_actions = QHBoxLayout()
        self.button("Lưu key", self.save_key, key_actions)
        self.button("Xóa key", self.clear_key, key_actions)
        self.connection_button = self.button("Kiểm tra kết nối", self.test_connection, key_actions)
        online_layout.addLayout(key_actions)
        self.key_status = QLabel()
        self.key_status.setWordWrap(True)
        online_layout.addWidget(self.key_status)
        for text in (
            "Key được lưu trong kho mật khẩu hệ điều hành. Có thể dùng key tạm trong phiên này.",
            "Kiểm tra kết nối gửi một câu thử ngắn, có thể được dịch vụ tính phí.",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            online_layout.addWidget(label)

        self.advanced_button = QPushButton("Tuỳ chọn nâng cao")
        self.advanced_button.setCheckable(True)
        online_layout.addWidget(self.advanced_button)
        self.advanced_panel = QWidget()
        advanced_form = QFormLayout(self.advanced_panel)
        self.auth_header_edit = QLineEdit(self.profile.auth_header or "Authorization")
        self.auth_prefix_edit = QLineEdit(
            self.profile.auth_prefix if self.profile.auth_header else "Bearer "
        )
        self.auth_enabled.toggled.connect(self.auth_header_edit.setEnabled)
        self.auth_enabled.toggled.connect(self.auth_prefix_edit.setEnabled)
        self.auth_header_edit.setEnabled(self.auth_enabled.isChecked())
        self.auth_prefix_edit.setEnabled(self.auth_enabled.isChecked())
        advanced_form.addRow("Header xác thực:", self.auth_header_edit)
        advanced_form.addRow("Prefix xác thực:", self.auth_prefix_edit)
        hint = QLabel("Ví dụ: Authorization + 'Bearer ' hoặc api-key + prefix trống.")
        hint.setWordWrap(True)
        advanced_form.addRow("", hint)
        self.batch_chars_spin = QSpinBox()
        self.batch_chars_spin.setRange(100, 1_000_000)
        self.batch_chars_spin.setValue(self.profile.batch_chars)
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1, 1_000_000)
        self.max_tokens_spin.setValue(self.profile.max_output_tokens)
        self.context_window_spin = QSpinBox()
        self.context_window_spin.setRange(2048, 10_000_000)
        self.context_window_spin.setValue(self.profile.context_window_tokens)
        self.token_margin_spin = QSpinBox()
        self.token_margin_spin.setRange(0, 1_000_000)
        self.token_margin_spin.setValue(self.profile.token_safety_margin)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 3600)
        self.timeout_spin.setValue(self.profile.timeout_seconds)
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 20)
        self.retries_spin.setValue(self.profile.retries)
        advanced_form.addRow("Ký tự mỗi batch:", self.batch_chars_spin)
        advanced_form.addRow("Token đầu ra tối đa:", self.max_tokens_spin)
        advanced_form.addRow("Context window (token):", self.context_window_spin)
        advanced_form.addRow("Token dự phòng:", self.token_margin_spin)
        budget_hint = QLabel("Nhập context window thật của model. App ước lượng đầu vào theo byte UTF-8, chừa token đầu ra và tự chia nhỏ khi vượt giới hạn.")
        budget_hint.setWordWrap(True)
        advanced_form.addRow("", budget_hint)
        advanced_form.addRow("Timeout (giây):", self.timeout_spin)
        advanced_form.addRow("Số lần thử lại:", self.retries_spin)
        online_layout.addWidget(self.advanced_panel)
        self.advanced_panel.hide()
        self.advanced_button.toggled.connect(self.advanced_panel.setVisible)
        self.apply_provider_button = QPushButton("Lưu dịch vụ")
        self.apply_provider_button.clicked.connect(lambda: self.save_provider_settings(True))
        online_layout.addWidget(self.apply_provider_button)
        online_layout.addStretch()
        self.settings_tabs.addTab(online_scroll, "Dịch vụ online")

        offline_page = QWidget()
        offline_layout = QVBoxLayout(offline_page)
        offline_form = QFormLayout()
        model_row = QHBoxLayout()
        self.argos_model_edit = QLineEdit(self.preferences.get("argos_model", ""))
        self.argos_model_edit.setPlaceholderText("Dùng model đi kèm nếu để trống")
        model_row.addWidget(self.argos_model_edit)
        self.button("Chọn model…", self.choose_argos_model, model_row)
        offline_form.addRow("Model offline:", model_row)
        model_link = QLabel(
            '<a href="https://www.argosopentech.com/argospm/index/">'
            'Argos Translate Package Index ↗</a>'
        )
        model_link.setOpenExternalLinks(True)
        offline_form.addRow("Tải model:", model_link)
        hint = QLabel("Chọn package Trung → Anh (.argosmodel). Offline cần runtime Argos.")
        hint.setWordWrap(True)
        offline_form.addRow("", hint)
        self.ocr_language = QComboBox()
        self.ocr_language.addItem("Trung giản thể + phồn thể + Anh", "chi_sim+chi_tra+eng")
        self.ocr_language.addItem("Trung giản thể + Anh", "chi_sim+eng")
        self.ocr_language.addItem("Trung phồn thể + Anh", "chi_tra+eng")
        self.ocr_language.addItem("Anh (tài liệu thử)", "eng")
        self.ocr_language.setCurrentIndex(max(0, self.ocr_language.findData(
            self.preferences.get("ocr_language", "chi_sim+chi_tra+eng")
        )))
        offline_form.addRow("OCR:", self.ocr_language)
        offline_layout.addLayout(offline_form)
        offline_layout.addStretch()
        self.settings_tabs.addTab(offline_page, "Offline & OCR")

        actions = QHBoxLayout()
        actions.addStretch()
        self.button("Đóng", self.settings_dialog.close, actions)
        layout.addLayout(actions)
        self.settings_dialog.finished.connect(self.save_settings_only)
        self.theme_combo.currentIndexChanged.connect(self.change_appearance)
        self.language_combo.currentIndexChanged.connect(self.change_appearance)
        self.ocr_language.currentIndexChanged.connect(self.save_display_preferences)
        self.argos_model_edit.editingFinished.connect(self.save_display_preferences)

    def provider_from_settings(self):
        return ProviderConfig(
            name=self.service_name_edit.text().strip() or "Dịch online",
            endpoint=normalize_endpoint(self.endpoint_edit.text()),
            model=self.model_edit.text().strip(),
            auth_header=self.auth_header_edit.text().strip() if self.auth_enabled.isChecked() else "",
            auth_prefix=self.auth_prefix_edit.text() if self.auth_enabled.isChecked() else "",
            batch_chars=self.batch_chars_spin.value(),
            max_output_tokens=self.max_tokens_spin.value(),
            timeout_seconds=self.timeout_spin.value(),
            retries=self.retries_spin.value(),
            context_window_tokens=self.context_window_spin.value(),
            token_safety_margin=self.token_margin_spin.value(),
        )

    def save_settings_only(self):
        self.save_provider_settings()
        self.save_display_preferences()

    def save_provider_settings(self, require_valid=False):
        try:
            profile = self.provider_from_settings()
            if require_valid:
                if self.auth_enabled.isChecked() and not profile.auth_header:
                    raise ValueError("Tên header xác thực không hợp lệ.")
                profile.validate()
            profile.save()
            self.profile = profile
            self.endpoint_edit.setText(profile.endpoint)
            self.provider_combo.setItemText(0, self.tr(profile.name))
            sources = self.provider_combo.property("item_sources") or []
            if sources:
                sources[0] = profile.name
                self.provider_combo.setProperty("item_sources", sources)
            self.show_status("Đã lưu cấu hình dịch vụ.")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def tr(self, text):
        return translate(str(text), self.language)

    def show_status(self, text):
        self.status_message = str(text)
        self.statusBar().showMessage(self.tr(text))

    def bind_translations(self):
        """Bind static labels once, leaving document text and user inputs untouched."""
        dynamic = (self.review_title, self.pdf_preview, self.privacy_label, self.key_status)
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QAbstractButton, QLabel)) and widget not in dynamic:
                text = widget.text()
                if text in ENGLISH or any(
                    s.split("{")[0] and text.startswith(s.split("{")[0]) for s in TEMPLATES
                ):
                    widget.setProperty("translation_source", text)
            elif isinstance(widget, QLineEdit):
                if widget.placeholderText() in ENGLISH:
                    widget.setProperty("placeholder_source", widget.placeholderText())
            elif isinstance(widget, QComboBox):
                widget.setProperty("item_sources", [widget.itemText(i) for i in range(widget.count())])

        for action in self.findChildren(QAction):
            if action.text() in ENGLISH:
                action.setProperty("translation_source", action.text())

    def retranslate_ui(self):
        self.setWindowTitle(self.tr("Converter — Trung → Anh"))
        self.settings_dialog.setWindowTitle(self.tr("Cài đặt"))
        self.settings_button.setToolTip(self.tr("Cài đặt"))
        self.settings_button.setAccessibleName(self.tr("Cài đặt"))
        self.settings_button.setIcon(settings_icon(self.palette().windowText().color()))
        self.more_button.setToolTip(self.tr("Thao tác khác"))
        self.more_button.setAccessibleName(self.tr("Thao tác khác"))
        self.output_browse_action.setToolTip(self.tr("Chọn thư mục"))
        self.mode_combo.setToolTip(self.tr("PDF → Office là DOCX dựng lại. Office đầu vào giữ định dạng gốc."))
        for action in self.findChildren(QAction):
            if action.property("translation_source"):
                action.setText(self.tr(action.property("translation_source")))
        for widget in self.findChildren(QWidget):
            source = widget.property("translation_source")
            if source:
                widget.setText(self.tr(source))
            placeholder = widget.property("placeholder_source")
            if placeholder:
                widget.setPlaceholderText(self.tr(placeholder))
            if isinstance(widget, QComboBox):
                for index, text in enumerate(widget.property("item_sources") or []):
                    widget.setItemText(index, self.tr(text))
        for index, title in enumerate(("Tài liệu & lịch sử", "Review", "Thuật ngữ")):
            self.tabs.setTabText(index, self.tr(title).replace("&", "&&"))
        for index, title in enumerate(("Chung", "Dịch vụ online", "Offline & OCR")):
            self.settings_tabs.setTabText(index, self.tr(title).replace("&", "&&"))
        for table, labels in (
            (self.job_table, ["Tài liệu", "Đầu ra Office", "Trạng thái", "Kết quả / lỗi"]),
            (self.review_table, ["Vị trí", "Nguồn", "Bản dịch", "Cảnh báo"]),
            (self.glossary_table, ["Tiếng Trung", "Tiếng Anh"]),
        ):
            table.setHorizontalHeaderLabels([self.tr(label) for label in labels])
        if not self.review_id:
            self.review_title.setText(self.tr("Chọn một tài liệu trong danh sách để review."))
        if self.pdf_preview.pixmap().isNull():
            self.pdf_preview.setText(self.tr("Preview PDF khi chọn đoạn."))
        if self.review_doc:
            self.warning_view.setPlainText("\n".join(self.tr(w) for w in self.review_doc.warnings))
            for row, segment in enumerate(self.review_doc.segments):
                self.review_table.item(row, 3).setText(self.tr(segment.warning))
        if self.key_status.property("message_source"):
            self.set_key_status(self.key_status.property("message_source"))
        self.update_privacy_label()
        self.update_markdown_preview()
        self.refresh_jobs()
        if hasattr(self, "status_message"):
            self.show_status(self.status_message)

    def open_settings(self):
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def change_appearance(self):
        self.theme = self.theme_combo.currentData()
        self.language = self.language_combo.currentData()
        apply_theme(self.theme)
        self.retranslate_ui()
        self.save_display_preferences()

    def save_display_preferences(self):
        self.preferences.update({
            "theme": self.theme,
            "language": self.language,
            "ocr_language": self.ocr_language.currentData(),
            "argos_model": self.argos_model_edit.text().strip(),
        })
        try:
            save_preferences(self.preferences)
        except OSError as exc:
            self.error(exc)

    def set_key_status(self, text):
        self.key_status.setProperty("message_source", str(text))
        self.key_status.setText(self.tr(text))

    def choose_argos_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Chọn model…"), self.argos_model_edit.text(),
            "Argos model (*.argosmodel)",
        )
        if path:
            self.argos_model_edit.setText(path)
            self.save_display_preferences()

    def update_privacy_label(self):
        self.privacy_label.setText(
            self.tr("Nội dung được gửi đến dịch vụ online đã cấu hình.")
            if self.provider_combo.currentData() == "online"
            else self.tr("Dịch trên máy bằng Argos; nội dung không gửi đến API.")
        )

    def error(self, message):
        QMessageBox.warning(self, "Converter", self.tr(message))

    def selected_ids(self):
        return [
            self.job_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in sorted({index.row() for index in self.job_table.selectedIndexes()})
        ]

    def refresh_jobs(self):
        selected = set(self.selected_ids())
        self.job_table.setRowCount(0)
        self.visible_jobs = {job["id"]: job for job in self.store.list()}
        for job in self.visible_jobs.values():
            row = self.job_table.rowCount()
            self.job_table.insertRow(row)
            name = QTableWidgetItem(job["name"])
            name.setData(Qt.ItemDataRole.UserRole, job["id"])
            ext = Path(job["name"]).suffix.upper().lstrip(".")
            output = self.tr("DOCX dựng lại") if ext == "PDF" else ext
            state = self.tr(self.progress_messages.get(
                job["id"], STATUS.get(job["status"], job["status"])
            ))
            results = []
            for kind, value in job["exports"].items():
                if value.get("status") == "done":
                    results.append(f"{self.tr(MODE_NAMES[kind])}: {Path(value['path']).name}")
                elif value.get("status") == "stale":
                    results.append(f"{self.tr(MODE_NAMES[kind])}: {self.tr('cần xuất lại')}")
            for col, item in enumerate(
                [
                    name,
                    QTableWidgetItem(output),
                    QTableWidgetItem(state),
                    QTableWidgetItem(self.tr(job["error"]) if job["error"] else " · ".join(results)),
                ]
            ):
                self.job_table.setItem(row, col, item)
            if job["id"] in selected:
                self.job_table.selectionModel().select(
                    self.job_table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

        self.job_stack.setCurrentWidget(
            self.job_table if self.job_table.rowCount() else self.empty_page
        )
        self.update_selection_actions()

    def add_paths(self, paths):
        if self.process:
            return
        added = []
        failures = []
        for path in paths:
            try:
                added.append(self.store.add(Path(path)))
            except Exception as exc:
                failures.append(f"{Path(path).name}: {self.tr(exc)}")
        if failures:
            self.error(self.tr("Không nhập được {count} file:\n{errors}").format(
                count=len(failures), errors="\n".join(failures[:10])
            ))
        if not added:
            return
        self.refresh_jobs()
        self.job_table.clearSelection()
        for row in range(self.job_table.rowCount()):
            if self.job_table.item(row, 0).data(Qt.ItemDataRole.UserRole) in added:
                self.job_table.selectionModel().select(
                    self.job_table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
        self.show_status("Đã thêm {count} tài liệu.".format(count=len(added)))

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Thêm tài liệu"), "", "Documents (*.docx *.pptx *.xlsx *.pdf)"
        )
        self.add_paths(paths)

    def add_folder(self):
        if self.process:
            return
        folder = QFileDialog.getExistingDirectory(self, self.tr("Chọn thư mục tài liệu"))
        if folder:
            self.import_folder(Path(folder))

    def import_folder(self, folder):
        """Scan subfolders, skipping lock files and the app's own job/output directories."""
        if self.process:
            return
        root = Path(folder).resolve()
        excluded = {self.store.root.resolve()}
        if self.output_edit.text().strip():
            output = Path(self.output_edit.text()).expanduser().resolve()
            if output != root:
                excluded.add(output)
        paths = []
        errors = []
        for directory, dirs, names in os.walk(root, onerror=errors.append):
            current = Path(directory)
            if current.resolve() in excluded:
                dirs[:] = []
                continue
            dirs[:] = sorted(d for d in dirs if (current / d).resolve() not in excluded)
            for name in sorted(names):
                path = current / name
                if not name.startswith("~$") and path.suffix.lower() in SUPPORTED:
                    paths.append(path)
        if paths:
            self.add_paths(paths)
        elif not errors:
            self.show_status("Không tìm thấy file DOCX, PPTX, XLSX hoặc PDF trong thư mục.")
        if errors:
            self.error("\n".join(str(error) for error in errors[:10]))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.process:
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        for path in paths:
            if path.is_dir():
                self.import_folder(path)
        self.add_paths([path for path in paths if path.is_file()])

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Thư mục kết quả"), self.output_edit.text()
        )
        if path:
            self.output_edit.setText(path)

    def glossary_entries(self):
        result = {}
        for row in range(self.glossary_table.rowCount()):
            source = self.glossary_table.item(row, 0)
            target = self.glossary_table.item(row, 1)
            if source and source.text().strip():
                if not target or not target.text().strip():
                    raise ValueError("Thuật ngữ phải có cả nguồn và bản dịch.")
                result[source.text().strip()] = target.text().strip()
        return result

    def glossary(self):
        return self.glossary_entries() if self.glossary_enabled.isChecked() else {}

    def filter_glossary(self):
        search = self.glossary_search.text().casefold()
        for row in range(self.glossary_table.rowCount()):
            text = " ".join(
                item.text() for col in range(2)
                if (item := self.glossary_table.item(row, col)) is not None
            )
            self.glossary_table.setRowHidden(row, search not in text.casefold())

    def restore_automotive_glossary(self):
        if self.process:
            return
        present = {
            item.text().strip() for row in range(self.glossary_table.rowCount())
            if (item := self.glossary_table.item(row, 0)) is not None
        }
        for source, target in default_glossary().items():
            if source not in present:
                row = self.glossary_table.rowCount()
                self.glossary_table.insertRow(row)
                self.glossary_table.setItem(row, 0, QTableWidgetItem(source))
                self.glossary_table.setItem(row, 1, QTableWidgetItem(target))
        self.filter_glossary()

    def show_glossary_sources(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Nguồn thuật ngữ"))
        dialog.resize(720, 500)
        layout = QVBoxLayout(dialog)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        note = self.tr("Thuật ngữ Trung được biên soạn cho app; tên tiếng Anh đối chiếu nguồn chính thức Bosch/AUTOSAR.")
        links = "".join(
            f'<li><a href="{escape(source["url"], quote=True)}">{escape(source["title"])}</a></li>'
            for source in automotive_pack()["sources"]
        )
        view.setHtml(f"<p>{escape(note)}</p><ul>{links}</ul>")
        layout.addWidget(view)
        dialog.exec()

    def persist_preferences(self):
        if not self.save_provider_settings():
            return False
        try:
            self.preferences.update(
                {
                    "provider": self.provider_combo.currentData(),
                    "mode": self.mode_combo.currentData(),
                    "output_dir": self.output_edit.text(),
                    "ocr_language": self.ocr_language.currentData(),
                    "glossary": self.glossary_entries(),
                    "glossary_enabled": self.glossary_enabled.isChecked(),
                    "theme": self.theme,
                    "language": self.language,
                    "argos_model": self.argos_model_edit.text().strip(),
                }
            )
            save_preferences(self.preferences)
            self.show_status("Đã lưu cài đặt.")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def set_busy(self, busy):
        self.busy = busy
        self.start_button.setVisible(not busy)
        self.pause_button.setVisible(busy)
        self.progress_bar.setVisible(busy)
        self.cancel_button.setVisible(busy)
        for button in [
            self.start_button,
            self.export_button,
            self.add_button,
            self.add_files_action,
            self.add_folder_action,
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
            self.glossary_table.setEnabled(not busy)
            self.glossary_enabled.setEnabled(not busy)
            for button in self.glossary_edit_buttons:
                button.setEnabled(not busy)

        self.update_selection_actions()

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
                if self.profile.auth_header and not self.api_key:
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
                "argos_model": self.argos_model_edit.text().strip(),
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
            self.show_status(
                "Sẽ tạm dừng sau request/batch đang xử lý; tiến độ được giữ."
            )

    def cancel_jobs(self):
        if self.cancel_event:
            self.cancel_event.set()
            self.show_status("Đang hủy; bản dịch đã hoàn thành vẫn được giữ.")

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
        self.show_status("Đã lưu tiến độ. Xem trạng thái và kết quả trong danh sách.")

    def poll(self):
        if self.events:
            while True:
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                if event["kind"] == "progress":
                    self.progress_messages[event["id"]] = event["message"]
                    self.show_status(event["message"])
                    if event["total"]:
                        self.progress_bar.setRange(0, event["total"])
                        self.progress_bar.setValue(event["done"])
                    self.refresh_jobs()
                elif event["kind"] == "error":
                    self.show_status(event["message"])
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
                self.set_key_status(event["message"])
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
        self.warning_view.setPlainText("\n".join(self.tr(w) for w in doc.warnings))
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
            warning = QTableWidgetItem(self.tr(segment.warning))
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
            self.show_status("Đã lưu review; xuất lại để nhận file cập nhật.")
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
            self.markdown_preview.setPlainText(self.tr("Markdown preview có sau khi hoàn thành bản dịch."))

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
            self.pdf_preview.setText(self.tr("Không render được trang PDF."))

    def export_report(self):
        if not self.review_id:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Xuất báo cáo"), "report.json", "JSON (*.json)")
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
            self.set_key_status("Đã lưu key vào kho mật khẩu hệ điều hành.")
        except Exception:
            self.set_key_status(
                "Kho mật khẩu không khả dụng; key chỉ dùng trong phiên hiện tại."
            )

    def clear_key(self):
        try:
            set_api_key("")
            self.key_edit.clear()
            self.api_key = ""
            self.set_key_status("Đã xóa key.")
        except Exception:
            self.error("Không xóa được key trong kho mật khẩu hệ điều hành.")

    def test_connection(self):
        if self.connection_process:
            return
        if not self.save_provider_settings(True):
            return
        self.connection_events = self.context.Queue()
        self.connection_process = self.context.Process(
            target=test_online,
            args=(asdict(self.profile), self.key_edit.text().strip(), self.connection_events),
        )
        self.connection_process.start()
        self.connection_button.setEnabled(False)
        self.set_key_status("Đang kiểm tra kết nối…")

    def closeEvent(self, event):
        if self.process and self.process.is_alive():
            self.pause_jobs()
            self.show_status(
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
