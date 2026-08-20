from __future__ import annotations

import threading
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

from config import Settings, load_settings
from exporter import Exporter
from service import MonitorService
from storage import Storage

try:
    import ttkbootstrap as tb
except ImportError:  # pragma: no cover - optional dependency
    tb = None


class MailMonitorGUI:
    """一体化桌面界面：配置、启动、收集、导出都在这里完成。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.storage = Storage(self.settings.resolve_path(self.settings.db_path))
        self.queue: Queue = Queue()
        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.service = self._new_service(self.settings)

        self.root = tb.Window(themename="flatly") if tb else tk.Tk()
        self.root.title("公司邮件智能监控工具 - 本地保密版")
        self.root.geometry("1280x820")
        self.root.minsize(1080, 700)
        self._configure_style()
        self._build_variables()
        self._build_ui()
        self._load_recent_rows()
        self.root.after(200, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _new_service(self, settings: Settings) -> MonitorService:
        return MonitorService(
            settings,
            storage=self.storage,
            log_callback=self._push_log,
            result_callback=self._push_result,
            progress_callback=self._push_progress,
        )

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
            style.configure("SubTitle.TLabel", font=("Microsoft YaHei UI", 10))
            style.configure("Card.TLabelframe", padding=10)
            style.configure("Danger.TLabel", foreground="#b00020")
            style.configure("Good.TLabel", foreground="#0f7b0f")
            style.configure("Big.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=8)
        except tk.TclError:
            pass

    def _build_variables(self) -> None:
        self.server_var = tk.StringVar(value=self.settings.imap_server)
        self.port_var = tk.StringVar(value=str(self.settings.imap_port))
        self.user_var = tk.StringVar(value=self.settings.imap_username)
        self.password_var = tk.StringVar(value=self.settings.imap_password)
        self.folder_var = tk.StringVar(value=self.settings.imap_folder)
        self.ssl_var = tk.BooleanVar(value=self.settings.imap_ssl)
        self.poll_var = tk.StringVar(value=str(self.settings.poll_interval))

        self.ollama_url_var = tk.StringVar(value=self.settings.ollama_base_url)
        self.model_var = tk.StringVar(value=self.settings.ollama_model)
        self.thread_var = tk.StringVar(value=str(self.settings.ollama_num_thread))
        self.ctx_var = tk.StringVar(value=str(self.settings.ollama_num_ctx))
        self.timeout_var = tk.StringVar(value=str(self.settings.ollama_timeout))
        self.remote_ollama_var = tk.BooleanVar(value=self.settings.allow_remote_ollama)

        self.categories_var = tk.StringVar(value=",".join(self.settings.categories))
        self.whitelist_var = tk.StringVar(value=",".join(self.settings.rule_whitelist))
        self.keywords_var = tk.StringVar(value=",".join(self.settings.rule_keywords))
        self.body_len_var = tk.StringVar(value=str(self.settings.ai_body_max_len))
        self.preview_len_var = tk.StringVar(value=str(self.settings.body_preview_len))
        self.retry_var = tk.StringVar(value=str(self.settings.max_retry))

        self.start_date_var = tk.StringVar(value=(date.today() - timedelta(days=1)).isoformat())
        self.end_date_var = tk.StringVar(value=date.today().isoformat())
        self.search_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="待命：本地保密模式已启用")
        self.progress_var = tk.IntVar(value=0)
        self.password_visible_var = tk.BooleanVar(value=False)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_header()
        self._build_left_panel()
        self._build_tabs()

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, padding=(14, 10))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="公司邮件智能监控工具", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="只连公司 IMAP + 本机 Ollama；不注册、不上云、不外传正文",
            style="SubTitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.status_label = ttk.Label(header, textvariable=self.status_var, style="Good.TLabel")
        self.status_label.grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_left_panel(self) -> None:
        panel = ttk.Frame(self.root, padding=(12, 0, 8, 12))
        panel.grid(row=1, column=0, sticky="ns")
        panel.columnconfigure(0, weight=1)

        actions = ttk.LabelFrame(panel, text="一键操作", padding=10)
        actions.grid(row=0, column=0, sticky="ew")
        for i in range(2):
            actions.columnconfigure(i, weight=1)

        ttk.Button(actions, text="保存配置", command=self.save_config, style="Big.TButton").grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(actions, text="开始常驻监控", command=self.start_watch, style="Big.TButton").grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(actions, text="收集今天", command=lambda: self.collect_quick(0), style="Big.TButton").grid(row=2, column=0, sticky="ew", pady=4, padx=(0, 4))
        ttk.Button(actions, text="收集昨天", command=lambda: self.collect_quick(1), style="Big.TButton").grid(row=2, column=1, sticky="ew", pady=4, padx=(4, 0))
        ttk.Button(actions, text="按日期收集", command=self.start_collect, style="Big.TButton").grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(actions, text="停止", command=self.stop, style="Big.TButton").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        checks = ttk.LabelFrame(panel, text="本地检查", padding=10)
        checks.grid(row=1, column=0, sticky="ew", pady=10)
        ttk.Button(checks, text="刷新 Ollama 模型", command=self.refresh_models).pack(fill=tk.X, pady=3)
        ttk.Button(checks, text="测试本地 Ollama", command=self.test_ollama).pack(fill=tk.X, pady=3)
        ttk.Button(checks, text="打开导出目录", command=self.choose_export_dir).pack(fill=tk.X, pady=3)

        progress = ttk.LabelFrame(panel, text="进度", padding=10)
        progress.grid(row=2, column=0, sticky="ew")
        self.progress = ttk.Progressbar(progress, variable=self.progress_var, maximum=100, length=230)
        self.progress.pack(fill=tk.X)
        self.progress_text = ttk.Label(progress, text="0/0")
        self.progress_text.pack(anchor="e", pady=(4, 0))

        privacy = ttk.LabelFrame(panel, text="保密状态", padding=10)
        privacy.grid(row=3, column=0, sticky="ew", pady=10)
        ttk.Label(privacy, text="✓ 邮件正文只进本机 Ollama", style="Good.TLabel").pack(anchor="w")
        ttk.Label(privacy, text="✓ .env / 数据库 / 导出已忽略提交", style="Good.TLabel").pack(anchor="w", pady=2)
        ttk.Label(privacy, text="✓ 默认拒绝远程 Ollama", style="Good.TLabel").pack(anchor="w")

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=1, sticky="nsew", padx=(0, 12), pady=(0, 12))
        self._build_overview_tab()
        self._build_config_tab()
        self._build_rules_tab()
        self._build_export_log_tab()

    def _build_overview_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        self.notebook.add(tab, text="总览")

        date_box = ttk.LabelFrame(tab, text="一键收集日期范围", padding=10)
        date_box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for i in range(8):
            date_box.columnconfigure(i, weight=1)
        ttk.Label(date_box, text="开始日期").grid(row=0, column=0, sticky="w")
        ttk.Entry(date_box, textvariable=self.start_date_var, width=14).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(date_box, text="结束日期").grid(row=0, column=2, sticky="w")
        ttk.Entry(date_box, textvariable=self.end_date_var, width=14).grid(row=0, column=3, sticky="w", padx=6)
        ttk.Button(date_box, text="今天", command=lambda: self._set_date_range(0)).grid(row=0, column=4, padx=4)
        ttk.Button(date_box, text="昨天", command=lambda: self._set_date_range(1)).grid(row=0, column=5, padx=4)
        ttk.Button(date_box, text="近7天", command=lambda: self._set_recent_days(7)).grid(row=0, column=6, padx=4)

        filter_box = ttk.Frame(tab)
        filter_box.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        filter_box.columnconfigure(1, weight=1)
        ttk.Label(filter_box, text="筛选").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(filter_box, textvariable=self.search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=6)
        entry.bind("<KeyRelease>", lambda _event: self.refresh_table())
        ttk.Button(filter_box, text="刷新结果", command=self.refresh_table).grid(row=0, column=2)

        columns = ("processed_at", "received_at", "importance", "category", "sender", "subject", "summary", "status")
        self.tree = ttk.Treeview(tab, columns=columns, show="headings")
        headers = {
            "processed_at": "处理时间",
            "received_at": "收件时间",
            "importance": "紧急度",
            "category": "分类",
            "sender": "发件人",
            "subject": "主题",
            "summary": "摘要",
            "status": "状态",
        }
        widths = {"processed_at": 150, "received_at": 150, "importance": 80, "category": 90, "sender": 180, "subject": 270, "summary": 300, "status": 80}
        for column in columns:
            self.tree.heading(column, text=headers[column])
            self.tree.column(column, width=widths[column], anchor="w")
        self.tree.grid(row=2, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

    def _build_config_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        self.notebook.add(tab, text="配置")

        imap = ttk.LabelFrame(tab, text="公司邮箱 IMAP", padding=12)
        imap.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        imap.columnconfigure(1, weight=1)
        self._row_entry(imap, 0, "服务器", self.server_var)
        self._row_entry(imap, 1, "端口", self.port_var)
        self._row_entry(imap, 2, "账号", self.user_var)
        self.password_entry = self._row_entry(imap, 3, "密码/授权码", self.password_var, show="*")
        ttk.Checkbutton(imap, text="显示密码", variable=self.password_visible_var, command=self._toggle_password).grid(row=4, column=1, sticky="w", pady=4)
        self._row_entry(imap, 5, "文件夹", self.folder_var)
        ttk.Checkbutton(imap, text="SSL 连接", variable=self.ssl_var).grid(row=6, column=1, sticky="w", pady=4)
        self._row_entry(imap, 7, "监控间隔秒", self.poll_var)

        ai = ttk.LabelFrame(tab, text="本地 Ollama", padding=12)
        ai.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ai.columnconfigure(1, weight=1)
        self._row_entry(ai, 0, "地址", self.ollama_url_var)
        ttk.Label(ai, text="模型").grid(row=1, column=0, sticky="w", pady=5)
        self.model_combo = ttk.Combobox(ai, textvariable=self.model_var)
        self.model_combo.grid(row=1, column=1, sticky="ew", pady=5)
        self._row_entry(ai, 2, "线程数", self.thread_var)
        self._row_entry(ai, 3, "上下文", self.ctx_var)
        self._row_entry(ai, 4, "超时秒", self.timeout_var)
        ttk.Checkbutton(ai, text="允许远程 Ollama（不推荐）", variable=self.remote_ollama_var).grid(row=5, column=1, sticky="w", pady=4)
        ttk.Label(ai, text="保密建议：保持 http://localhost:11434", style="Danger.TLabel").grid(row=6, column=1, sticky="w", pady=4)

    def _build_rules_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        tab.columnconfigure(1, weight=1)
        self.notebook.add(tab, text="规则与分类")
        self._row_entry(tab, 0, "分类列表", self.categories_var)
        self._row_entry(tab, 1, "发件人白名单", self.whitelist_var)
        self._row_entry(tab, 2, "高优先关键词", self.keywords_var)
        self._row_entry(tab, 3, "正文给AI字数", self.body_len_var)
        self._row_entry(tab, 4, "预览字数", self.preview_len_var)
        self._row_entry(tab, 5, "失败重试次数", self.retry_var)
        tip = "白名单或关键词命中后，紧急度会强制 high；但仍会用本地 Ollama 做分类和摘要。"
        ttk.Label(tab, text=tip, style="SubTitle.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=12)

    def _build_export_log_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self.notebook.add(tab, text="日志与导出")

        buttons = ttk.Frame(tab)
        buttons.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(buttons, text="导出 CSV", command=self.export_csv).pack(side=tk.LEFT)
        ttk.Button(buttons, text="导出 Markdown", command=self.export_markdown).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="导出 JSONL", command=self.export_jsonl).pack(side=tk.LEFT)
        ttk.Button(buttons, text="清空界面日志", command=lambda: self.log_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=6)

        self.log_text = tk.Text(tab, height=16, wrap="word")
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _row_entry(self, parent, row: int, label: str, variable: tk.Variable, show: str = ""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 8))
        entry = ttk.Entry(parent, textvariable=variable, show=show)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        return entry

    def _toggle_password(self) -> None:
        self.password_entry.configure(show="" if self.password_visible_var.get() else "*")

    def _set_date_range(self, days_ago: int) -> None:
        target = date.today() - timedelta(days=days_ago)
        self.start_date_var.set(target.isoformat())
        self.end_date_var.set(target.isoformat())

    def _set_recent_days(self, days: int) -> None:
        self.start_date_var.set((date.today() - timedelta(days=days - 1)).isoformat())
        self.end_date_var.set(date.today().isoformat())

    def _settings_from_form(self) -> Settings:
        settings = deepcopy(self.settings)
        settings.imap_server = self.server_var.get().strip()
        settings.imap_port = int(self.port_var.get().strip() or "993")
        settings.imap_username = self.user_var.get().strip()
        settings.imap_password = self.password_var.get().strip()
        settings.imap_folder = self.folder_var.get().strip() or "INBOX"
        settings.imap_ssl = bool(self.ssl_var.get())
        settings.poll_interval = int(self.poll_var.get().strip() or "10")
        settings.ollama_base_url = self.ollama_url_var.get().strip() or "http://localhost:11434"
        settings.ollama_model = self.model_var.get().strip() or settings.ollama_model
        settings.ollama_num_thread = int(self.thread_var.get().strip() or "8")
        settings.ollama_num_ctx = int(self.ctx_var.get().strip() or "2048")
        settings.ollama_timeout = int(self.timeout_var.get().strip() or "120")
        settings.allow_remote_ollama = bool(self.remote_ollama_var.get())
        settings.categories = [item.strip() for item in self.categories_var.get().split(",") if item.strip()]
        settings.rule_whitelist = [item.strip() for item in self.whitelist_var.get().split(",") if item.strip()]
        settings.rule_keywords = [item.strip() for item in self.keywords_var.get().split(",") if item.strip()]
        settings.ai_body_max_len = int(self.body_len_var.get().strip() or "3000")
        settings.body_preview_len = int(self.preview_len_var.get().strip() or "200")
        settings.max_retry = int(self.retry_var.get().strip() or "3")
        settings.validate_security()
        return settings

    def save_config(self) -> None:
        try:
            self.settings = self._settings_from_form()
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        env_path = self.settings.workspace / ".env"
        lines = [
            "# 公司邮件智能监控工具 — 本地保密配置",
            "# 由 GUI 自动保存；不要提交这个文件",
            "",
            "# ---- IMAP 邮箱配置 ----",
            f"IMAP_SERVER={self.settings.imap_server}",
            f"IMAP_PORT={self.settings.imap_port}",
            f"IMAP_USERNAME={self.settings.imap_username}",
            f"IMAP_PASSWORD={self.settings.imap_password}",
            f"IMAP_SSL={1 if self.settings.imap_ssl else 0}",
            f"IMAP_FOLDER={self.settings.imap_folder}",
            "IMAP_SEARCH=ALL",
            f"IMAP_TIMEOUT={self.settings.imap_timeout}",
            f"POLL_INTERVAL={self.settings.poll_interval}",
            "PREFER_IDLE=0",
            "",
            "# ---- Ollama 本地 AI 配置 ----",
            f"OLLAMA_BASE_URL={self.settings.ollama_base_url}",
            f"OLLAMA_MODEL={self.settings.ollama_model}",
            f"OLLAMA_TIMEOUT={self.settings.ollama_timeout}",
            f"OLLAMA_NUM_THREAD={self.settings.ollama_num_thread}",
            f"OLLAMA_NUM_CTX={self.settings.ollama_num_ctx}",
            f"ALLOW_REMOTE_OLLAMA={1 if self.settings.allow_remote_ollama else 0}",
            "",
            "# ---- AI 与规则 ----",
            f"AI_BODY_MAX_LEN={self.settings.ai_body_max_len}",
            f"CATEGORIES={','.join(self.settings.categories)}",
            f"RULE_WHITELIST={','.join(self.settings.rule_whitelist)}",
            f"RULE_KEYWORDS={','.join(self.settings.rule_keywords)}",
            "",
            "# ---- 本地输出 ----",
            f"DB_PATH={self.settings.db_path}",
            f"OUTPUT_MD={self.settings.output_md}",
            f"RESULTS_JSONL={self.settings.results_jsonl}",
            f"LOG_FILE={self.settings.log_file}",
            f"EXPORTS_DIR={self.settings.exports_dir}",
            f"BODY_PREVIEW_LEN={self.settings.body_preview_len}",
            f"MAX_RETRY={self.settings.max_retry}",
        ]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.service = self._new_service(self.settings)
        self._push_log(f"配置已保存：{env_path}")
        self.status_var.set("配置已保存，本地保密模式启用")

    def start_watch(self) -> None:
        self._start_worker(lambda: self.service.watch(self.stop_event), "常驻监控已启动")

    def start_collect(self) -> None:
        try:
            start_date = date.fromisoformat(self.start_date_var.get().strip())
            end_date = date.fromisoformat(self.end_date_var.get().strip())
        except ValueError:
            messagebox.showerror("日期错误", "日期格式必须是 YYYY-MM-DD")
            return
        self._start_worker(lambda: self.service.collect(start_date, end_date, self.stop_event), f"一键收集已启动：{start_date} ~ {end_date}")

    def collect_quick(self, days_ago: int) -> None:
        self._set_date_range(days_ago)
        self.start_collect()

    def _start_worker(self, target, status_text: str) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提示", "任务已在运行中。")
            return
        try:
            self.settings = self._settings_from_form()
            self.service = self._new_service(self.settings)
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        self.stop_event = threading.Event()

        def guarded_target() -> None:
            try:
                self._push_log(status_text)
                self.status_var.set(status_text)
                target()
            except Exception as exc:
                self._push_log(f"任务异常：{type(exc).__name__}: {exc}")
                self.status_var.set("任务异常，请查看日志")

        self.worker_thread = threading.Thread(target=guarded_target, daemon=True)
        self.worker_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._push_log("已发出停止信号，当前邮件处理完成后停止。")
        self.status_var.set("正在停止...")

    def refresh_models(self) -> None:
        try:
            self.settings = self._settings_from_form()
            self.service = self._new_service(self.settings)
            models = self.service.list_models()
        except Exception as exc:
            messagebox.showerror("模型读取失败", str(exc))
            return
        self.model_combo["values"] = models
        if models and self.model_var.get() not in models:
            self.model_var.set(models[0])
        self._push_log("已刷新本地 Ollama 模型列表。")

    def test_ollama(self) -> None:
        try:
            self.refresh_models()
            self.status_var.set("本地 Ollama 连接正常")
        except Exception:
            # refresh_models 已弹窗
            pass

    def choose_export_dir(self) -> None:
        folder = filedialog.askdirectory(initialdir=str(self.settings.resolve_path(self.settings.exports_dir)))
        if folder:
            self.settings.exports_dir = Path(folder)
            self._push_log(f"导出目录已选择：{folder}")

    def export_csv(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            Exporter(self.settings, self.storage).export_csv(path)
            self._push_log(f"已导出 CSV：{path}")

    def export_markdown(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")])
        if path:
            Exporter(self.settings, self.storage).export_markdown(path)
            self._push_log(f"已导出 Markdown：{path}")

    def export_jsonl(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".jsonl", filetypes=[("JSONL", "*.jsonl")])
        if path:
            Exporter(self.settings, self.storage).export_jsonl(path)
            self._push_log(f"已导出 JSONL：{path}")

    def refresh_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._load_recent_rows()

    def _load_recent_rows(self) -> None:
        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        rows = self.storage.list_mails(limit=500)
        for row in reversed(rows):
            text = " ".join(str(row.get(key, "")) for key in ("importance", "category", "sender", "subject", "summary", "status")).lower()
            if query and query not in text:
                continue
            self._insert_row(row)

    def _insert_row(self, row: dict) -> None:
        self.tree.insert(
            "",
            0,
            values=(
                row.get("processed_at", ""),
                row.get("received_at", ""),
                row.get("importance", ""),
                row.get("category", ""),
                row.get("sender", ""),
                row.get("subject", ""),
                row.get("summary", ""),
                row.get("status", ""),
            ),
        )

    def _push_log(self, message: str) -> None:
        self.queue.put(("log", message))

    def _push_result(self, row: dict) -> None:
        self.queue.put(("result", row))

    def _push_progress(self, current: int, total: int) -> None:
        self.queue.put(("progress", (current, total)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self.log_text.insert("1.0", payload + "\n")
                elif kind == "result":
                    self._insert_row(payload)
                    self.status_var.set("收到并处理了一封邮件")
                elif kind == "progress":
                    current, total = payload
                    percent = 0 if total <= 0 else min(100, int(current * 100 / total))
                    self.progress_var.set(percent)
                    self.progress_text.config(text=f"{current}/{total}")
        except Empty:
            pass
        self.root.after(200, self._poll_queue)

    def _on_close(self) -> None:
        self.stop_event.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_gui() -> None:
    MailMonitorGUI().run()
