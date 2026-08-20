from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


def utcnow_text() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class Storage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS monitor_state (
                    mailbox_key TEXT PRIMARY KEY,
                    uidvalidity TEXT NOT NULL,
                    baseline_uid INTEGER NOT NULL DEFAULT 0,
                    last_seen_uid INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mail_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mailbox_key TEXT NOT NULL,
                    uidvalidity TEXT NOT NULL,
                    uid INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(mailbox_key, uidvalidity, uid)
                );

                CREATE INDEX IF NOT EXISTS idx_mail_jobs_status
                ON mail_jobs(mailbox_key, status, id);

                CREATE TABLE IF NOT EXISTS mails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mailbox_key TEXT NOT NULL,
                    uidvalidity TEXT NOT NULL,
                    uid INTEGER NOT NULL,
                    message_id TEXT NOT NULL DEFAULT '',
                    received_at TEXT NOT NULL DEFAULT '',
                    received_epoch INTEGER NOT NULL DEFAULT 0,
                    sender TEXT NOT NULL DEFAULT '',
                    sender_address TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '',
                    subject_key TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '其他',
                    importance TEXT NOT NULL DEFAULT 'normal',
                    rule_hit TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    body_preview TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'done',
                    error TEXT NOT NULL DEFAULT '',
                    processed_at TEXT NOT NULL,
                    UNIQUE(mailbox_key, uidvalidity, uid)
                );

                CREATE INDEX IF NOT EXISTS idx_mails_message_id
                ON mails(mailbox_key, message_id);

                CREATE INDEX IF NOT EXISTS idx_mails_subject_window
                ON mails(mailbox_key, subject_key, received_epoch);

                CREATE TABLE IF NOT EXISTS run_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def append_log(self, level: str, message: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO run_logs(level, message, created_at) VALUES (?, ?, ?)",
                (level.upper(), message, utcnow_text()),
            )

    def get_state(self, mailbox_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM monitor_state WHERE mailbox_key = ?",
            (mailbox_key,),
        ).fetchone()
        return dict(row) if row else None

    def set_baseline(self, mailbox_key: str, uidvalidity: str, baseline_uid: int) -> None:
        now = utcnow_text()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO monitor_state(mailbox_key, uidvalidity, baseline_uid, last_seen_uid, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(mailbox_key) DO UPDATE SET
                    uidvalidity=excluded.uidvalidity,
                    baseline_uid=excluded.baseline_uid,
                    last_seen_uid=excluded.last_seen_uid,
                    updated_at=excluded.updated_at
                """,
                (mailbox_key, uidvalidity, baseline_uid, baseline_uid, now),
            )

    def update_last_seen_uid(self, mailbox_key: str, uidvalidity: str, uid: int) -> None:
        current = self.get_state(mailbox_key)
        baseline_uid = current["baseline_uid"] if current else uid
        last_seen_uid = max(uid, int(current["last_seen_uid"])) if current else uid
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO monitor_state(mailbox_key, uidvalidity, baseline_uid, last_seen_uid, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(mailbox_key) DO UPDATE SET
                    uidvalidity=excluded.uidvalidity,
                    baseline_uid=excluded.baseline_uid,
                    last_seen_uid=excluded.last_seen_uid,
                    updated_at=excluded.updated_at
                """,
                (mailbox_key, uidvalidity, baseline_uid, last_seen_uid, utcnow_text()),
            )

    def has_uid(self, mailbox_key: str, uidvalidity: str, uid: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM mails WHERE mailbox_key=? AND uidvalidity=? AND uid=?",
            (mailbox_key, uidvalidity, uid),
        ).fetchone()
        return row is not None

    def find_by_message_id(self, mailbox_key: str, message_id: str) -> dict[str, Any] | None:
        if not message_id:
            return None
        row = self._conn.execute(
            "SELECT * FROM mails WHERE mailbox_key=? AND message_id=? ORDER BY id DESC LIMIT 1",
            (mailbox_key, message_id),
        ).fetchone()
        return dict(row) if row else None

    def find_recent_subject(self, mailbox_key: str, subject_key: str, received_epoch: int, window_seconds: int = 3) -> dict[str, Any] | None:
        if not subject_key or received_epoch <= 0:
            return None
        row = self._conn.execute(
            """
            SELECT * FROM mails
            WHERE mailbox_key=?
              AND subject_key=?
              AND ABS(received_epoch - ?) <= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (mailbox_key, subject_key, received_epoch, window_seconds),
        ).fetchone()
        return dict(row) if row else None

    def enqueue_job(self, mailbox_key: str, uidvalidity: str, uid: int) -> bool:
        now = utcnow_text()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO mail_jobs(mailbox_key, uidvalidity, uid, status, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (mailbox_key, uidvalidity, uid, now, now),
            )
            return cursor.rowcount > 0

    def claim_next_job(self, mailbox_key: str) -> dict[str, Any] | None:
        with self._lock, self._conn:
            row = self._conn.execute(
                """
                SELECT * FROM mail_jobs
                WHERE mailbox_key=? AND status IN ('pending', 'retrying')
                ORDER BY id ASC
                LIMIT 1
                """,
                (mailbox_key,),
            ).fetchone()
            if not row:
                return None
            self._conn.execute(
                """
                UPDATE mail_jobs
                SET status='processing', attempts=attempts+1, updated_at=?
                WHERE id=?
                """,
                (utcnow_text(), row["id"]),
            )
            updated = self._conn.execute("SELECT * FROM mail_jobs WHERE id=?", (row["id"],)).fetchone()
            return dict(updated) if updated else None

    def finish_job(self, job_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE mail_jobs SET status='done', updated_at=? WHERE id=?",
                (utcnow_text(), job_id),
            )

    def retry_job(self, job_id: int, error: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE mail_jobs SET status='retrying', last_error=?, updated_at=? WHERE id=?",
                (error[:500], utcnow_text(), job_id),
            )

    def fail_job(self, job_id: int, error: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE mail_jobs SET status='failed', last_error=?, updated_at=? WHERE id=?",
                (error[:500], utcnow_text(), job_id),
            )

    def save_mail(self, record: dict[str, Any]) -> None:
        payload = {
            "mailbox_key": record.get("mailbox_key", ""),
            "uidvalidity": record.get("uidvalidity", ""),
            "uid": int(record.get("uid", 0)),
            "message_id": record.get("message_id", ""),
            "received_at": record.get("received_at", ""),
            "received_epoch": int(record.get("received_epoch", 0)),
            "sender": record.get("sender", ""),
            "sender_address": record.get("sender_address", ""),
            "subject": record.get("subject", ""),
            "subject_key": record.get("subject_key", ""),
            "category": record.get("category", "其他"),
            "importance": record.get("importance", "normal"),
            "rule_hit": record.get("rule_hit", ""),
            "summary": record.get("summary", ""),
            "body_preview": record.get("body_preview", ""),
            "status": record.get("status", "done"),
            "error": record.get("error", ""),
            "processed_at": record.get("processed_at", utcnow_text()),
        }
        columns = ",".join(payload.keys())
        placeholders = ",".join(["?"] * len(payload))
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO mails({columns}) VALUES ({placeholders})",
                tuple(payload.values()),
            )

    def list_mails(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM mails ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_all_mails(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM mails ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]
