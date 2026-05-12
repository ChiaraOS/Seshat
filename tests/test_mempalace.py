"""Tests for MemPalaceClient (uses a temporary on-disk ChromaDB instance)."""
import pytest

from seshat.memory.mempalace_client import MemPalaceClient


@pytest.fixture()
def palace(tmp_path):
    return MemPalaceClient(path=str(tmp_path / "test_palace"))


def test_count_empty(palace):
    assert palace.count("Firewall", "high", "alerts") == 0


def test_store_and_count(palace):
    palace.store("Firewall", "high", "alerts", "id-1", "malware C2 beacon", {"severity": "high"})
    assert palace.count("Firewall", "high", "alerts") == 1


def test_store_and_search(palace):
    palace.store("Firewall", "high", "alerts", "id-1", "malware C2 beacon outbound", {"severity": "high"})
    results = palace.search("Firewall", "high", "alerts", "C2 beacon malware")
    assert len(results) == 1
    assert results[0]["id"] == "id-1"
    assert results[0]["text"] == "malware C2 beacon outbound"


def test_search_returns_metadata(palace):
    palace.store("Firewall", "high", "alerts", "id-1", "text", {"key": "value"})
    results = palace.search("Firewall", "high", "alerts", "text")
    assert results[0]["metadata"]["key"] == "value"


def test_search_empty_collection_returns_empty(palace):
    results = palace.search("Firewall", "high", "alerts", "any query")
    assert results == []


def test_upsert_overwrites(palace):
    palace.store("Firewall", "high", "alerts", "id-1", "original text", {"v": "1"})
    palace.store("Firewall", "high", "alerts", "id-1", "updated text", {"v": "2"})
    assert palace.count("Firewall", "high", "alerts") == 1
    results = palace.search("Firewall", "high", "alerts", "updated")
    assert results[0]["metadata"]["v"] == "2"


def test_list_collections(palace):
    palace.store("Firewall", "high", "alerts", "id-1", "text", {"severity": "high"})
    palace.store("EDR", "critical", "alerts", "id-2", "text", {"severity": "critical"})
    cols = palace.list_collections()
    assert len(cols) == 2


def test_search_all_rooms(palace):
    palace.store("Firewall", "high", "alerts", "id-1", "C2 beacon high severity", {"severity": "high"})
    palace.store("Firewall", "critical", "alerts", "id-2", "ransomware critical", {"severity": "critical"})
    results = palace.search_all_rooms("Firewall", "alerts", "ransomware", n_results=5)
    ids = [r["id"] for r in results]
    assert "id-2" in ids


def test_n_results_capped_at_collection_size(palace):
    palace.store("Firewall", "high", "alerts", "id-1", "single document", {"severity": "high"})
    # Requesting more than available should not raise
    results = palace.search("Firewall", "high", "alerts", "document", n_results=100)
    assert len(results) == 1
