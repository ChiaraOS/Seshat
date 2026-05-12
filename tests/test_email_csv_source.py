"""Tests for EmailCsvAlertSource (SonicWall email export format)."""
from pathlib import Path

import pytest

from seshat.ingestion import SOURCE_REGISTRY, get_source
from seshat.ingestion.schema import AlertSeverity, NormalizedAlert

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_sonicwall_email.csv"

# Mirrors the real sonicwall_email.yaml pattern (YAML block scalar → single line)
ALERT_PATTERN = (
    r"(?P<timestamp>\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})"
    r"\s+-\s+\d+\s+-\s+"
    r"(?P<category>[^-]+?)\s+-\s+"
    r"(?P<severity_raw>\w+)\s+-\s+"
    r"(?P<src_ip>[\d.]+),\s*(?P<src_port>\d+),\s*\S+\s+-\s+"
    r"(?P<dst_ip>[\d.]+),\s*(?P<dst_port>\d+),\s*\S+\s+-\s+"
    r"(?P<protocol>\w+)\s+-\s+"
    r"(?P<description>[^\n\r]+)"
)

SUBJECT_PATTERN = r"Asunto:.*?\[[^\]]*\]\s*\[(?P<rule_name>[^\]]+)\]"

BASE_CONFIG = {
    "source_type": "email_csv",
    "source_name": "test_sonicwall",
    "file_path": str(FIXTURE_CSV),
    "encoding": "utf-8",
    "body_column": "Cuerpo",
    "alert_line_pattern": ALERT_PATTERN,
    "subject_pattern": SUBJECT_PATTERN,
    "severity_map": {
        "Alert": "high",
        "Warning": "medium",
        "Notice": "low",
        "Info": "info",
    },
}


def _alerts():
    return list(get_source(BASE_CONFIG).alerts())


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

def test_registry_has_email_csv():
    assert "email_csv" in SOURCE_REGISTRY


# ------------------------------------------------------------------
# Parsing and skipping
# ------------------------------------------------------------------

def test_yields_only_rows_with_alert_lines():
    # Fixture has 4 rows: 3 with alert lines, 1 plain email → expect 3
    assert len(_alerts()) == 3


def test_all_are_normalized_alert():
    for alert in _alerts():
        assert isinstance(alert, NormalizedAlert)


def test_raw_preserved():
    for alert in _alerts():
        assert isinstance(alert.raw, dict)
        assert alert.raw


# ------------------------------------------------------------------
# Field extraction
# ------------------------------------------------------------------

def test_severity_mapped_from_alert_label():
    for alert in _alerts():
        assert alert.severity == AlertSeverity.HIGH


def test_network_context_extracted():
    first = _alerts()[0]
    assert first.network.src_ip == "99.84.9.100"
    assert first.network.dst_ip == "88.27.254.19"
    assert first.network.src_port == 443
    assert first.network.dst_port == 62996
    assert first.network.protocol == "tcp"


def test_category_extracted():
    first = _alerts()[0]
    assert first.category is not None
    assert "Firewall" in first.category or "Settings" in first.category


def test_description_extracted():
    first = _alerts()[0]
    assert first.description is not None
    assert "TCP Flood" in first.description


def test_rule_name_from_subject():
    first = _alerts()[0]
    assert first.rule_name is not None
    assert "TCP Flood" in first.rule_name


def test_timestamps_parsed():
    for alert in _alerts():
        assert alert.timestamp is not None


def test_source_name_propagated():
    for alert in _alerts():
        assert alert.source_name == "test_sonicwall"


# ------------------------------------------------------------------
# Robustness
# ------------------------------------------------------------------

def test_missing_file_raises():
    config = dict(BASE_CONFIG, file_path="/no/such/file.csv")
    with pytest.raises(FileNotFoundError):
        list(get_source(config).alerts())


def test_no_alert_pattern_skips_all_rows():
    config = dict(BASE_CONFIG, alert_line_pattern=r"THIS_WILL_NEVER_MATCH_ANYTHING")
    assert list(get_source(config).alerts()) == []
