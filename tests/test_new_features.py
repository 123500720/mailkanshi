from config import Settings
from mail_parser import parse_email_bytes
from ollama_client import OllamaClient


def _build_with_attachment() -> bytes:
    return (
        "From: Alice <alice@corp.com>\r\n"
        "Subject: 报价单\r\n"
        "Message-ID: <att1@example.com>\r\n"
        "Date: Wed, 20 Aug 2025 10:00:00 +0900\r\n"
        'Content-Type: multipart/mixed; boundary="BOUND"\r\n'
        "\r\n"
        "--BOUND\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "请查收报价。\r\n"
        "--BOUND\r\n"
        "Content-Type: application/pdf; name=\"quote.pdf\"\r\n"
        "Content-Disposition: attachment; filename=\"quote.pdf\"\r\n"
        "Content-Transfer-Encoding: base64\r\n"
        "\r\n"
        "SGVsbG8gUERG\r\n"
        "--BOUND--\r\n"
    ).encode()


def test_parse_attachments():
    mail = parse_email_bytes(_build_with_attachment(), uid=1)
    assert mail.has_attachment is True
    assert len(mail.attachments) == 1
    assert mail.attachments[0]["filename"] == "quote.pdf"
    assert "quote.pdf" in mail.attachment_names
    assert "请查收报价" in mail.body_text


def test_no_attachment():
    raw = (
        b"From: a@b.com\r\nSubject: x\r\nMessage-ID: <n@e.com>\r\n"
        b"Date: Wed, 20 Aug 2025 10:00:00 +0900\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\nhi\r\n"
    )
    mail = parse_email_bytes(raw, uid=2)
    assert mail.has_attachment is False
    assert mail.attachment_names == ""


def _client() -> OllamaClient:
    import tempfile
    from pathlib import Path

    return OllamaClient(Settings(workspace=Path(tempfile.gettempdir())))


def test_coerce_categories_filters_and_dedups():
    client = _client()
    cats = client._coerce_categories(["报价", "会议", "不存在", "报价"], "报价")
    assert cats[0] == "报价"
    assert "会议" in cats
    assert "不存在" not in cats


def test_coerce_categories_inserts_primary():
    client = _client()
    cats = client._coerce_categories(None, "通知")
    assert cats == ["通知"]


def test_coerce_action_items():
    client = _client()
    items = client._coerce_action_items(
        [
            {"task": "回复报价", "type": "回复", "due": "本周五"},
            {"task": "", "type": "回复"},
            {"task": "未知类型任务", "type": "xxx", "due": ""},
        ]
    )
    assert len(items) == 2
    assert items[0]["type"] == "回复"
    assert items[1]["type"] == "其他"


def test_coerce_action_items_non_list():
    client = _client()
    assert client._coerce_action_items("nope") == []
