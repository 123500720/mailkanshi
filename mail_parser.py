from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return value.strip()


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n", text)
    text = re.sub(r"(?is)<.*?>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _extract_attachments(message) -> list[dict]:
    """收集附件元信息（文件名/类型/大小）；不解析内容以保持轻量与安全。"""
    attachments: list[dict] = []
    if not message.is_multipart():
        return attachments
    for part in message.walk():
        disposition = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()
        if "attachment" not in disposition and not filename:
            continue
        name = _decode_header(filename) if filename else ""
        if not name:
            continue
        try:
            payload = part.get_payload(decode=True) or b""
            size = len(payload)
        except Exception:
            size = 0
        attachments.append({
            "filename": name,
            "content_type": part.get_content_type(),
            "size": size,
        })
    return attachments


def _extract_body(message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            try:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(_html_to_text(text))
    else:
        payload = message.get_payload(decode=True) or b""
        charset = message.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if message.get_content_type() == "text/html":
            html_parts.append(_html_to_text(text))
        else:
            plain_parts.append(text)
    body = "\n\n".join(part.strip() for part in plain_parts if part.strip())
    if not body:
        body = "\n\n".join(part.strip() for part in html_parts if part.strip())
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _extract_addresses(message, header: str) -> list[str]:
    raw_values = message.get_all(header, [])
    if not raw_values:
        return []
    decoded = [_decode_header(v) for v in raw_values]
    result: list[str] = []
    for _name, addr in getaddresses(decoded):
        addr = (addr or "").strip().lower()
        if addr and addr not in result:
            result.append(addr)
    return result


def normalize_subject(subject: str) -> str:
    cleaned = subject.strip()
    cleaned = re.sub(
        r"^(?:(?:re|fw|fwd|答复|回复|转发|返信|転送)\s*[:：]\s*)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.lower()


@dataclass
class ParsedMail:
    uid: int
    message_id: str
    sender: str
    sender_address: str
    subject: str
    subject_key: str
    received_at: str
    received_epoch: int
    body_text: str
    body_preview: str
    to_addresses: list[str] = field(default_factory=list)
    cc_addresses: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)

    @property
    def attachment_names(self) -> str:
        return ", ".join(a.get("filename", "") for a in self.attachments if a.get("filename"))

    @property
    def has_attachment(self) -> bool:
        return bool(self.attachments)


def parse_email_bytes(raw_bytes: bytes, uid: int, preview_len: int = 200) -> ParsedMail:
    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    sender = _decode_header(message.get("From"))
    sender_address = parseaddr(sender)[1].lower()
    subject = _decode_header(message.get("Subject"))
    message_id = (message.get("Message-ID") or "").strip().strip("<>")
    body_text = _extract_body(message)
    body_preview = body_text[:preview_len].replace("\r", " ").replace("\n", " ").strip()
    to_addresses = _extract_addresses(message, "To")
    cc_addresses = _extract_addresses(message, "Cc")
    attachments = _extract_attachments(message)
    received_at = ""
    received_epoch = 0
    try:
        parsed_date = parsedate_to_datetime(message.get("Date"))
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        received_at = parsed_date.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        received_epoch = int(parsed_date.timestamp())
    except Exception:
        now = datetime.now(timezone.utc)
        received_at = now.replace(microsecond=0).isoformat()
        received_epoch = int(now.timestamp())
    return ParsedMail(
        uid=uid,
        message_id=message_id,
        sender=sender,
        sender_address=sender_address,
        subject=subject,
        subject_key=normalize_subject(subject),
        received_at=received_at,
        received_epoch=received_epoch,
        body_text=body_text,
        body_preview=body_preview,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        attachments=attachments,
    )
