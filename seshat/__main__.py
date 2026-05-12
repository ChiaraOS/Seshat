"""Entry point for ``python -m seshat``.

Starts the Seshat API server with uvicorn, reading settings from
``config/config.yaml`` (or the path given by --config).

Usage
-----
  python -m seshat
  python -m seshat --config /path/to/config.yaml
  python -m seshat --host 127.0.0.1 --port 9000
"""
import argparse
import logging
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m seshat", description="Start the Seshat server")
    p.add_argument("--config", default="config/config.yaml", metavar="PATH",
                   help="Path to config.yaml (default: config/config.yaml)")
    p.add_argument("--host", default=None, help="Bind host (overrides config)")
    p.add_argument("--port", type=int, default=None, help="Bind port (overrides config)")
    p.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    import yaml
    from pathlib import Path

    cfg: dict = {}
    config_path = Path(args.config)
    if config_path.exists():
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    else:
        print(f"[seshat] Config not found at {config_path!s} — using defaults.", file=sys.stderr)

    log_level = args.log_level or cfg.get("logging", {}).get("level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    server_cfg = cfg.get("server", {})
    host = args.host or server_cfg.get("host", "0.0.0.0")
    port = args.port or server_cfg.get("port", 8000)

    import uvicorn
    from seshat.server import create_app

    logging.getLogger("seshat").info(
        "Starting Seshat on http://%s:%d  (Open-WebUI → http://host.docker.internal:%d/v1)",
        host, port, port,
    )
    uvicorn.run(create_app(args.config), host=host, port=port, log_level=log_level.lower())


if __name__ == "__main__":
    main()
