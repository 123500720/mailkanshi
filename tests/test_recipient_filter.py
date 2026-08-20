from config import Settings
from mail_parser import ParsedMail
from service import recipient_allowed


def _mail(to=None, cc=None) -> ParsedMail:
    return ParsedMail(
        uid=1,
        message_id="m1",
        sender="Alice <alice@corp.com>",
        sender_address="alice@corp.com",
        subject="件名",
        subject_key="件名",
        received_at="",
        received_epoch=1,
        body_text="本文",
        body_preview="本文",
        to_addresses=to or [],
        cc_addresses=cc or [],
    )


def _settings(tmp_path, **kw) -> Settings:
    return Settings(workspace=tmp_path, imap_username="me@corp.com", **kw)


def test_filter_off_allows_all(tmp_path):
    s = _settings(tmp_path, recipient_filter="off")
    assert recipient_allowed(_mail(to=["x@corp.com"]), s)


def test_filter_to_or_cc_me(tmp_path):
    s = _settings(tmp_path, recipient_filter="to_or_cc_me")
    assert recipient_allowed(_mail(to=["me@corp.com"]), s)
    assert recipient_allowed(_mail(cc=["me@corp.com"]), s)
    assert not recipient_allowed(_mail(to=["other@corp.com"]), s)


def test_filter_watched_addresses(tmp_path):
    s = _settings(tmp_path, recipient_filter="watched",
                  watched_addresses=["team@corp.com"])
    assert recipient_allowed(_mail(cc=["team@corp.com"]), s)
    assert not recipient_allowed(_mail(to=["me@corp.com"]), s)


def test_filter_watched_empty_allows_all(tmp_path):
    s = _settings(tmp_path, recipient_filter="watched", watched_addresses=[])
    assert recipient_allowed(_mail(to=["anyone@corp.com"]), s)
