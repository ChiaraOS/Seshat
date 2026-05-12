# Seshat — CLAUDE.md

## What is this project
SOC AI assistant for alert triage. Config-driven, Pydantic-validated, ChromaDB-backed semantic memory, local Ollama LLM.

## Non-negotiable design rules
1. **Config-driven**: new data source = new YAML file in `config/sources/`, no Python changes
2. **NormalizedAlert is the pipeline contract**: every source adapter produces `NormalizedAlert` objects; raw dicts never cross module boundaries
3. **`raw` is sacred**: every original field preserved in `alert.raw`; nothing discarded
4. **SOURCE_REGISTRY is the extension point**: add a source type by subclassing `BaseAlertSource` and registering it in `seshat/ingestion/__init__.py`
5. **LLM never guesses**: `GROUNDED_RESPONSE_PROMPT` enforces citation of retrieved records; never relax this constraint

## Key implementation decisions
- MemPalace is implemented directly on ChromaDB (no external `mempalace` package dependency). Wing/Room/Hall hierarchy maps to ChromaDB collection names: `{wing}__{room}__{hall}`.
- `OllamaClient` uses `httpx` for HTTP calls to a local Ollama instance.
- `AlertSeverity` is a Pydantic `str` enum — safe for JSON serialisation and ChromaDB metadata.
- Timestamp parsing uses `python-dateutil` for flexible format support.

## Module layout
```
seshat/
  ingestion/   — schema, base class, source adapters, registry
  memory/      — MemPalaceClient (ChromaDB wrapper)
  agent/       — OllamaClient + prompt templates
  normalization/ — reserved for future transform logic
scripts/
  ingest.py    — CLI entry point (ingest + index into MemPalace)
config/
  config.yaml              — global settings
  sources/*.yaml           — one file per source
tests/
  fixtures/sample_firewall.csv
```

## Running the project
```bash
python -m venv .venv && .venv\Scripts\activate
pip install -e .[dev]

# Ingest the sample firewall CSV
python scripts/ingest.py ingest config/sources/firewall_csv.yaml

# Dry-run (print normalised alerts, don't store)
python scripts/ingest.py ingest config/sources/firewall_csv.yaml --dry-run

# Run tests
pytest
```

## Adding a new source type
1. Create `seshat/ingestion/<type>_source.py` — subclass `BaseAlertSource`, implement `alerts()`
2. Add one line to `SOURCE_REGISTRY` in `seshat/ingestion/__init__.py`
3. Create `config/sources/<name>.yaml` with `source_type: <type>` and the required fields
