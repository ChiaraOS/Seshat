import csv
import logging
from pathlib import Path
from typing import Iterator, Optional

from .base import BaseAlertSource
from .schema import AlertSeverity, HostContext, NetworkContext, NormalizedAlert

logger = logging.getLogger(__name__)


class CSVAlertSource(BaseAlertSource):
    """Ingest alerts from a delimited CSV file.

    Requires a ``field_mapping`` dict in the source config that maps
    NormalizedAlert schema field names to CSV column names.
    """

    def alerts(self) -> Iterator[NormalizedAlert]:
        file_path = Path(self.config["file_path"])
        if not file_path.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        delimiter = self.config.get("delimiter", ",")
        field_mapping: dict = self.config.get("field_mapping", {})

        with open(file_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            for row in reader:
                yield self._row_to_alert(dict(row), field_mapping)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_alert(self, row: dict, field_mapping: dict) -> NormalizedAlert:
        def get(schema_field: str) -> Optional[str]:
            """Return the CSV value for a schema field, or None if missing/empty."""
            col = field_mapping.get(schema_field)
            if col and col in row:
                val = row[col]
                return val if val else None
            return None

        timestamp = self._parse_timestamp(get("timestamp"))
        severity = self._parse_severity(get("severity"))
        src_port = self._parse_int(get("src_port"), "src_port")
        dst_port = self._parse_int(get("dst_port"), "dst_port")

        return NormalizedAlert(
            source_type=self.source_type,
            source_name=self.source_name,
            timestamp=timestamp,
            severity=severity,
            category=get("category"),
            action=get("action"),
            description=get("description"),
            rule_name=get("rule_name"),
            network=NetworkContext(
                src_ip=get("src_ip"),
                dst_ip=get("dst_ip"),
                src_port=src_port,
                dst_port=dst_port,
                protocol=get("protocol"),
                direction=get("direction"),
            ),
            host=HostContext(
                hostname=get("hostname"),
                ip=get("host_ip"),
                user=get("user"),
            ),
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
    def _parse_severity(value: Optional[str]) -> AlertSeverity:
        if not value:
            return AlertSeverity.UNKNOWN
        try:
            return AlertSeverity(value.lower())
        except ValueError:
            logger.warning("Unknown severity value: %r — defaulting to unknown", value)
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
