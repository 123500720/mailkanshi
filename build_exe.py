"""打包脚本：把 mailkanshi 打成单文件 Windows exe（面向不懂命令行的用户）。

用法：
    pip install .[build]
    python build_exe.py

生成物在 dist\\mailkanshi.exe，双击即可启动图形界面。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENTRY = BASE / "mail_monitor_gui.py"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，请先运行：pip install .[build]")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--name",
        "mailkanshi",
        str(ENTRY),
    ]
    print("执行：", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(BASE))


if __name__ == "__main__":
    raise SystemExit(main())
