from mail_parser import ParsedMail
from rules import RuleEngine


def _mail(sender="user@corp.com", subject="hello", body="body"):
    return ParsedMail(
        uid=1, message_id="m", sender=sender, sender_address=sender,
        subject=subject, subject_key=subject.lower(), received_at="", received_epoch=1,
        body_text=body, body_preview=body,
    )


def test_whitelist_forces_high():
    engine = RuleEngine(whitelist=["boss@corp.com"], keywords=[])
    dec = engine.evaluate(_mail(sender="boss@corp.com"))
    assert dec.forced_importance == "high"
    assert dec.matched_rule.startswith("whitelist:")


def test_keyword_forces_high():
    engine = RuleEngine(whitelist=[], keywords=["紧急"])
    dec = engine.evaluate(_mail(subject="【紧急】请处理"))
    assert dec.forced_importance == "high"
    assert "keyword" in dec.matched_rule


def test_no_match_returns_empty():
    engine = RuleEngine(whitelist=["x@y.com"], keywords=["urgent"])
    dec = engine.evaluate(_mail())
    assert dec.forced_importance is None
    assert dec.matched_rule == ""


def test_keyword_case_insensitive():
    engine = RuleEngine(whitelist=[], keywords=["urgent"])
    dec = engine.evaluate(_mail(body="This is URGENT"))
    assert dec.forced_importance == "high"
