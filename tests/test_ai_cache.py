from storage import Storage


def test_ai_cache_roundtrip(tmp_path):
    st = Storage(tmp_path / "c.db")
    assert st.get_ai_cache("hash1") is None
    st.put_ai_cache(
        "hash1",
        {
            "category": "报价",
            "summary": "客户询价",
            "importance": "high",
            "categories": "报价、会议",
            "action_items": '[{"task":"回复","type":"回复","due":""}]',
        },
    )
    cached = st.get_ai_cache("hash1")
    assert cached["category"] == "报价"
    assert cached["summary"] == "客户询价"
    assert cached["importance"] == "high"
    assert cached["categories"] == "报价、会议"


def test_ai_cache_empty_hash_ignored(tmp_path):
    st = Storage(tmp_path / "c.db")
    st.put_ai_cache("", {"category": "x"})
    assert st.get_ai_cache("") is None
