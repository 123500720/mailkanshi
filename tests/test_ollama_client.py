from ollama_client import OllamaClient


def test_coerce_plain_json():
    assert OllamaClient._coerce_json('{"category":"报价","importance":"high"}')["category"] == "报价"


def test_coerce_fenced_json():
    text = '```json\n{"category":"会议","summary":"x"}\n```'
    assert OllamaClient._coerce_json(text)["category"] == "会议"


def test_coerce_embedded_json():
    text = '好的，结果是：{"category":"通知","importance":"normal"} 完毕'
    assert OllamaClient._coerce_json(text)["importance"] == "normal"


def test_is_local_detects_localhost():
    assert OllamaClient._is_local("http://localhost:11434")
    assert OllamaClient._is_local("http://127.0.0.1:11434")
    assert not OllamaClient._is_local("http://ollama.corp.example.com:11434")


def test_local_client_disables_trust_env(tmp_path):
    from config import Settings

    client = OllamaClient(Settings(workspace=tmp_path, ollama_base_url="http://127.0.0.1:11434"))
    assert client.session.trust_env is False

