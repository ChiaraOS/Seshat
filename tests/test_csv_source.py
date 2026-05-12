"""Tests for CSVAlertSource and SOURCE_REGISTRY.

CSV content is generated in code — no fixture files required.
"""
import textwrap

import pytest

from seshat.ingestion import SOURCE_REGISTRY, get_source
from seshat.ingestion.schema import AlertSeverity, NormalizedAlert

CSV_CONTENT = textwrap.dedent("""\
    timestamp,severity,category,action,description,rule_name,src_ip,dst_ip,src_port,dst_port,protocol,direction,hostname,user
    2024-01-15T08:23:11Z,high,malware,blocked,Outbound C2 beacon,block_c2,192.168.1.105,185.220.101.42,49521,443,TCP,outbound,workstation-042,jdoe
    2024-01-15T08:31:47Z,critical,exploitation,blocked,SQL injection attempt,waf_sqli,203.0.113.77,10.0.1.25,52341,443,TCP,inbound,,
    2024-01-15T09:04:22Z,medium,policy-violation,allowed,Uncategorised domain,default_allow,192.168.2.18,198.51.100.9,54831,80,TCP,outbound,laptop-019,msmith
    2024-01-15T09:12:55Z,low,reconnaissance,detected,ICMP sweep,detect_icmp,203.0.113.14,10.0.0.1,,,ICMP,inbound,,
    2024-01-15T11:30:00Z,info,authentication,allowed,VPN login,allow_vpn,203.0.113.99,10.0.0.1,,,UDP,inbound,,rgarcia
""")

FIELD_MAPPING = {
    "timestamp": "timestamp", "severity": "severity",
    "category": "category", "action": "action",
    "description": "description", "rule_name": "rule_name",
    "src_ip": "src_ip", "dst_ip": "dst_ip",
    "src_port": "src_port", "dst_port": "dst_port",
    "protocol": "protocol", "direction": "direction",
    "hostname": "hostname", "user": "user",
}


@pytest.fixture(scope="module")
def csv_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("csv") / "alerts.csv"
    path.write_text(CSV_CONTENT, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def base_config(csv_file):
    return {
        "source_type": "csv",
        "source_name": "test_fw",
        "file_path": str(csv_file),
        "field_mapping": FIELD_MAPPING,
    }


def _alerts(base_config):
    return list(get_source(base_config).alerts())


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

def test_yields_correct_count(base_config):
    assert len(_alerts(base_config)) == 5


def test_all_are_normalized_alert(base_config):
    for alert in _alerts(base_config):
        assert isinstance(alert, NormalizedAlert)


def test_raw_preserved_for_all(base_config):
    for alert in _alerts(base_config):
        assert isinstance(alert.raw, dict)
        assert alert.raw


def test_source_name_propagated(base_config):
    for alert in _alerts(base_config):
        assert alert.source_name == "test_fw"


def test_source_type_propagated(base_config):
    for alert in _alerts(base_config):
        assert alert.source_type == "csv"


# ------------------------------------------------------------------
# Severity mapping
# ------------------------------------------------------------------

def test_severity_mapping(base_config):
    severities = {a.severity for a in _alerts(base_config)}
    assert AlertSeverity.HIGH in severities
    assert AlertSeverity.CRITICAL in severities
    assert AlertSeverity.MEDIUM in severities
    assert AlertSeverity.LOW in severities
    assert AlertSeverity.INFO in severities


# ------------------------------------------------------------------
# Network context
# ------------------------------------------------------------------

def test_first_alert_network(base_config):
    first = _alerts(base_config)[0]
    assert first.network.src_ip == "192.168.1.105"
    assert first.network.dst_ip == "185.220.101.42"
    assert first.network.src_port == 49521
    assert first.network.dst_port == 443
    assert first.network.protocol == "TCP"
    assert first.network.direction == "outbound"


def test_missing_ports_are_none(base_config):
    alerts = _alerts(base_config)
    icmp = [a for a in alerts if a.network.protocol == "ICMP"]
    assert icmp
    assert icmp[0].network.src_port is None
    assert icmp[0].network.dst_port is None


# ------------------------------------------------------------------
# Host context
# ------------------------------------------------------------------

def test_first_alert_host(base_config):
    first = _alerts(base_config)[0]
    assert first.host.hostname == "workstation-042"
    assert first.host.user == "jdoe"


# ------------------------------------------------------------------
# Timestamps
# ------------------------------------------------------------------

def test_timestamps_parsed(base_config):
    for alert in _alerts(base_config):
        assert alert.timestamp is not None


# ------------------------------------------------------------------
# Missing file
# ------------------------------------------------------------------

def test_missing_file_raises(base_config):
    config = dict(base_config, file_path="/nonexistent/path/file.csv")
    with pytest.raises(FileNotFoundError):
        list(get_source(config).alerts())
