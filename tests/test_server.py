"""Tests for the Seshat FastAPI server.

OllamaClient is mocked throughout — no live Ollama required.
MemPalaceClient uses a real ephemeral ChromaDB instance via tmp_path.
"""
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from seshat.memory import MemPalaceClient
from seshat.server import create_app


# ------------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------------

@pytest.fixture()
def mock_llm():
    llm = MagicMock()
    llm.translate_query.return_value = "firewall block high severity"
    llm.grounded_response.return_value = (
        "## Summary\nTwo high-severity blocks detected.\n\n"
        "## Key Findings\n- C2 beacon blocked [Record 1]\n\n"
        "## Recommended Actions\n1. Isolate workstation-042 [Record 1]\n\n"
        "## Data Gaps\n- No EDR data available"
    )
    return llm


@pytest.fixture()
def palace(tmp_path):
    p = MemPalaceClient(path=str(tmp_path / "palace"))
    # Pre-populate with one alert so searches return something
    p.store(
        "Firewall", "high", "alerts", "test-id-1",
        "severity=high | source=fw01 | action=blocked | C2 beacon outbound",
        {"severity": "high", "source_name": "fw01", "seshat_id": "test-id-1",
         "source_type": "csv", "category": "malware", "action": "blocked"},
    )
    return p


@pytest.fixture()
def client(palace, mock_llm):
    app = create_app(palace=palace, llm=mock_llm)
    return TestClient(app)


# ------------------------------------------------------------------
# Health / meta
# ------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_models(client):
    r = client.get("/v1/models")
    assert r.status_code == 200
    models = r.json()["data"]
    assert len(models) == 1
    assert models[0]["id"] == "seshat"


def test_api_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    assert "collections" in r.json()


# ------------------------------------------------------------------
# /v1/chat/completions — non-streaming
# ------------------------------------------------------------------

def test_chat_completions_returns_answer(client, mock_llm):
    r = client.post("/v1/chat/completions", json={
        "model": "seshat",
        "messages": [{"role": "user", "content": "Show me high severity firewall blocks"}],
        "stream": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert "Summary" in body["choices"][0]["message"]["content"]
    mock_llm.translate_query.assert_called_once()
    mock_llm.grounded_response.assert_called_once()


def test_chat_completions_uses_last_user_message(client, mock_llm):
    r = client.post("/v1/chat/completions", json={
        "messages": [
            {"role": "system", "content": "You are a SOC assistant"},
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ],
        "stream": False,
    })
    assert r.status_code == 200
    call_args = mock_llm.translate_query.call_args[0][0]
    assert call_args == "Second question"


def test_chat_completions_no_user_message_returns_400(client):
    r = client.post("/v1/chat/completions", json={
        "messages": [{"role": "system", "content": "system only"}],
        "stream": False,
    })
    assert r.status_code == 400


# ------------------------------------------------------------------
# /v1/chat/completions — streaming
# ------------------------------------------------------------------

def test_chat_completions_streaming(client):
    r = client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "Any critical alerts?"}],
        "stream": True,
    })
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    chunks = [line for line in r.text.splitlines() if line.startswith("data: ")]
    assert chunks[-1] == "data: [DONE]"

    # All non-DONE chunks must be valid JSON with the right shape
    for chunk in chunks[:-1]:
        payload = json.loads(chunk[len("data: "):])
        assert payload["object"] == "chat.completion.chunk"
        assert "choices" in payload


# ------------------------------------------------------------------
# /api/question
# ------------------------------------------------------------------

def test_api_question(client, mock_llm):
    r = client.post("/api/question", json={"question": "Are there C2 beacons?"})
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body
    assert "search_query" in body
    assert isinstance(body["records_retrieved"], int)


def test_api_question_missing_field(client):
    r = client.post("/api/question", json={})
    assert r.status_code == 400


def test_api_question_with_wing(client, mock_llm):
    r = client.post("/api/question", json={
        "question": "Any blocked firewall traffic?",
        "wing": "Firewall",
    })
    assert r.status_code == 200
    mock_llm.translate_query.assert_called_once()


# ------------------------------------------------------------------
# /api/ingest
# ------------------------------------------------------------------

def test_api_ingest_missing_config(client):
    r = client.post("/api/ingest", json={})
    assert r.status_code == 400


def test_api_ingest_nonexistent_file(client):
    r = client.post("/api/ingest", json={"config": "/no/such/file.yaml"})
    assert r.status_code == 404


def test_api_ingest_real_fixture(palace, mock_llm, tmp_path):
    """Ingest via the API using entirely in-memory generated data."""
    import textwrap
    import yaml

    csv_content = textwrap.dedent("""\
        timestamp,severity,category,action,src_ip,dst_ip,src_port,dst_port,protocol,direction
        2024-01-15T08:23:11Z,high,malware,blocked,192.168.1.1,1.2.3.4,1234,443,TCP,outbound
        2024-01-15T09:00:00Z,critical,exploitation,blocked,10.0.0.1,10.0.0.2,5555,80,TCP,inbound
    """)
    csv_file = tmp_path / "alerts.csv"
    csv_file.write_text(csv_content)

    config = {
        "source_type": "csv",
        "source_name": "test_fw",
        "file_path": str(csv_file),
        "field_mapping": {
            "timestamp": "timestamp", "severity": "severity",
            "category": "category", "action": "action",
            "src_ip": "src_ip", "dst_ip": "dst_ip",
            "src_port": "src_port", "dst_port": "dst_port",
            "protocol": "protocol", "direction": "direction",
        },
        "mempalace": {"wing": "Firewall", "room_field": "severity"},
    }
    config_file = tmp_path / "fw.yaml"
    config_file.write_text(yaml.dump(config))

    app = create_app(palace=palace, llm=mock_llm)
    c = TestClient(app)

    before = palace.count("Firewall", "high", "alerts")
    r = c.post("/api/ingest", json={"config": str(config_file)})
    assert r.status_code == 200
    assert r.json()["wing"] == "Firewall"
    assert r.json()["ingested"] == 2
    assert palace.count("Firewall", "high", "alerts") > before
