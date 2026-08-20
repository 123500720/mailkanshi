from __future__ import annotations

import imaplib
import sys
import threading
import traceback
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from config import Settings, load_settings
from diagnostics import humanize_error
from exporter import Exporter
from service import MonitorService
from storage import Storage

try:
    from PySide6.QtCore import Qt, QThread, Signal, QDate, QTimer
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDateEdit,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSplitter,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise RuntimeError("缺少 PySide6。请运行：pip install PySide6") from exc

APP_QSS = """
QMainWindow,QWidget{background:#0f172a;color:#e5e7eb;font-family:'Microsoft YaHei UI','Segoe UI';font-size:13px}
QFrame#Sidebar{background:#0b1120;border-right:1px solid #1e293b} QLabel#AppTitle{font-size:20px;font-weight:800;color:#f8fafc}
QLabel#HeroTitle{font-size:24px;font-weight:800;color:#f8fafc} QLabel#Muted{color:#94a3b8}
QPushButton{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:9px 13px;color:#e5e7eb} QPushButton:hover{background:#334155} QPushButton:disabled{background:#111827;color:#64748b;border-color:#1f2937}
QPushButton#PrimaryButton{background:#2563eb;border-color:#3b82f6;color:white;font-weight:700} QPushButton#PrimaryButton:hover{background:#1d4ed8}
QPushButton#DangerButton{background:#7f1d1d;border-color:#991b1b;color:#fee2e2;font-weight:700}
QPushButton#NavButton{text-align:left;border:0;border-radius:12px;padding:11px 14px;color:#cbd5e1;background:transparent} QPushButton#NavButton:checked{background:#1d4ed8;color:white;font-weight:700}
QFrame#TopBar,QFrame#Card,QGroupBox{background:#111c33;border:1px solid #243044;border-radius:16px} QGroupBox{margin-top:12px;padding:16px 12px 12px 12px;font-weight:700}
QGroupBox::title{subcontrol-origin:margin;left:14px;padding:0 6px;color:#bfdbfe}
QLineEdit,QComboBox,QDateEdit,QPlainTextEdit,QTextEdit{background:#0b1220;border:1px solid #334155;border-radius:10px;padding:8px;color:#f8fafc;selection-background-color:#2563eb}
QLineEdit[invalid="true"],QComboBox[invalid="true"],QDateEdit[invalid="true"],QPlainTextEdit[invalid="true"]{border:1px solid #ef4444;background:#1f1118}
QTableWidget{background:#0b1220;gridline-color:#1e293b;border:1px solid #243044;border-radius:12px;selection-background-color:#1d4ed8;alternate-background-color:#101a2e}
QHeaderView::section{background:#111c33;color:#cbd5e1;padding:8px;border:0;border-right:1px solid #243044;font-weight:700}
QListWidget{background:#0b1220;border:1px solid #243044;border-radius:12px;padding:6px} QListWidget::item{padding:10px;border-radius:10px} QListWidget::item:selected{background:#1d4ed8}
QProgressBar{background:#0b1220;border:1px solid #334155;border-radius:8px;height:12px;text-align:center} QProgressBar::chunk{background:#22c55e;border-radius:7px}
"""

STATE_META = {
    "idle": ("待命", "#64748b"),
    "watching": ("监控中", "#22c55e"),
    "collecting": ("处理中", "#eab308"),
    "stopping": ("停止中", "#f97316"),
    "error": ("异常", "#ef4444"),
}


class UserFacingError(ValueError):
    def __init__(self, message: str, widget: QWidget | None = None, page_index: int | None = None) -> None:
        super().__init__(message)
        self.widget = widget
        self.page_index = page_index


class ServiceThread(QThread):
    log_signal = Signal(str)
    result_signal = Signal(dict)
    progress_signal = Signal(int, int)
    status_signal = Signal(str)
    error_signal = Signal(str)
    models_signal = Signal(list)

    def __init__(self, settings: Settings, storage: Storage, mode: str, start_date: date | None = None, end_date: date | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.storage = storage
        self.mode = mode
        self.start_date = start_date
        self.end_date = end_date
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            svc = MonitorService(
                self.settings,
                storage=self.storage,
                log_callback=lambda msg: self.log_signal.emit("INFO | " + msg),
                result_callback=self.result_signal.emit,
                progress_callback=self.progress_signal.emit,
            )
            if self.mode == "watch":
                self.status_signal.emit("常驻监控运行中")
                svc.watch(self.stop_event)
                self.status_signal.emit("常驻监控已停止")
            elif self.mode == "collect":
                if not self.start_date or not self.end_date:
                    raise ValueError("收集模式缺少日期范围")
                self.status_signal.emit(f"正在收集 {self.start_date} ~ {self.end_date}")
                svc.collect(self.start_date, self.end_date, self.stop_event)
                self.status_signal.emit("一键收集完成")
            elif self.mode == "models":
                self.status_signal.emit("正在读取本地 Ollama 模型")
                self.models_signal.emit(svc.list_models())
                self.status_signal.emit("本地 Ollama 连接正常")
            else:
                raise ValueError(f"未知任务：{self.mode}")
        except Exception as exc:
            self.error_signal.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}")
            self.status_signal.emit("任务异常，请查看日志")

class FirstRunDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("首次启动向导")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)

        title = QLabel("欢迎使用本地 AI 邮件助理")
        title.setStyleSheet("font-size:22px;font-weight:800;color:#f8fafc")
        intro = QLabel("请按 4 步完成初始化：公司邮箱 → 测试 IMAP → 测试 Ollama → 保存并开始监控。")
        intro.setObjectName("Muted")
        layout.addWidget(title)
        layout.addWidget(intro)

        form_box = QGroupBox("1. 公司邮箱 IMAP")
        form = QFormLayout(form_box)
        self.server_edit = QLineEdit(settings.imap_server)
        self.port_edit = QLineEdit(str(settings.imap_port or 993))
        self.user_edit = QLineEdit(settings.imap_username)
        self.password_edit = QLineEdit(settings.imap_password)
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.folder_edit = QLineEdit(settings.imap_folder or "INBOX")
        form.addRow("IMAP 服务器", self.server_edit)
        form.addRow("端口", self.port_edit)
        form.addRow("邮箱账号", self.user_edit)
        form.addRow("密码/授权码", self.password_edit)
        form.addRow("文件夹", self.folder_edit)
        layout.addWidget(form_box)

        ai_box = QGroupBox("3. 本地 Ollama")
        ai_form = QFormLayout(ai_box)
        self.ollama_edit = QLineEdit(settings.ollama_base_url)
        self.model_edit = QLineEdit(settings.ollama_model)
        ai_form.addRow("Ollama 地址", self.ollama_edit)
        ai_form.addRow("模型", self.model_edit)
        layout.addWidget(ai_box)

        test_row = QHBoxLayout()
        self.imap_result = QLabel("2. IMAP 尚未测试")
        self.ollama_result = QLabel("3. Ollama 尚未测试")
        test_imap_btn = QPushButton("测试 IMAP")
        test_ollama_btn = QPushButton("测试 Ollama")
        test_imap_btn.clicked.connect(self.test_imap)
        test_ollama_btn.clicked.connect(self.test_ollama)
        test_row.addWidget(test_imap_btn)
        test_row.addWidget(self.imap_result, 1)
        test_row.addWidget(test_ollama_btn)
        test_row.addWidget(self.ollama_result, 1)
        layout.addLayout(test_row)

        self.autostart_check = QCheckBox("4. 保存后立即开始监控")
        self.autostart_check.setChecked(True)
        layout.addWidget(self.autostart_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存并完成")
        buttons.button(QDialogButtonBox.Cancel).setText("稍后再说")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str | bool]:
        return {
            "server": self.server_edit.text().strip(),
            "port": self.port_edit.text().strip(),
            "user": self.user_edit.text().strip(),
            "password": self.password_edit.text().strip(),
            "folder": self.folder_edit.text().strip() or "INBOX",
            "ollama_url": self.ollama_edit.text().strip() or "http://localhost:11434",
            "model": self.model_edit.text().strip(),
            "autostart": self.autostart_check.isChecked(),
        }

    def test_imap(self) -> None:
        try:
            values = self.values()
            if not values["server"] or not values["user"]:
                raise UserFacingError("请先填写 IMAP 服务器和邮箱账号。")
            port = int(str(values["port"] or "993"))
            client = imaplib.IMAP4_SSL(str(values["server"]), port, timeout=10)
            client.login(str(values["user"]), str(values["password"]))
            client.select(str(values["folder"] or "INBOX"), readonly=True)
            client.logout()
            self.imap_result.setText("IMAP 测试成功")
            self.imap_result.setStyleSheet("color:#22c55e")
        except Exception as exc:
            msg = humanize_error(f"IMAP {type(exc).__name__}: {exc}")
            self.imap_result.setText(msg)
            self.imap_result.setStyleSheet("color:#ef4444")

    def test_ollama(self) -> None:
        try:
            values = self.values()
            response = requests.get(str(values["ollama_url"]).rstrip("/") + "/api/tags", timeout=8)
            response.raise_for_status()
            self.ollama_result.setText("Ollama 测试成功")
            self.ollama_result.setStyleSheet("color:#22c55e")
        except Exception as exc:
            msg = humanize_error(f"Ollama {type(exc).__name__}: {exc}")
            self.ollama_result.setText(msg)
            self.ollama_result.setStyleSheet("color:#ef4444")

class MailMonitorModernWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or load_settings()
        self.storage = Storage(self.settings.resolve_path(self.settings.db_path))
        self.worker: ServiceThread | None = None
        self.rows: list[dict[str, Any]] = []
        self.nav_buttons: list[QPushButton] = []
        self.app_state = "idle"
        self._invalid_widgets: list[QWidget] = []
        self._env_exists_at_start = (self.settings.workspace / ".env").exists()

        self.setWindowTitle("公司邮件智能监控工具 - AI 工作台")
        self.resize(1360, 860)
        self.setMinimumSize(1120, 720)
        self._build_variables()
        self._build_ui()
        self.refresh_rows()
        self.update_dashboard()
        self.set_app_state("idle", "待命 · 本地保密模式")
        QTimer.singleShot(350, self.maybe_show_first_run_wizard)

    def _build_variables(self) -> None:
        s = self.settings
        self.status_label = QLabel("待命 · 本地保密模式")
        self.state_pill = QLabel("待命")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QLabel("0/0")

        self.server_edit = QLineEdit(s.imap_server)
        self.port_edit = QLineEdit(str(s.imap_port))
        self.user_edit = QLineEdit(s.imap_username)
        self.password_edit = QLineEdit(s.imap_password)
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.folder_edit = QLineEdit(s.imap_folder)
        self.ssl_check = QCheckBox("SSL 连接")
        self.ssl_check.setChecked(s.imap_ssl)
        self.poll_edit = QLineEdit(str(s.poll_interval))

        self.ollama_url_edit = QLineEdit(s.ollama_base_url)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItem(s.ollama_model)
        self.thread_edit = QLineEdit(str(s.ollama_num_thread))
        self.ctx_edit = QLineEdit(str(s.ollama_num_ctx))
        self.timeout_edit = QLineEdit(str(s.ollama_timeout))
        self.remote_check = QCheckBox("允许远程 Ollama（不推荐）")
        self.remote_check.setChecked(s.allow_remote_ollama)

        self.categories_edit = QPlainTextEdit(",".join(s.categories))
        self.whitelist_edit = QPlainTextEdit(",".join(s.rule_whitelist))
        self.keywords_edit = QPlainTextEdit(",".join(s.rule_keywords))
        self.body_len_edit = QLineEdit(str(s.ai_body_max_len))
        self.preview_len_edit = QLineEdit(str(s.body_preview_len))
        self.retry_edit = QLineEdit(str(s.max_retry))

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-1))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar())
        layout.addWidget(self._content(), 1)

    def _sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(238)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        title = QLabel("Mail Kanshi")
        title.setObjectName("AppTitle")
        sub = QLabel("Local AI Inbox")
        sub.setObjectName("Muted")
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addSpacing(18)
        for text, idx in [("仪表盘", 0), ("收件工作台", 1), ("规则与分类", 2), ("设置", 3), ("日志与导出", 4)]:
            btn = QPushButton(text)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked=False, i=idx: self.switch_page(i))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch(1)
        privacy = QLabel("✓ 公司 IMAP\n✓ 本机 Ollama\n✓ 不注册不上云")
        privacy.setObjectName("Muted")
        layout.addWidget(privacy)
        return side

    def _content(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(self._topbar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._dashboard())
        self.stack.addWidget(self._inbox())
        self.stack.addWidget(self._rules())
        self.stack.addWidget(self._settings())
        self.stack.addWidget(self._logs())
        layout.addWidget(self.stack, 1)
        return wrapper

    def _topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("AI 邮件工作台")
        title.setObjectName("HeroTitle")
        self.status_label.setObjectName("Muted")
        self.progress_bar.setFixedWidth(180)
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(self.state_pill)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        return bar

    def _card(self, title: str, value: str, caption: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        title_label = QLabel(title)
        title_label.setObjectName("Muted")
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size:28px;font-weight:800;color:#f8fafc")
        caption_label = QLabel(caption)
        caption_label.setObjectName("Muted")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        card.value_label = value_label
        return card

    def _btn(self, text: str, slot, primary: bool = False, danger: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        if primary:
            btn.setObjectName("PrimaryButton")
        if danger:
            btn.setObjectName("DangerButton")
        return btn
    def _dashboard(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        grid = QGridLayout()
        self.card_today = self._card("今日处理", "0", "processed today")
        self.card_high = self._card("高优先", "0", "need attention")
        self.card_total = self._card("本地记录", "0", "stored in SQLite")
        self.card_ollama = self._card("Ollama", "未检测", "localhost only")
        for i, card in enumerate([self.card_today, self.card_high, self.card_total, self.card_ollama]):
            grid.addWidget(card, 0, i)
        layout.addLayout(grid)

        actions = QFrame()
        actions.setObjectName("Card")
        action_layout = QVBoxLayout(actions)
        action_layout.setContentsMargins(18, 18, 18, 18)
        action_layout.addWidget(QLabel("快速操作"))
        row1 = QHBoxLayout()
        self.start_watch_btn = self._btn("开始监控", self.start_watch, primary=True)
        self.stop_btn = self._btn("停止", self.stop_worker, danger=True)
        self.refresh_models_btn = self._btn("刷新模型", self.refresh_models)
        row1.addWidget(self.start_watch_btn)
        row1.addWidget(self.stop_btn)
        row1.addWidget(self.refresh_models_btn)
        row1.addStretch(1)
        action_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.collect_today_btn = self._btn("收集今天", lambda: self.collect_quick(0), primary=True)
        self.collect_yesterday_btn = self._btn("收集昨天", lambda: self.collect_quick(1))
        self.collect_range_btn = self._btn("按日期收集", self.start_collect)
        row2.addWidget(self.collect_today_btn)
        row2.addWidget(self.collect_yesterday_btn)
        row2.addWidget(QLabel("开始"))
        row2.addWidget(self.start_date_edit)
        row2.addWidget(QLabel("结束"))
        row2.addWidget(self.end_date_edit)
        row2.addWidget(self.collect_range_btn)
        row2.addStretch(1)
        action_layout.addLayout(row2)
        layout.addWidget(actions)

        latest = QFrame()
        latest.setObjectName("Card")
        latest_layout = QVBoxLayout(latest)
        latest_layout.setContentsMargins(18, 18, 18, 18)
        latest_layout.addWidget(QLabel("最近高优先邮件"))
        self.high_list = QListWidget()
        latest_layout.addWidget(self.high_list)
        layout.addWidget(latest, 1)
        return page

    def _inbox(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索发件人、主题、摘要...")
        self.importance_filter = QComboBox()
        self.importance_filter.addItems(["全部紧急度", "high", "normal", "low"])
        self.category_filter = QComboBox()
        self.category_filter.addItem("全部分类")
        self.category_filter.addItems(self.settings.categories)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_rows)
        filters.addWidget(self.search_edit, 1)
        filters.addWidget(self.importance_filter)
        filters.addWidget(self.category_filter)
        filters.addWidget(refresh_btn)
        layout.addLayout(filters)
        self.search_edit.textChanged.connect(self.populate_table)
        self.importance_filter.currentTextChanged.connect(self.populate_table)
        self.category_filter.currentTextChanged.connect(self.populate_table)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["紧急度", "分类", "发件人", "主题", "摘要", "处理时间"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        modes = [QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.Stretch, QHeaderView.ResizeToContents]
        for i, mode in enumerate(modes):
            self.table.horizontalHeader().setSectionResizeMode(i, mode)
        self.table.itemSelectionChanged.connect(self.update_detail)
        splitter.addWidget(self.table)

        detail = QFrame()
        detail.setObjectName("Card")
        detail.setMinimumWidth(330)
        detail_layout = QVBoxLayout(detail)
        self.detail_title = QLabel("选择一封邮件")
        self.detail_title.setStyleSheet("font-size:18px;font-weight:800")
        self.detail_meta = QLabel("-")
        self.detail_meta.setObjectName("Muted")
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addWidget(self.detail_text, 1)
        splitter.addWidget(detail)
        splitter.setSizes([860, 380])
        layout.addWidget(splitter, 1)
        return page

    def _rules(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        box = QGroupBox("AI 分类与本地规则")
        form = QFormLayout(box)
        for editor in [self.categories_edit, self.whitelist_edit, self.keywords_edit]:
            editor.setMinimumHeight(80)
        form.addRow("分类列表（逗号分隔）", self.categories_edit)
        form.addRow("发件人白名单", self.whitelist_edit)
        form.addRow("高优先关键词", self.keywords_edit)
        form.addRow("正文给 AI 字数", self.body_len_edit)
        form.addRow("正文预览字数", self.preview_len_edit)
        form.addRow("失败重试次数", self.retry_edit)
        layout.addWidget(box)
        layout.addWidget(self._btn("保存规则和配置", self.save_config, primary=True), alignment=Qt.AlignLeft)
        layout.addStretch(1)
        return page
    def _settings(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        imap_box = QGroupBox("公司邮箱 IMAP")
        imap_form = QFormLayout(imap_box)
        imap_form.addRow("服务器", self.server_edit)
        imap_form.addRow("端口", self.port_edit)
        imap_form.addRow("账号", self.user_edit)
        imap_form.addRow("密码/授权码", self.password_edit)
        imap_form.addRow("文件夹", self.folder_edit)
        imap_form.addRow("SSL", self.ssl_check)
        imap_form.addRow("监控间隔秒", self.poll_edit)

        ai_box = QGroupBox("本地 Ollama")
        ai_form = QFormLayout(ai_box)
        ai_form.addRow("地址", self.ollama_url_edit)
        ai_form.addRow("模型", self.model_combo)
        ai_form.addRow("线程数", self.thread_edit)
        ai_form.addRow("上下文", self.ctx_edit)
        ai_form.addRow("超时秒", self.timeout_edit)
        ai_form.addRow("远程", self.remote_check)

        storage_box = QGroupBox("本地存储与保密")
        storage_layout = QVBoxLayout(storage_box)
        storage_layout.addWidget(QLabel(f"数据库：{self.settings.resolve_path(self.settings.db_path)}"))
        storage_layout.addWidget(QLabel("邮件正文只送到本机 Ollama；.env、数据库、导出文件不提交。"))
        storage_layout.addWidget(self._btn("保存配置", self.save_config, primary=True))

        grid.addWidget(imap_box, 0, 0)
        grid.addWidget(ai_box, 0, 1)
        grid.addWidget(storage_box, 1, 0, 1, 2)
        grid.setRowStretch(2, 1)
        return page

    def _logs(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(self._btn("导出 CSV", self.export_csv))
        row.addWidget(self._btn("导出 Markdown", self.export_markdown))
        row.addWidget(self._btn("导出 JSONL", self.export_jsonl))
        clear_btn = QPushButton("清空界面日志")
        clear_btn.clicked.connect(lambda: self.log_text.clear())
        row.addWidget(clear_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text, 1)
        return page

    def switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

    def set_app_state(self, state: str, message: str | None = None) -> None:
        self.app_state = state
        label, color = STATE_META.get(state, STATE_META["idle"])
        self.state_pill.setText(label)
        self.state_pill.setStyleSheet(f"background:{color};color:white;border-radius:10px;padding:4px 10px;font-weight:700")
        if message:
            self.status_label.setText(message)
        busy = state in {"watching", "collecting", "stopping"}
        watching = state == "watching"
        collecting = state == "collecting"
        stopping = state == "stopping"
        self.start_watch_btn.setEnabled(not busy or state == "error")
        self.collect_today_btn.setEnabled(not busy or state == "error")
        self.collect_yesterday_btn.setEnabled(not busy or state == "error")
        self.collect_range_btn.setEnabled(not busy or state == "error")
        self.refresh_models_btn.setEnabled(not busy or state == "error")
        self.stop_btn.setEnabled((watching or collecting) and not stopping)
        self.start_date_edit.setEnabled(not busy)
        self.end_date_edit.setEnabled(not busy)

    def _clear_invalid_widgets(self) -> None:
        for widget in self._invalid_widgets:
            widget.setProperty("invalid", False)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self._invalid_widgets.clear()

    def _mark_invalid(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        widget.setProperty("invalid", True)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        self._invalid_widgets.append(widget)

    def _parse_int_field(self, widget: QLineEdit, name: str, default: int, page: int) -> int:
        value = widget.text().strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise UserFacingError(f"{name} 必须是数字。", widget, page) from exc

    def _settings_from_form(self) -> Settings:
        self._clear_invalid_widgets()
        settings = deepcopy(self.settings)
        if not self.server_edit.text().strip():
            raise UserFacingError("IMAP 服务器不能为空。", self.server_edit, 3)
        if not self.user_edit.text().strip():
            raise UserFacingError("邮箱账号不能为空。", self.user_edit, 3)
        settings.imap_server = self.server_edit.text().strip()
        settings.imap_port = self._parse_int_field(self.port_edit, "IMAP 端口", 993, 3)
        settings.imap_username = self.user_edit.text().strip()
        settings.imap_password = self.password_edit.text().strip()
        settings.imap_folder = self.folder_edit.text().strip() or "INBOX"
        settings.imap_ssl = self.ssl_check.isChecked()
        settings.poll_interval = self._parse_int_field(self.poll_edit, "监控间隔", 10, 3)
        settings.ollama_base_url = self.ollama_url_edit.text().strip() or "http://localhost:11434"
        settings.ollama_model = self.model_combo.currentText().strip() or settings.ollama_model
        settings.ollama_num_thread = self._parse_int_field(self.thread_edit, "线程数", 8, 3)
        settings.ollama_num_ctx = self._parse_int_field(self.ctx_edit, "上下文", 2048, 3)
        settings.ollama_timeout = self._parse_int_field(self.timeout_edit, "Ollama 超时", 120, 3)
        settings.allow_remote_ollama = self.remote_check.isChecked()
        settings.categories = self._csv(self.categories_edit.toPlainText())
        if not settings.categories:
            raise UserFacingError("分类列表不能为空。", self.categories_edit, 2)
        settings.rule_whitelist = self._csv(self.whitelist_edit.toPlainText())
        settings.rule_keywords = self._csv(self.keywords_edit.toPlainText())
        settings.ai_body_max_len = self._parse_int_field(self.body_len_edit, "正文给 AI 字数", 3000, 2)
        settings.body_preview_len = self._parse_int_field(self.preview_len_edit, "预览字数", 200, 2)
        settings.max_retry = self._parse_int_field(self.retry_edit, "失败重试次数", 3, 2)
        try:
            settings.validate_security()
        except ValueError as exc:
            raise UserFacingError(str(exc), self.ollama_url_edit, 3) from exc
        return settings

    @staticmethod
    def _csv(text: str) -> list[str]:
        return [item.strip() for item in text.replace("\n", ",").split(",") if item.strip()]
    def save_config(self, show_message: bool = True) -> bool:
        try:
            self.settings = self._settings_from_form()
        except UserFacingError as exc:
            self._mark_invalid(exc.widget)
            if exc.page_index is not None:
                self.switch_page(exc.page_index)
            QMessageBox.critical(self, "配置错误", str(exc))
            return False
        except Exception as exc:
            QMessageBox.critical(self, "配置错误", humanize_error(f"{type(exc).__name__}: {exc}"))
            return False
        settings = self.settings
        env_path = settings.workspace / ".env"
        lines = [
            "# 公司邮件智能监控工具 — 本地保密配置",
            "# 由现代 GUI 自动保存；不要提交这个文件",
            "",
            f"IMAP_SERVER={settings.imap_server}",
            f"IMAP_PORT={settings.imap_port}",
            f"IMAP_USERNAME={settings.imap_username}",
            f"IMAP_PASSWORD={settings.imap_password}",
            f"IMAP_SSL={1 if settings.imap_ssl else 0}",
            f"IMAP_FOLDER={settings.imap_folder}",
            "IMAP_SEARCH=ALL",
            f"IMAP_TIMEOUT={settings.imap_timeout}",
            f"POLL_INTERVAL={settings.poll_interval}",
            "PREFER_IDLE=0",
            "",
            f"OLLAMA_BASE_URL={settings.ollama_base_url}",
            f"OLLAMA_MODEL={settings.ollama_model}",
            f"OLLAMA_TIMEOUT={settings.ollama_timeout}",
            f"OLLAMA_NUM_THREAD={settings.ollama_num_thread}",
            f"OLLAMA_NUM_CTX={settings.ollama_num_ctx}",
            f"ALLOW_REMOTE_OLLAMA={1 if settings.allow_remote_ollama else 0}",
            "",
            f"AI_BODY_MAX_LEN={settings.ai_body_max_len}",
            f"CATEGORIES={','.join(settings.categories)}",
            f"RULE_WHITELIST={','.join(settings.rule_whitelist)}",
            f"RULE_KEYWORDS={','.join(settings.rule_keywords)}",
            "",
            f"DB_PATH={settings.db_path}",
            f"OUTPUT_MD={settings.output_md}",
            f"RESULTS_JSONL={settings.results_jsonl}",
            f"LOG_FILE={settings.log_file}",
            f"EXPORTS_DIR={settings.exports_dir}",
            f"BODY_PREVIEW_LEN={settings.body_preview_len}",
            f"MAX_RETRY={settings.max_retry}",
        ]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.append_log("INFO | 配置已保存：" + str(env_path))
        self.set_app_state("idle", "配置已保存 · 本地保密模式")
        self._sync_category_filter()
        if show_message:
            QMessageBox.information(self, "已保存", "配置已保存到本地 .env。")
        return True

    def _sync_category_filter(self) -> None:
        current = self.category_filter.currentText()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("全部分类")
        self.category_filter.addItems(self.settings.categories)
        index = self.category_filter.findText(current)
        self.category_filter.setCurrentIndex(index if index >= 0 else 0)
        self.category_filter.blockSignals(False)

    def maybe_show_first_run_wizard(self) -> None:
        if self._env_exists_at_start and self.settings.imap_server and self.settings.imap_username:
            return
        dialog = FirstRunDialog(self.settings, self)
        if dialog.exec() != QDialog.Accepted:
            self.switch_page(3)
            return
        values = dialog.values()
        self.server_edit.setText(str(values["server"]))
        self.port_edit.setText(str(values["port"] or "993"))
        self.user_edit.setText(str(values["user"]))
        self.password_edit.setText(str(values["password"]))
        self.folder_edit.setText(str(values["folder"] or "INBOX"))
        self.ollama_url_edit.setText(str(values["ollama_url"]))
        if values["model"]:
            self.model_combo.setEditText(str(values["model"]))
        if self.save_config(show_message=False) and values.get("autostart"):
            self.start_watch()

    def start_watch(self) -> None:
        self._start_worker("watch")

    def collect_quick(self, days_ago: int) -> None:
        target = date.today() - timedelta(days=days_ago)
        self._start_worker("collect", start_date=target, end_date=target)

    def start_collect(self) -> None:
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()
        self._start_worker("collect", start_date=start_date, end_date=end_date)

    def refresh_models(self) -> None:
        self._start_worker("models")

    def _start_worker(self, mode: str, start_date: date | None = None, end_date: date | None = None) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "任务运行中", "已有任务在运行，请先停止或等待完成。")
            return
        if mode == "collect" and start_date and end_date and end_date < start_date:
            self._mark_invalid(self.end_date_edit)
            self.switch_page(0)
            QMessageBox.critical(self, "日期错误", "结束日期不能早于开始日期。")
            return
        try:
            self.settings = self._settings_from_form()
        except UserFacingError as exc:
            self._mark_invalid(exc.widget)
            if exc.page_index is not None:
                self.switch_page(exc.page_index)
            QMessageBox.critical(self, "配置错误", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "配置错误", humanize_error(f"{type(exc).__name__}: {exc}"))
            return

        next_state = "watching" if mode == "watch" else "collecting"
        message = "常驻监控启动中" if mode == "watch" else ("正在刷新模型" if mode == "models" else "一键收集启动中")
        self.set_app_state(next_state, message)
        self.worker = ServiceThread(self.settings, self.storage, mode, start_date, end_date)
        self.worker.log_signal.connect(self.append_log)
        self.worker.result_signal.connect(self.on_result)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.status_signal.connect(self.status_label.setText)
        self.worker.error_signal.connect(self.on_error)
        self.worker.models_signal.connect(self.on_models)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def stop_worker(self) -> None:
        if self.worker and self.worker.isRunning():
            self.set_app_state("stopping", "正在停止...")
            self.worker.stop()
            self.append_log("WARN | 已发出停止信号，当前邮件处理完成后停止。")
        else:
            self.set_app_state("idle", "当前没有运行中的任务")

    def on_worker_finished(self) -> None:
        if self.app_state != "error":
            self.set_app_state("idle", "任务结束 · 待命")
        self.update_dashboard()
    def on_models(self, models: list[str]) -> None:
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(models or [current or self.settings.ollama_model])
        if current:
            index = self.model_combo.findText(current)
            self.model_combo.setCurrentIndex(index if index >= 0 else 0)
        self.card_ollama.value_label.setText("正常")
        self.append_log("INFO | 已刷新本地 Ollama 模型列表。")

    def on_result(self, row: dict) -> None:
        self.rows.insert(0, row)
        self.populate_table()
        self.update_dashboard()
        self.status_label.setText("收到并处理了一封邮件")

    def on_progress(self, current: int, total: int) -> None:
        percent = 0 if total <= 0 else min(100, int(current * 100 / total))
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"{current}/{total}")

    def on_error(self, detail: str) -> None:
        friendly = humanize_error(detail)
        self.set_app_state("error", friendly)
        self.append_log("ERROR | " + detail)
        QMessageBox.warning(self, "任务异常", friendly + "\n\n技术详情已写入日志页。")

    def append_log(self, message: str) -> None:
        if hasattr(self, "log_text"):
            self.log_text.append(message)

    def refresh_rows(self) -> None:
        self.rows = self.storage.list_mails(limit=500)
        self.populate_table()
        self.update_dashboard()

    def populate_table(self) -> None:
        if not hasattr(self, "table"):
            return
        query = self.search_edit.text().strip().lower()
        importance = self.importance_filter.currentText()
        category = self.category_filter.currentText()
        filtered: list[dict[str, Any]] = []
        for row in self.rows:
            blob = " ".join(str(row.get(key, "")) for key in ("sender", "subject", "summary", "category", "importance")).lower()
            if query and query not in blob:
                continue
            if importance != "全部紧急度" and row.get("importance") != importance:
                continue
            if category != "全部分类" and row.get("category") != category:
                continue
            filtered.append(row)
        self.table.setRowCount(len(filtered))
        self.table.filtered_rows = filtered
        for row_index, row in enumerate(filtered):
            values = [
                row.get("importance", ""),
                row.get("category", ""),
                row.get("sender", ""),
                row.get("subject", ""),
                row.get("summary", ""),
                row.get("processed_at", ""),
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col_index == 0 and value == "high":
                    item.setForeground(QColor("#fecaca"))
                self.table.setItem(row_index, col_index, item)
        if filtered:
            self.table.selectRow(0)

    def update_detail(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        rows = getattr(self.table, "filtered_rows", [])
        if not selected or selected[0].row() >= len(rows):
            return
        row = rows[selected[0].row()]
        self.detail_title.setText(str(row.get("subject", "无主题"))[:80])
        self.detail_meta.setText(
            f"{row.get('importance', '')} · {row.get('category', '')} · {row.get('sender', '')}\n{row.get('received_at', '')}"
        )
        self.detail_text.setPlainText(
            "摘要：" + str(row.get("summary", ""))
            + "\n\n规则：" + str(row.get("rule_hit", ""))
            + "\n\n正文预览：\n" + str(row.get("body_preview", ""))
        )

    def update_dashboard(self) -> None:
        rows = self.storage.list_mails(limit=500)
        today = date.today().isoformat()
        high_rows = [row for row in rows if row.get("importance") == "high"]
        self.card_today.value_label.setText(str(sum(1 for row in rows if str(row.get("processed_at", "")).startswith(today))))
        self.card_high.value_label.setText(str(len(high_rows)))
        self.card_total.value_label.setText(str(len(rows)))
        if hasattr(self, "high_list"):
            self.high_list.clear()
            for row in high_rows[:12]:
                self.high_list.addItem(QListWidgetItem(f"{row.get('category', '')} · {row.get('subject', '')}\n{row.get('sender', '')}"))

    def export_csv(self) -> None:
        self._export("csv", "CSV (*.csv)", lambda path: Exporter(self.settings, self.storage).export_csv(path))

    def export_markdown(self) -> None:
        self._export("md", "Markdown (*.md)", lambda path: Exporter(self.settings, self.storage).export_markdown(path))

    def export_jsonl(self) -> None:
        self._export("jsonl", "JSONL (*.jsonl)", lambda path: Exporter(self.settings, self.storage).export_jsonl(path))

    def _export(self, ext: str, filter_text: str, fn) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"导出 {ext.upper()}",
            str(self.settings.resolve_path(self.settings.exports_dir) / f"result.{ext}"),
            filter_text,
        )
        if not path:
            return
        try:
            fn(path)
            self.append_log(f"INFO | 已导出：{path}")
            QMessageBox.information(self, "导出完成", f"文件已导出：\n{path}")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            self.append_log("ERROR | 导出失败：" + detail)
            QMessageBox.warning(self, "导出失败", humanize_error(detail))

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        event.accept()


def launch_modern_gui() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
    window = MailMonitorModernWindow()
    window.show()
    app.exec()
