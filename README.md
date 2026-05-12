# Seshat

Seshat is an open-source SOC AI assistant for alert filtering, semantic memory, and self-hosted LLM analysis. Named after the Egyptian goddess of writing and records. Nothing is hardcoded — all behaviour is config-driven.

## Architecture

```
Alert sources → Normalisation → MemPalace ──► Ollama LLM ──► SOC Analyst
                                  (ChromaDB)    (local)
```

1. Raw alerts are ingested from any source and normalised to a common Pydantic schema.
2. Normalised alerts are stored in **MemPalace** — a ChromaDB-backed semantic memory organised by Wing / Room / Hall.
3. An analyst asks a question; Ollama translates it into a search query, retrieves matching records, and synthesises a grounded response (citations required — no guessing).

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -e .[dev]
```

### Start infrastructure (Ollama + Open-WebUI)

```bash
docker compose up -d
```

Then pull the default model:

```bash
docker exec -it <ollama_container> ollama pull llama3.1:8b
```

### Ingest alerts

```bash
# Ingest the sample firewall CSV into MemPalace
python scripts/ingest.py ingest config/sources/firewall_csv.yaml

# Dry-run: print normalised alerts as JSON without storing
python scripts/ingest.py ingest config/sources/firewall_csv.yaml --dry-run
```

### Run tests

```bash
pytest
```

## Project structure

```
seshat/
├── ingestion/
│   ├── schema.py          NormalizedAlert (Pydantic model) + enums
│   ├── base.py            BaseAlertSource (abstract class)
│   ├── csv_source.py      CSVAlertSource
│   └── __init__.py        SOURCE_REGISTRY + get_source()
├── memory/
│   └── mempalace_client.py  MemPalaceClient (ChromaDB wrapper)
├── agent/
│   ├── prompts.py         Prompt templates (translate + grounded response)
│   └── ollama_client.py   OllamaClient (two-step pipeline)
└── normalization/         Reserved for future transform logic

config/
├── config.yaml            Global settings (model, MemPalace path)
└── sources/
    └── firewall_csv.yaml  Example source config (Palo Alto firewall CSV)

scripts/
└── ingest.py              CLI entry point

tests/
├── fixtures/
│   └── sample_firewall.csv   8-row realistic firewall log
├── test_schema.py
├── test_csv_source.py
└── test_mempalace.py
```

## Adding a new source type

1. Create `seshat/ingestion/<type>_source.py` — subclass `BaseAlertSource`, implement `alerts()`.
2. Add one line to `SOURCE_REGISTRY` in `seshat/ingestion/__init__.py`.
3. Create `config/sources/<name>.yaml` with `source_type: <type>` and your `field_mapping`.

No other Python changes needed.

## Stack

| Component | Purpose |
|---|---|
| **Pydantic v2** | Schema validation and serialisation |
| **ChromaDB** | Semantic vector store (MemPalace backend) |
| **Ollama** | Local LLM inference (default: `llama3.1:8b`) |
| **httpx** | HTTP client for Ollama API |
| **python-dateutil** | Flexible timestamp parsing |
| **Docker Compose** | Runs Ollama + Open-WebUI locally |

## Open-WebUI wiring

After running `python -m seshat` and `docker compose up -d`:

1. Open Open-WebUI at **http://localhost:3000**
2. Go to **Admin → Settings → Connections → OpenAI API** → add a new connection:
   - **URL**: `http://host.docker.internal:8000/v1` (Windows / macOS)
     or `http://172.17.0.1:8000/v1` (Linux)
   - **API Key**: `seshat` (any non-empty string)
3. Save and select the **seshat** model in a new chat.

Every message you send is now routed through the full Seshat pipeline:
translate → semantic search → grounded response.

### API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/v1/models` | OpenAI model list (required by Open-WebUI) |
| `POST` | `/v1/chat/completions` | OpenAI-compatible chat (streaming supported) |
| `POST` | `/api/question` | Raw Q&A: `{"question": "..."}` |
| `POST` | `/api/ingest` | Ingest via API: `{"config": "config/sources/firewall_csv.yaml"}` |
| `GET` | `/api/status` | List MemPalace collections |

## What's in this release

| Component | Status |
|---|---|
| NormalizedAlert schema | ✅ Done |
| BaseAlertSource | ✅ Done |
| CSVAlertSource | ✅ Done |
| SOURCE_REGISTRY | ✅ Done |
| MemPalaceClient (ChromaDB) | ✅ Done |
| OllamaClient (two-step pipeline) | ✅ Done |
| Prompt templates | ✅ Done |
| CLI ingest script | ✅ Done |
| FastAPI server (OpenAI-compatible) | ✅ Done |
| Open-WebUI wiring | ✅ Done |
| Test suite | ✅ Done |

## Future expansion

- Connectors for SIEM, EDR, email, ticketing systems, and log streams.
- REST API server exposing `/api/ingest`, `/api/search`, `/api/question`.
- Open-WebUI plugin manifest for direct chat integration.
- Rule-based remediation policies.
