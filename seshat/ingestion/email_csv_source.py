"""Email CSV source adapter.

Handles CSVs exported from Outlook where each row is an email and the
actual alert data is a structured line embedded in the email body.

The alert line format is fully configurable via ``alert_line_pattern``
in the source YAML — named capture groups map directly to NormalizedAlert
fields. This means any vendor (SonicWall, FortiGate, Palo Alto, …) can
be supported with a new config file and no Python changes.

Named capture groups recognised in ``alert_line_pattern``:
  timestamp, severity_raw, category, action, description, rule_name,
  src_ip, src_port, dst_ip, dst_port, protocol, direction, hostname, user

Named capture groups recognised in ``subject_pattern``:
  rule_name, category, description
"""

import csv
import logging
import re
from pathlib import Path
from typing import Iterator, Optional

from .base import BaseAlertSource
from .schema import AlertSeverity, HostContext, NetworkContext, NormalizedAlert

logger = logging.getLogger(__name__)


class EmailCsvAlertSource(BaseAlertSource):
    """Ingest security alerts from an Outlook-exported email CSV.

    Each CSV row is one email. The adapter searches the configured body
    column for a line matching ``alert_line_pattern`` and extracts
    structured data from the named capture groups.

    Rows that contain no matching alert line are silently skipped.
    """

    def alerts(self) -> Iterator[NormalizedAlert]:
        file_path = Path(self.config["file_path"])
        if not file_path.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        encoding = self.config.get("encoding", "latin-1")
        delimiter = self.config.get("delimiter", ",")
        body_column = self.config.get("body_column", "Cuerpo")
        alert_pattern = re.compile(
            self.config["alert_line_pattern"],
            re.IGNORECASE | re.MULTILINE | re.VERBOSE,
        )
        subject_pattern_str = self.config.get("subject_pattern")
        subject_re = (
            re.compile(subject_pattern_str, re.IGNORECASE | re.VERBOSE)
            if subject_pattern_str else None
        )
        severity_map: dict = self.config.get("severity_map", {})

        skipped = 0
        with open(file_path, newline="", encoding=encoding, errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            for row in reader:
                body = row.get(body_column, "") or ""
                match = alert_pattern.search(body)
                if not match:
                    skipped += 1
                    continue

                groups = match.groupdict()
                subject_groups: dict = {}
                if subject_re:
                    sm = subject_re.search(body)
                    if sm:
                        subject_groups = sm.groupdict()

                yield self._build_alert(row, body, groups, subject_groups, severity_map)

        if skipped:
            logger.debug(
                "%s: skipped %d row(s) with no alert line match", self.source_name, skipped
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_alert(
        self,
        row: dict,
        body: str,
        groups: dict,
        subject_groups: dict,
        severity_map: dict,
    ) -> NormalizedAlert:
        def g(key: str) -> Optional[str]:
            """Return a non-empty value from alert groups, subject groups, or None."""
            val = groups.get(key) or subject_groups.get(key)
            return val.strip() if val and val.strip() else None

        timestamp = self._parse_timestamp(g("timestamp"))
        severity = self._map_severity(g("severity_raw"), severity_map)
        src_port = self._parse_int(g("src_port"), "src_port")
        dst_port = self._parse_int(g("dst_port"), "dst_port")

        return NormalizedAlert(
            source_type=self.source_type,
            source_name=self.source_name,
            timestamp=timestamp,
            severity=severity,
            category=g("category"),
            action=g("action"),
            description=g("description"),
            rule_name=g("rule_name"),
            network=NetworkContext(
                src_ip=g("src_ip"),
                dst_ip=g("dst_ip"),
                src_port=src_port,
                dst_port=dst_port,
                protocol=g("protocol"),
                direction=g("direction"),
            ),
            host=HostContext(
                hostname=g("hostname"),
                ip=None,
                user=g("user"),
            ),
            # raw keeps the full CSV row; body is too large for metadata
            # but is preserved here for completeness
            raw={k: v for k, v in row.items() if k is not None},
        )

    @staticmethod
    def _parse_timestamp(value: Optional[str]):
        if not value:
            return None
        try:
            from dateutil import parser as dp
            return dp.parse(value)
        except Exception:
            logger.warning("Could not parse timestamp: %r", value)
            return None

    @staticmethod
    def _map_severity(raw: Optional[str], severity_map: dict) -> AlertSeverity:
        if not raw:
            return AlertSeverity.UNKNOWN
        # Try the config-provided map first (e.g. "Alert" → "high")
        mapped = severity_map.get(raw) or severity_map.get(raw.lower())
        candidate = mapped or raw
        try:
            return AlertSeverity(candidate.lower())
        except ValueError:
            logger.warning("Unknown severity %r (mapped: %r) — defaulting to unknown", raw, mapped)
            return AlertSeverity.UNKNOWN

    @staticmethod
    def _parse_int(value: Optional[str], field_name: str) -> Optional[int]:
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            logger.warning("Could not parse %s as int: %r", field_name, value)
            return None
