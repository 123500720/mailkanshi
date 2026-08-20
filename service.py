from __future__ import annotations

import hashlib
import json
import traceback
from base64 import b64encode
from collections.abc import Callable
from contextlib import suppress
from datetime import date
from threading import Event
from urllib.parse import quote

from config import Settings
from exporter import Exporter
from imap_watcher import ImapWatcher
from mail_parser import ParsedMail, parse_email_bytes
from ollama_client import AiDecision, OllamaClient
from rules import RuleEngine
from storage import Storage, utcnow_text

LogCallback = Callable[[str], None]
ResultCallback = Callable[[dict], None]
ProgressCallback = Callable[[int, int], None]


def _attachments_text(parsed: ParsedMail) -> str:
    if not parsed.attachments:
        return ""
    parts = []
    for att in parsed.attachments:
        name = att.get("filename", "")
        size = att.get("size", 0)
        if size:
            parts.append(f"{name}({size}B)")
        else:
            parts.append(name)
    return "; ".join(p for p in parts if p)


class MonitorService:
    def __init__(
        self,
        settings: Settings,
        storage: Storage | None = None,
        log_callback: LogCallback | None = None,
        result_callback: ResultCallback | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage or Storage(self.settings.resolve_path(self.settings.db_path))
        self.exporter = Exporter(self.settings, self.storage)
        self.rule_engine = RuleEngine(self.settings.rule_whitelist, self.settings.rule_keywords)
        self.ollama = OllamaClient(self.settings)
        self.log_callback = log_callback
        self.result_callback = result_callback
        self.progress_callback = progress_callback

    def log(self, message: str, level: str = "INFO") -> None:
        safe_message = self._redact(message)
        self.storage.append_log(level, safe_message)
        if self.log_callback:
            self.log_callback(safe_message)

    def _redact(self, message: str) -> str:
        safe = message
        secrets = [self.settings.imap_password]
        for secret in secrets:
            if not secret:
                continue
            safe = safe.replace(secret, "***")
            with suppress(Exception):
                safe = safe.replace(quote(secret), "***")
            with suppress(Exception):
                safe = safe.replace(b64encode(secret.encode()).decode(), "***")
        return safe

    def notify_result(self, row: dict) -> None:
        if self.result_callback:
            self.result_callback(row)

    def _maybe_desktop_notify(self, record: dict) -> None:
        if record.get("importance") != "high":
            return
        if not getattr(self.settings, "desktop_notify", True):
            return
        title = "高优先邮件"
        summary = record.get("summary") or record.get("subject") or ""
        sender = record.get("sender", "")
        message = f"{sender}: {summary}"[:200]
        with suppress(Exception):
            self._send_desktop_notification(title, message)

    def _send_desktop_notification(self, title: str, message: str) -> None:
        try:
            from plyer import notification  # type: ignore

            notification.notify(title=title, message=message, timeout=10)
            return
        except Exception:
            pass
        import sys

        if sys.platform.startswith("win"):
            with suppress(Exception):
                import ctypes

                ctypes.windll.user32.MessageBeep(0)

    def notify_progress(self, current: int, total: int) -> None:
        if self.progress_callback:
            self.progress_callback(current, total)

    def list_models(self) -> list[str]:
        return self.ollama.list_models()

    def watch(self, stop_event: Event | None = None) -> None:
        stop_event = stop_event or Event()
        self.log("启动常驻监控。")
        with ImapWatcher(self.settings, logger=lambda text: self.log(text)) as watcher:
            state = self.storage.get_state(self.settings.mailbox_key)
            if not state or state["uidvalidity"] != watcher.uidvalidity:
                baseline_uid = watcher.get_highest_uid()
                self.storage.set_baseline(self.settings.mailbox_key, watcher.uidvalidity, baseline_uid)
                self.log(f"已建立基线，只监控之后的新邮件。当前最大 UID={baseline_uid}")
            else:
                self.log(f"继续使用已有水位 UID={state['last_seen_uid']}")
            current_state = self.storage.get_state(self.settings.mailbox_key)
            start_after = int(current_state["last_seen_uid"]) if current_state else 0
            while not stop_event.is_set():
                saw_uid = False
                for uid in watcher.iter_new_uids(start_after, stop_event):
                    saw_uid = True
                    if stop_event.is_set():
                        break
                    self.storage.enqueue_job(self.settings.mailbox_key, watcher.uidvalidity, uid)
                    self._drain_jobs(watcher, stop_event)
                    start_after = max(start_after, uid)
                if not saw_uid and not stop_event.is_set():
                    self._drain_jobs(watcher, stop_event)
        self.log("常驻监控已停止。")

    def collect(self, start_date: date, end_date: date, stop_event: Event | None = None) -> int:
        stop_event = stop_event or Event()
        self.log(f"开始一键收集：{start_date.isoformat()} ~ {end_date.isoformat()}")
        done = 0
        with ImapWatcher(self.settings, logger=lambda text: self.log(text)) as watcher:
            uids = watcher.collect_uids(start_date, end_date)
            fresh_uids: list[int] = []
            for uid in uids:
                if not self.storage.has_uid(self.settings.mailbox_key, watcher.uidvalidity, uid):
                    if self.storage.enqueue_job(self.settings.mailbox_key, watcher.uidvalidity, uid):
                        fresh_uids.append(uid)
            total = len(fresh_uids)
            self.notify_progress(0, max(total, 1))
            while not stop_event.is_set():
                job = self.storage.claim_next_job(self.settings.mailbox_key)
                if not job:
                    break
                self._run_job(watcher, job)
                done += 1
                self.notify_progress(done, max(total, 1))
        self.log(f"一键收集完成，共处理 {done} / {len(fresh_uids)} 封。")
        return done

    def _drain_jobs(self, watcher: ImapWatcher, stop_event: Event) -> None:
        while not stop_event.is_set():
            job = self.storage.claim_next_job(self.settings.mailbox_key)
            if not job:
                return
            self._run_job(watcher, job)

    def _run_job(self, watcher: ImapWatcher, job: dict) -> None:
        uid = int(job["uid"])
        uidvalidity = str(job["uidvalidity"])
        try:
            if self.storage.has_uid(self.settings.mailbox_key, uidvalidity, uid):
                self.storage.finish_job(job["id"])
                return
            raw_bytes = watcher.fetch_message(uid)
            parsed = parse_email_bytes(raw_bytes, uid, preview_len=self.settings.body_preview_len)
            duplicate_reason = self._detect_duplicate(parsed)
            if duplicate_reason:
                record = self._build_duplicate_record(parsed, uidvalidity, duplicate_reason)
                self.storage.save_mail(record)
                self.storage.update_last_seen_uid(self.settings.mailbox_key, uidvalidity, uid)
                self.storage.finish_job(job["id"])
                self.exporter.append_default_outputs(record)
                self.notify_result(record)
                self.log(f"邮件 UID={uid} 因 {duplicate_reason} 被去重。")
                return

            decision = self._analyze_mail(parsed)
            record = {
                "mailbox_key": self.settings.mailbox_key,
                "uidvalidity": uidvalidity,
                "uid": parsed.uid,
                "message_id": parsed.message_id,
                "received_at": parsed.received_at,
                "received_epoch": parsed.received_epoch,
                "sender": parsed.sender,
                "sender_address": parsed.sender_address,
                "subject": parsed.subject,
                "subject_key": parsed.subject_key,
                "category": decision["category"],
                "importance": decision["importance"],
                "rule_hit": decision["rule_hit"],
                "summary": decision["summary"],
                "body_preview": parsed.body_preview,
                "attachments": _attachments_text(parsed),
                "categories": decision.get("categories", ""),
                "action_items": decision.get("action_items", ""),
                "status": "done",
                "error": "",
                "processed_at": utcnow_text(),
            }
            self.storage.save_mail(record)
            self.storage.update_last_seen_uid(self.settings.mailbox_key, uidvalidity, uid)
            self.storage.finish_job(job["id"])
            self.exporter.append_default_outputs(record)
            self.notify_result(record)
            self._maybe_desktop_notify(record)
            self.log(f"邮件 UID={uid} 处理完成：{record['category']} / {record['importance']}")
        except Exception as exc:  # pragma: no cover - integration path
            message = f"{type(exc).__name__}: {exc}"
            if int(job["attempts"]) < self.settings.max_retry:
                self.storage.retry_job(job["id"], message)
                self.log(f"邮件 UID={uid} 处理失败，稍后重试：{message}", level="WARN")
            else:
                record = {
                    "mailbox_key": self.settings.mailbox_key,
                    "uidvalidity": uidvalidity,
                    "uid": uid,
                    "message_id": "",
                    "received_at": "",
                    "received_epoch": 0,
                    "sender": "",
                    "sender_address": "",
                    "subject": "",
                    "subject_key": "",
                    "category": "其他",
                    "importance": "normal",
                    "rule_hit": "",
                    "summary": "处理失败，请查看本地日志。",
                    "body_preview": "",
                    "status": "failed",
                    "error": message,
                    "processed_at": utcnow_text(),
                }
                self.storage.save_mail(record)
                self.storage.fail_job(job["id"], message)
                self.exporter.append_default_outputs(record)
                self.notify_result(record)
                self.log(f"邮件 UID={uid} 最终失败：{message}", level="ERROR")
                self.log(traceback.format_exc(limit=3), level="ERROR")

    def _detect_duplicate(self, parsed: ParsedMail) -> str:
        if parsed.message_id and self.storage.find_by_message_id(self.settings.mailbox_key, parsed.message_id):
            return "Message-ID 去重"
        if self.storage.find_recent_subject(self.settings.mailbox_key, parsed.subject_key, parsed.received_epoch):
            return "3秒主题窗口去重"
        return ""

    def _content_hash(self, parsed: ParsedMail) -> str:
        raw = f"{parsed.sender_address}\n{parsed.subject}\n{parsed.body_text}".encode()
        return hashlib.sha256(raw).hexdigest()

    def _analyze_mail(self, parsed: ParsedMail) -> dict[str, str]:
        rule = self.rule_engine.evaluate(parsed)
        content_hash = self._content_hash(parsed)
        cached = None
        if getattr(self.settings, "ai_cache_enabled", True):
            cached = self.storage.get_ai_cache(content_hash)
        if cached:
            self.log(f"命中 AI 缓存（内容哈希 {content_hash[:8]}），跳过 LLM 调用。")
            importance = rule.forced_importance or cached.get("importance", "normal")
            return {
                "category": cached.get("category", "其他"),
                "summary": cached.get("summary", ""),
                "importance": importance,
                "rule_hit": rule.matched_rule,
                "categories": cached.get("categories", ""),
                "action_items": cached.get("action_items", ""),
            }
        ai: AiDecision = self.ollama.analyze(parsed)
        importance = rule.forced_importance or ai.importance
        categories = ai.categories or ([ai.category] if ai.category else [])
        result = {
            "category": ai.category,
            "summary": ai.summary,
            "importance": importance,
            "rule_hit": rule.matched_rule,
            "categories": "、".join(categories),
            "action_items": json.dumps(ai.action_items, ensure_ascii=False) if ai.action_items else "",
        }
        if getattr(self.settings, "ai_cache_enabled", True):
            with suppress(Exception):
                self.storage.put_ai_cache(content_hash, {**result, "importance": ai.importance})
        return result

    def _build_duplicate_record(self, parsed: ParsedMail, uidvalidity: str, duplicate_reason: str) -> dict:
        return {
            "mailbox_key": self.settings.mailbox_key,
            "uidvalidity": uidvalidity,
            "uid": parsed.uid,
            "message_id": parsed.message_id,
            "received_at": parsed.received_at,
            "received_epoch": parsed.received_epoch,
            "sender": parsed.sender,
            "sender_address": parsed.sender_address,
            "subject": parsed.subject,
            "subject_key": parsed.subject_key,
            "category": "其他",
            "importance": "normal",
            "rule_hit": duplicate_reason,
            "summary": "重复邮件，已跳过。",
            "body_preview": parsed.body_preview,
            "attachments": _attachments_text(parsed),
            "categories": "",
            "action_items": "",
            "status": "duplicate",
            "error": "",
            "processed_at": utcnow_text(),
        }
