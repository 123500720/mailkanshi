from __future__ import annotations

import argparse
from datetime import date

from config import load_settings
from exporter import Exporter
from mail_monitor_gui import launch_gui
from service import MonitorService
from storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="公司邮件本地监控工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("gui", help="启动图形界面")
    sub.add_parser("watch", help="启动常驻监控")

    collect = sub.add_parser("collect", help="按日期范围批量收集")
    collect.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    collect.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")

    sub.add_parser("models", help="列出本地 Ollama 模型")

    export = sub.add_parser("export", help="导出本地结果")
    export.add_argument("--format", choices=["csv", "md", "jsonl"], required=True)
    export.add_argument("--output", required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings()
    storage = Storage(settings.resolve_path(settings.db_path))
    service = MonitorService(settings, storage=storage, log_callback=print)

    if args.command == "gui":
        launch_gui()
        return
    if args.command == "watch":
        service.watch()
        return
    if args.command == "collect":
        service.collect(date.fromisoformat(args.start), date.fromisoformat(args.end))
        return
    if args.command == "models":
        for model in service.list_models():
            print(model)
        return
    if args.command == "export":
        exporter = Exporter(settings, storage)
        if args.format == "csv":
            exporter.export_csv(args.output)
        elif args.format == "md":
            exporter.export_markdown(args.output)
        else:
            exporter.export_jsonl(args.output)
        print(f"已导出到：{args.output}")


if __name__ == "__main__":
    main()

