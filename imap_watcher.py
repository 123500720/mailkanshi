from __future__ import annotations

import imaplib
import time
from contextlib import suppress
from datetime import date, timedelta
from typing import Callable, Iterator

from config import Settings


class ImapWatcher:
    def __init__(self, settings: Settings, logger: Callable[[str], None] | None = None) -> None:
        self.settings = settings
        self.logger = logger or (lambda _msg: None)
        self.client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        self._selected_uidvalidity = "0"
        self._idle_supported = False

    def connect(self) -> None:
        timeout = self.settings.imap_timeout
        if self.settings.imap_ssl:
            self.client = imaplib.IMAP4_SSL(self.settings.imap_server, self.settings.imap_port, timeout=timeout)
        else:
            self.client = imaplib.IMAP4(self.settings.imap_server, self.settings.imap_port, timeout=timeout)
        self.client.login(self.settings.imap_username, self.settings.imap_password)
        status, data = self.client.select(self.settings.imap_folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"无法选择邮箱文件夹：{self.settings.imap_folder}")
        self._selected_uidvalidity = self._read_uidvalidity()
        with suppress(Exception):
            status, capability = self.client.capability()
            joined = b" ".join(capability if isinstance(capability, list) else [capability]).decode(errors="ignore")
            self._idle_supported = "IDLE" in joined.upper()

    def _read_uidvalidity(self) -> str:
        if self.client is None:
            return "0"
        with suppress(Exception):
            status, data = self.client.status(self.settings.imap_folder, "(UIDVALIDITY)")
            if status == "OK" and data:
                text = b" ".join(item for item in data if isinstance(item, bytes)).decode(errors="ignore")
                tokens = text.replace("(", " ").replace(")", " ").split()
                for idx, token in enumerate(tokens):
                    if token.upper() == "UIDVALIDITY" and idx + 1 < len(tokens):
                        return tokens[idx + 1]
        return "0"

    def close(self) -> None:
        if self.client is None:
            return
        with suppress(Exception):
            self.client.close()
        with suppress(Exception):
            self.client.logout()
        self.client = None

    def __enter__(self) -> "ImapWatcher":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def uidvalidity(self) -> str:
        return self._selected_uidvalidity

    def get_highest_uid(self) -> int:
        if self.client is None:
            raise RuntimeError("IMAP 未连接")
        status, data = self.client.uid("SEARCH", None, "ALL")
        if status != "OK" or not data or not data[0]:
            return 0
        items = data[0].decode().split()
        return int(items[-1]) if items else 0

    def fetch_message(self, uid: int) -> bytes:
        if self.client is None:
            raise RuntimeError("IMAP 未连接")
        status, data = self.client.uid("FETCH", str(uid), "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"拉取邮件失败 UID={uid}")
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                return item[1]
        raise RuntimeError(f"邮件内容为空 UID={uid}")

    def collect_uids(self, start_date: date, end_date: date) -> list[int]:
        if self.client is None:
            raise RuntimeError("IMAP 未连接")
        before_date = end_date + timedelta(days=1)
        criteria = f'(SINCE "{start_date.strftime("%d-%b-%Y")}" BEFORE "{before_date.strftime("%d-%b-%Y")}")'
        status, data = self.client.uid("SEARCH", None, criteria)
        if status != "OK" or not data or not data[0]:
            return []
        return [int(item) for item in data[0].decode().split() if item.isdigit()]

    def search_new_uids(self, last_seen_uid: int) -> list[int]:
        if self.client is None:
            raise RuntimeError("IMAP 未连接")
        status, data = self.client.uid("SEARCH", None, f"UID {last_seen_uid + 1}:*")
        if status != "OK" or not data or not data[0]:
            return []
        return [int(item) for item in data[0].decode().split() if item.isdigit() and int(item) > last_seen_uid]

    def iter_new_uids(self, start_after_uid: int, stop_event) -> Iterator[int]:
        last_seen = start_after_uid
        idle_notice_sent = False
        while not stop_event.is_set():
            try:
                if self._idle_supported and self.settings.prefer_idle and not idle_notice_sent:
                    self.logger("IMAP 服务器支持 IDLE；本版本用 UID 轻量轮询兜底，避免标准库私有协议在公司邮箱上不稳定。")
                    idle_notice_sent = True
                for uid in self.search_new_uids(last_seen):
                    last_seen = max(last_seen, uid)
                    yield uid
                slept = 0
                interval = max(5, self.settings.poll_interval)
                while slept < interval and not stop_event.is_set():
                    time.sleep(1)
                    slept += 1
            except imaplib.IMAP4.abort:
                self.logger("IMAP 连接中断，准备自动重连。")
                self.close()
                time.sleep(3)
                self.connect()
