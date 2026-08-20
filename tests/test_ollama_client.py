from ollama_client import OllamaClient


def test_coerce_plain_json():
    assert OllamaClient._coerce_json('{"category":"报价","importance":"high"}')["category"] == "报价"


def test_coerce_fenced_json():
    text = '```json\n{"category":"会议","summary":"x"}\n```'
    assert OllamaClient._coerce_json(text)["category"] == "会议"


def test_coerce_embedded_json():
    text = '好的，结果是：{"category":"通知","importance":"normal"} 完毕'
    assert OllamaClient._coerce_json(text)["importance"] == "normal"
