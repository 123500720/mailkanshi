from __future__ import annotations

import csv
import json
from pathlib import Path

from config import Settings
from storage import Storage

EXPORT_FIELDS = [
    "processed_at",
    "received_at",
    "sender",
    "subject",
    "category",
    "importance",
    "rule_hit",
    "summary",
    "body_preview",
    "uid",
    "status",
]


MD_HEADER = ["# 邮件分析结果", "", "|处理时间|收件时间|紧急度|分类|发件人|主题|摘要|", "|---|---|---|---|---|---|---|"]


def _md_row(row: dict) -> str:
    return "|{processed_at}|{received_at}|{importance}|{category}|{sender}|{subject}|{summary}|".format(
        processed_at=row.get("processed_at", ""),
        received_at=row.get("received_at", ""),
        importance=row.get("importance", ""),
        category=row.get("category", ""),
        sender=str(row.get("sender", "")).replace("|", " "),
        subject=str(row.get("subject", "")).replace("|", " "),
        summary=str(row.get("summary", "")).replace("|", " "),
    )


class Exporter:
    def __init__(self, settings: Settings, storage: Storage) -> None:
        self.settings = settings
        self.storage = storage

    def _rows(self) -> list[dict]:
        return self.storage.list_all_mails()

    def sync_default_outputs(self) -> None:
        self.export_jsonl(self.settings.resolve_path(self.settings.results_jsonl))
        self.export_markdown(self.settings.resolve_path(self.settings.output_md))

    def append_default_outputs(self, record: dict) -> None:
        """增量追加单条记录，避免每封邮件全量重写（O(n^2)）。"""
        payload = {field: record.get(field, "") for field in EXPORT_FIELDS}

        jsonl_path = self.settings.resolve_path(self.settings.results_jsonl)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

        md_path = self.settings.resolve_path(self.settings.output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        if not md_path.exists() or md_path.stat().st_size == 0:
            md_path.write_text("\n".join(MD_HEADER) + "\n", encoding="utf-8")
        with md_path.open("a", encoding="utf-8") as handle:
            handle.write(_md_row(payload) + "\n")

    def export_csv(self, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS)
            writer.writeheader()
            for row in self._rows():
                writer.writerow({field: row.get(field, "") for field in EXPORT_FIELDS})
        return output

    def export_jsonl(self, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for row in self._rows():
                handle.write(json.dumps({field: row.get(field, "") for field in EXPORT_FIELDS}, ensure_ascii=False) + "\n")
        return output

    def export_markdown(self, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        lines = list(MD_HEADER)
        for row in self._rows():
            lines.append(_md_row(row))
        output.write_text("\n".join(lines), encoding="utf-8")
        return output
