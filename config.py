from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - graceful fallback
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


DEFAULT_CATEGORIES = ["报价", "客户咨询", "新增任务", "会议", "报表", "通知", "垃圾邮件", "其他"]
LOCAL_OLLAMA_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _parse_csv(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = list(value)
    return [item.strip() for item in items if item and item.strip()]


def _safe_int(value: str | int | None, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    workspace: Path
    imap_server: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_ssl: bool = True
    imap_timeout: int = 30
    imap_folder: str = "INBOX"
    imap_search: str = "ALL"
    poll_interval: int = 30
    prefer_idle: bool = True

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_timeout: int = 120
    ollama_num_thread: int = 8
    ollama_num_ctx: int = 2048
    allow_remote_ollama: bool = False

    ai_body_max_len: int = 3000
    body_preview_len: int = 200
    categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))

    rule_whitelist: list[str] = field(default_factory=list)
    rule_keywords: list[str] = field(default_factory=lambda: ["紧急", "urgent", "asap", "加急", "重要", "important"])

    db_path: Path = Path("mail_monitor.db")
    output_md: Path = Path("index.md")
    results_jsonl: Path = Path("results.jsonl")
    log_file: Path = Path("monitor.log")
    exports_dir: Path = Path("exports")

    max_retry: int = 3

    @property
    def mailbox_key(self) -> str:
        return f"{self.imap_server}|{self.imap_username}|{self.imap_folder}"

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.workspace / path).resolve()

    def validate_security(self) -> None:
        parsed = urlparse(self.ollama_base_url)
        host = (parsed.hostname or "").lower()
        if not self.allow_remote_ollama and host not in LOCAL_OLLAMA_HOSTS:
            raise ValueError("为保证保密，OLLAMA_BASE_URL 只允许 localhost / 127.0.0.1 / ::1")

    def prepare_directories(self) -> None:
        self.resolve_path(self.exports_dir).mkdir(parents=True, exist_ok=True)
        self.resolve_path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def redacted(self) -> dict[str, str]:
        return {
            "imap_server": self.imap_server,
            "imap_port": str(self.imap_port),
            "imap_username": self.imap_username,
            "imap_password": "***",
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
        }


def load_settings(workspace: str | Path | None = None, env_file: str = ".env") -> Settings:
    workspace_path = Path(workspace or Path(__file__).resolve().parent).resolve()
    env_path = workspace_path / env_file
    if env_path.exists():
        load_dotenv(env_path)

    settings = Settings(
        workspace=workspace_path,
        imap_server=os.getenv("IMAP_SERVER", ""),
        imap_port=_safe_int(os.getenv("IMAP_PORT"), 993),
        imap_username=os.getenv("IMAP_USERNAME", ""),
        imap_password=os.getenv("IMAP_PASSWORD", ""),
        imap_ssl=_parse_bool(os.getenv("IMAP_SSL"), True),
        imap_timeout=_safe_int(os.getenv("IMAP_TIMEOUT"), 30),
        imap_folder=os.getenv("IMAP_FOLDER", "INBOX"),
        imap_search=os.getenv("IMAP_SEARCH", "ALL"),
        poll_interval=_safe_int(os.getenv("POLL_INTERVAL"), 30),
        prefer_idle=_parse_bool(os.getenv("PREFER_IDLE"), True),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
        ollama_timeout=_safe_int(os.getenv("OLLAMA_TIMEOUT"), 120),
        ollama_num_thread=_safe_int(os.getenv("OLLAMA_NUM_THREAD"), 8),
        ollama_num_ctx=_safe_int(os.getenv("OLLAMA_NUM_CTX"), 2048),
        allow_remote_ollama=_parse_bool(os.getenv("ALLOW_REMOTE_OLLAMA"), False),
        ai_body_max_len=_safe_int(os.getenv("AI_BODY_MAX_LEN"), 3000),
        body_preview_len=_safe_int(os.getenv("BODY_PREVIEW_LEN"), 200),
        categories=_parse_csv(os.getenv("CATEGORIES")) or list(DEFAULT_CATEGORIES),
        rule_whitelist=_parse_csv(os.getenv("RULE_WHITELIST")),
        rule_keywords=_parse_csv(os.getenv("RULE_KEYWORDS")) or ["紧急", "urgent", "asap", "加急", "重要", "important"],
        db_path=Path(os.getenv("DB_PATH", "mail_monitor.db")),
        output_md=Path(os.getenv("OUTPUT_MD", "index.md")),
        results_jsonl=Path(os.getenv("RESULTS_JSONL", "results.jsonl")),
        log_file=Path(os.getenv("LOG_FILE", "monitor.log")),
        exports_dir=Path(os.getenv("EXPORTS_DIR", "exports")),
        max_retry=_safe_int(os.getenv("MAX_RETRY"), 3),
    )
    settings.validate_security()
    settings.prepare_directories()
    return settings
