#!/usr/bin/env python3
"""CLI entry point for Seshat alert ingestion.

Usage
-----
  python scripts/ingest.py ingest config/sources/firewall_csv.yaml
  python scripts/ingest.py ingest config/sources/firewall_csv.yaml --dry-run
  python scripts/ingest.py ingest config/sources/firewall_csv.yaml --palace-path ./data/mempalace
"""
import argparse
import logging
import sys
from pathlib import Path


def _configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seshat-ingest",
        description="Seshat alert ingestion CLI",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    ingest = sub.add_parser("ingest", help="Ingest alerts from a source config file")
    ingest.add_argument("source_config", help="Path to the source YAML config")
    ingest.add_argument(
        "--palace-path",
        default="./data/mempalace",
        metavar="PATH",
        help="MemPalace storage directory (default: ./data/mempalace)",
    )
    ingest.add_argument(
        "--dry-run",
        action="store_true",
        help="Print normalised alerts as JSON without writing to MemPalace",
    )
    ingest.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )

    return parser


def _run_ingest(args: argparse.Namespace) -> None:
    import yaml

    from seshat.ingestion import get_source
    from seshat.memory.mempalace_client import MemPalaceClient

    config_path = Path(args.source_config)
    if not config_path.exists():
        logging.error("Source config not found: %s", config_path)
        sys.exit(1)

    with open(config_path, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    source = get_source(config)
    log = logging.getLogger("seshat.ingest")

    if args.dry_run:
        log.info("Dry-run mode — alerts will not be stored")
        for alert in source.alerts():
            print(alert.model_dump_json(indent=2))
        return

    palace = MemPalaceClient(path=args.palace_path)
    palace_cfg = config.get("mempalace", {})
    wing = palace_cfg.get("wing", "alerts")
    hall = "alerts"
    room_field = palace_cfg.get("room_field", "severity")

    count = 0
    for alert in source.alerts():
        room_val = getattr(alert, room_field, alert.severity)
        # Unwrap enums to their string value
        room = room_val.value if hasattr(room_val, "value") else str(room_val)

        palace.store(
            wing=wing,
            room=room,
            hall=hall,
            doc_id=alert.seshat_id,
            text=alert.to_text(),
            metadata=alert.to_mempalace_metadata(),
        )
        count += 1

    log.info(
        "Ingested %d alert(s) into MemPalace — wing=%r path=%s",
        count, wing, args.palace_path,
    )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(getattr(args, "log_level", "INFO"))

    if args.command == "ingest":
        _run_ingest(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
