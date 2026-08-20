from __future__ import annotations

import importlib.util
import os
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path


def dependency_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def collect_startup_diagnostics(base_dir: str | Path | None = None, error_text: str | None = None) -> str:
    base = Path(base_dir or Path(__file__).resolve().parent)
    lines = [
        "# 邮件监控启动诊断",
        f"time={datetime.now().isoformat(timespec='seconds')}",
        f"base_dir={base}",
        f"cwd={Path.cwd()}",
        f"python_executable={sys.executable}",
        f"python_version={sys.version.replace(os.linesep, ' ')}",
        f"platform={platform.platform()}",
        f"PySide6={dependency_available('PySide6')}",
        f"requests={dependency_available('requests')}",
        f"dotenv={dependency_available('dotenv')}",
        f"tkinter={dependency_available('tkinter')}",
        f"env_exists={(base / '.env').exists()}",
        f"requirements_exists={(base / 'requirements.txt').exists()}",
    ]
    if error_text:
        lines.extend(["", "# error", error_text])
    return "\n".join(lines) + "\n"


def write_startup_diagnostics(path: str | Path, base_dir: str | Path | None = None, error_text: str | None = None) -> Path:
    output = Path(path)
    output.write_text(collect_startup_diagnostics(base_dir, error_text), encoding="utf-8")
    return output


def traceback_text() -> str:
    return traceback.format_exc()


def humanize_error(detail: str) -> str:
    text = detail.lower()
    if "connectionrefusederror" in text or "failed to establish a new connection" in text:
        if "11434" in text or "ollama" in text:
            return "无法连接本地 Ollama。请确认 Ollama 已启动，并且地址是 http://localhost:11434。"
        return "无法建立网络连接。请检查公司网络、服务器地址和端口。"
    if "ollama" in text and ("timeout" in text or "timed out" in text):
        return "本地 Ollama 响应超时。请确认模型已安装、Ollama 正在运行，或适当调大超时时间。"
    if "authenticationfailed" in text or "login failed" in text or "invalid credentials" in text:
        return "IMAP 登录失败。请检查邮箱账号、密码或授权码。"
    if "imap" in text and ("timeout" in text or "timed out" in text):
        return "连接公司邮箱 IMAP 超时。请检查 IMAP 服务器地址、端口和公司网络。"
    if "imap" in text and ("name or service not known" in text or "getaddrinfo" in text or "nodename" in text):
        return "找不到 IMAP 服务器。请检查公司邮箱 IMAP 地址是否填写正确。"
    if "ollama_base_url" in text or "只允许 localhost" in detail:
        return "为保证保密，Ollama 地址默认只能使用 localhost / 127.0.0.1。如确需远程地址，请手动勾选允许远程 Ollama。"
    if "结束日期不能早于开始日期" in detail:
        return "结束日期不能早于开始日期。请重新选择日期范围。"
    if "缺少 pyside6" in detail.lower():
        return "缺少 PySide6，现代界面无法启动。请在项目目录运行：pip install PySide6。"
    return detail.splitlines()[0] if detail.strip() else "发生未知错误，请查看日志详情。"
