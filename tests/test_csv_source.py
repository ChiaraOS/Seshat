"""Tests for CSVAlertSource and SOURCE_REGISTRY."""
from pathlib import Path

import pytest

from seshat.ingestion import SOURCE_REGISTRY, get_source
from seshat.ingestion.schema import AlertSeverity, NormalizedAlert

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_firewall.csv"

BASE_CONFIG = {
    "source_type": "csv",
    "source_name": "test_fw",
    "file_path": str(FIXTURE_CSV),
    "field_mapping": {
        "timestamp": "timestamp",
        "severity": "severity",
        "category": "category",
        "action": "action",
        "description": "description",
        "rule_name": "rule_name",
        "src_ip": "src_ip",
        "dst_ip": "dst_ip",
        "src_port": "src_port",
        "dst_port": "dst_port",
        "protocol": "protocol",
        "direction": "direction",
        "hostname": "hostname",
        "user": "user",
    },
}


def _all_alerts():
    return list(get_source(BASE_CONFIG).alerts())


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

def test_registry_has_csv():
    assert "csv" in SOURCE_REGISTRY


def test_registry_unknown_raises():
    with pytest.raises(ValueError, match="Unknown source type"):
        get_source({"source_type": "does_not_exist"})


# ------------------------------------------------------------------
# Alert count and contract
# ------------------------------------------------------------------

def test_yields_correct_count():
    assert len(_all_alerts()) == 8


def test_all_are_normalized_alert():
    for alert in _all_alerts():
        assert isinstance(alert, NormalizedAlert)


def test_raw_preserved_for_all():
    for alert in _all_alerts():
        assert isinstance(alert.raw, dict)
        assert alert.raw  # must not be empty


def test_source_name_propagated():
    for alert in _all_alerts():
        assert alert.source_name == "test_fw"


def test_source_type_propagated():
    for alert in _all_alerts():
        assert alert.source_type == "csv"


# ------------------------------------------------------------------
# Severity mapping
# ------------------------------------------------------------------

def test_severity_mapping():
    alerts = _all_alerts()
    severities = {a.severity for a in alerts}
    assert AlertSeverity.HIGH in severities
    assert AlertSeverity.CRITICAL in severities
    assert AlertSeverity.MEDIUM in severities
    assert AlertSeverity.LOW in severities
    assert AlertSeverity.INFO in severities


# ------------------------------------------------------------------
# Network context
# ------------------------------------------------------------------

def test_first_alert_network():
    first = _all_alerts()[0]
    assert first.network.src_ip == "192.168.1.105"
    assert first.network.dst_ip == "185.220.101.42"
    assert first.network.src_port == 49521
    assert first.network.dst_port == 443
    assert first.network.protocol == "TCP"
    assert first.network.direction == "outbound"


def test_missing_ports_are_none():
    # Row 4 (ICMP sweep) has no ports
    alerts = _all_alerts()
    icmp_alerts = [a for a in alerts if a.network.protocol == "ICMP"]
    assert icmp_alerts
    assert icmp_alerts[0].network.src_port is None
    assert icmp_alerts[0].network.dst_port is None


# ------------------------------------------------------------------
# Host context
# ------------------------------------------------------------------

def test_first_alert_host():
    first = _all_alerts()[0]
    assert first.host.hostname == "workstation-042"
    assert first.host.user == "jdoe"


# ------------------------------------------------------------------
# Timestamps
# ------------------------------------------------------------------

def test_timestamps_parsed():
    for alert in _all_alerts():
        assert alert.timestamp is not None


# ------------------------------------------------------------------
# Missing file
# ------------------------------------------------------------------

def test_missing_file_raises():
    config = dict(BASE_CONFIG)
    config["file_path"] = "/nonexistent/path/file.csv"
    with pytest.raises(FileNotFoundError):
        list(get_source(config).alerts())
