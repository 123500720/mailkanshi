import subprocess
import sys
from pathlib import Path
from tkinter import Tk, messagebox

from diagnostics import traceback_text, write_startup_diagnostics

BASE = Path(__file__).resolve().parent
LOG = BASE / "launcher_error.log"


def pick_python() -> list[str]:
    candidates = [
        BASE / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable) if sys.executable else None,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return [str(candidate)]
    return ["python"]


def show_error(text: str) -> None:
    try:
        root = Tk()
        root.withdraw()
        messagebox.showerror("邮件监控启动失败", text)
        root.destroy()
    except Exception:
        pass


def main() -> int:
    cmd = pick_python() + [str(BASE / "mail_monitor_gui.py")]
    try:
        proc = subprocess.Popen(cmd, cwd=str(BASE))
        return 0 if proc.pid else 1
    except Exception:
        detail = traceback_text()
        write_startup_diagnostics(LOG, BASE, detail)
        show_error(
            "启动失败。\n\n"
            f"尝试命令：{' '.join(cmd)}\n\n"
            f"错误详情已写入：{LOG}\n\n"
            "请把这个日志文件发给我。"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
