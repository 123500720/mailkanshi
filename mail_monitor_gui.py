from __future__ import annotations

from pathlib import Path
from tkinter import Tk, messagebox

from diagnostics import humanize_error, traceback_text, write_startup_diagnostics

BASE = Path(__file__).resolve().parent


def _tk_root() -> Tk | None:
    try:
        root = Tk()
        root.withdraw()
        return root
    except Exception:
        return None


def _fallback_to_tk(reason: str) -> None:
    write_startup_diagnostics(BASE / "startup_error.log", BASE, reason)
    root = _tk_root()
    use_fallback = True
    if root:
        use_fallback = messagebox.askyesno(
            "PySide6 现代界面不可用",
            humanize_error(reason)
            + "\n\n如果还没安装，请在项目目录运行：\n"
            + "pip install PySide6\n\n"
            + "是否先打开旧版 Tkinter 备用界面？",
        )
        root.destroy()
    if use_fallback:
        from gui import launch_gui as launch_tk_gui

        launch_tk_gui()


def _show_startup_error(log_path: Path, detail: str) -> None:
    root = _tk_root()
    if root:
        messagebox.showerror(
            "邮件监控启动失败",
            humanize_error(detail)
            + "\n\n"
            + f"详细诊断已写入：{log_path}\n\n"
            + "把这个日志内容发给我，我就能继续修。",
        )
        root.destroy()


def launch_gui() -> None:
    try:
        from qt_gui import launch_modern_gui

        launch_modern_gui()
    except RuntimeError as exc:
        if "PySide6" in str(exc):
            _fallback_to_tk(str(exc))
            return
        raise


if __name__ == "__main__":
    try:
        launch_gui()
    except Exception:
        detail = traceback_text()
        log_path = write_startup_diagnostics(BASE / "startup_error.log", BASE, detail)
        _show_startup_error(log_path, detail)
        raise
