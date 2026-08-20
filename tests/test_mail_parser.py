from mail_parser import normalize_subject, parse_email_bytes


def _build_raw(subject: str, sender: str, body: str, ctype: str = "text/plain") -> bytes:
    return (
        f"From: {sender}\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: <abc123@example.com>\r\n"
        f"Date: Wed, 20 Aug 2025 10:00:00 +0900\r\n"
        f"Content-Type: {ctype}; charset=utf-8\r\n"
        f"\r\n"
        f"{body}\r\n"
    ).encode()


def test_normalize_subject_strips_reply_prefix():
    assert normalize_subject("Re: 报价单") == "报价单"
    assert normalize_subject("回复：会议安排") == "会议安排"
    assert normalize_subject("FW:  Multiple   Spaces") == "multiple spaces"


def test_parse_plain_email():
    raw = _build_raw("询价-东京项目", "Alice <alice@corp.com>", "请提供本周报价。")
    mail = parse_email_bytes(raw, uid=42, preview_len=100)
    assert mail.uid == 42
    assert mail.sender_address == "alice@corp.com"
    assert mail.subject == "询价-东京项目"
    assert mail.message_id == "abc123@example.com"
    assert "报价" in mail.body_text
    assert mail.received_epoch > 0


def test_parse_html_email_strips_tags():
    raw = _build_raw("通知", "sys@corp.com", "<p>今晚<b>维护</b></p>", ctype="text/html")
    mail = parse_email_bytes(raw, uid=1)
    assert "<" not in mail.body_text
    assert "维护" in mail.body_text


def test_parse_missing_date_falls_back():
    raw = b"From: a@b.com\r\nSubject: x\r\n\r\nbody\r\n"
    mail = parse_email_bytes(raw, uid=2)
    assert mail.received_epoch > 0
    assert mail.subject == "x"
