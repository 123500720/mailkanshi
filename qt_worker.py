"""后台服务线程（从 qt_gui.py 拆分）：把 MonitorService 的运行放到 QThread，
通过 Qt 信号回传日志/结果/进度/状态，保持 UI 不卡顿。"""

from __future__ import annotations

import threading
import traceback
from datetime import date

from PySide6.QtCore import QThread, Signal

from config import Settings
from service import MonitorService
from storage import Storage


class ServiceThread(QThread):
    log_signal = Signal(str)
    result_signal = Signal(dict)
    progress_signal = Signal(int, int)
    status_signal = Signal(str)
    error_signal = Signal(str)
    models_signal = Signal(list)

    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        mode: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
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
