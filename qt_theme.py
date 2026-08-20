"""界面样式与状态常量（从 qt_gui.py 拆分，便于维护）。"""

from __future__ import annotations

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
