import json

from config import Settings
from exporter import Exporter
from storage import Storage


def _record(uid=1, **kw):
    base = {
        "mailbox_key": "k", "uidvalidity": "1", "uid": uid, "message_id": f"m{uid}",
        "received_at": "2025-08-20T01:00:00+00:00", "received_epoch": 1000 + uid,
        "sender": "a@b.com", "sender_address": "a@b.com", "subject": f"主题|{uid}",
        "subject_key": f"主题{uid}", "category": "报价", "importance": "high",
        "rule_hit": "", "summary": "摘要", "body_preview": "预览", "status": "done",
        "error": "", "processed_at": "2025-08-20T02:00:00Z",
    }
    base.update(kw)
    return base


def test_append_writes_header_once_and_rows(tmp_path):
    s = Settings(workspace=tmp_path)
    st = Storage(tmp_path / "t.db")
    ex = Exporter(s, st)
    ex.append_default_outputs(_record(1))
    ex.append_default_outputs(_record(2))

    md = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert md.count("# 邮件分析结果") == 1
    assert md.count("|报价|") == 2
    assert "主题 1" in md  # pipe escaped to space

    jl = (tmp_path / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(jl) == 2
    assert json.loads(jl[0])["uid"] == 1


def test_storage_dedup_helpers(tmp_path):
    st = Storage(tmp_path / "t.db")
    rec = _record(1)
    st.save_mail(rec)
    assert st.has_uid("k", "1", 1)
    assert st.find_by_message_id("k", "m1") is not None
    # subject window dedup within 3 seconds
    assert st.find_recent_subject("k", "主题1", 1001, window_seconds=3) is not None
    assert st.find_recent_subject("k", "主题1", 9999, window_seconds=3) is None


def test_enqueue_job_dedups(tmp_path):
    st = Storage(tmp_path / "t.db")
    assert st.enqueue_job("k", "1", 5) is True
    assert st.enqueue_job("k", "1", 5) is False
