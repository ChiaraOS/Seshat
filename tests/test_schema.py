"""Tests for NormalizedAlert and related schema models."""
import pytest

from seshat.ingestion.schema import (
    AlertSeverity,
    HostContext,
    NetworkContext,
    NormalizedAlert,
)


def test_alert_auto_fields():
    alert = NormalizedAlert(source_type="csv", source_name="test", raw={"k": "v"})
    assert alert.seshat_id
    assert alert.ingested_at


def test_alert_defaults():
    alert = NormalizedAlert(source_type="csv", source_name="test", raw={})
    assert alert.severity == AlertSeverity.UNKNOWN
    assert alert.network == NetworkContext()
    assert alert.host == HostContext()
    assert alert.timestamp is None


def test_to_text_contains_key_fields():
    alert = NormalizedAlert(
        source_type="csv",
        source_name="fw01",
        severity=AlertSeverity.HIGH,
        description="C2 beacon",
        category="malware",
        network=NetworkContext(src_ip="10.0.0.1", dst_ip="1.2.3.4"),
        host=HostContext(hostname="ws-1", user="alice"),
        raw={},
    )
    text = alert.to_text()
    assert "severity=high" in text
    assert "fw01" in text
    assert "C2 beacon" in text
    assert "category=malware" in text
    assert "src=10.0.0.1" in text
    assert "dst=1.2.3.4" in text
    assert "host=ws-1" in text
    assert "user=alice" in text


def test_to_mempalace_metadata_flat():
    alert = NormalizedAlert(
        source_type="csv",
        source_name="fw01",
        severity=AlertSeverity.CRITICAL,
        raw={"original": "data"},
    )
    meta = alert.to_mempalace_metadata()
    # Must be a flat dict — no nested objects
    for v in meta.values():
        assert not isinstance(v, dict), f"Nested dict found in metadata: {v}"
    assert meta["severity"] == "critical"
    assert meta["source_name"] == "fw01"
    assert "seshat_id" in meta
    assert "ingested_at" in meta


def test_to_mempalace_metadata_no_none():
    alert = NormalizedAlert(source_type="csv", source_name="x", raw={})
    meta = alert.to_mempalace_metadata()
    for k, v in meta.items():
        assert v is not None, f"None value for key {k!r}"


def test_severity_enum_all_values():
    for val in ("critical", "high", "medium", "low", "info", "unknown"):
        assert AlertSeverity(val).value == val


def test_severity_enum_is_str():
    assert isinstance(AlertSeverity.HIGH, str)


def test_raw_is_preserved():
    original = {"col1": "val1", "col2": "val2"}
    alert = NormalizedAlert(source_type="csv", source_name="x", raw=original)
    assert alert.raw == original
