"""FastAPI server exposing Seshat as an OpenAI-compatible endpoint.

Open-WebUI integration
-----------------------
In Open-WebUI → Admin → Settings → Connections → OpenAI API, add:

  URL : http://host.docker.internal:8000/v1   (Windows/macOS)
        http://172.17.0.1:8000/v1             (Linux)
  Key : seshat   (any non-empty string)

Then select the "seshat" model in a chat and ask your SOC questions.
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from seshat.agent import OllamaClient
from seshat.memory import MemPalaceClient

logger = logging.getLogger(__name__)

HALL = "alerts"


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def load_config(path: str) -> dict:
    p = Path(path)
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def create_app(
    config_path: str = "config/config.yaml",
    palace: Optional[MemPalaceClient] = None,
    llm: Optional[OllamaClient] = None,
) -> FastAPI:
    """Build and return the FastAPI application.

    *palace* and *llm* can be injected for testing; otherwise they are
    created from the config file.
    """
    cfg = load_config(config_path)

    if palace is None:
        palace = MemPalaceClient(
            path=cfg.get("mempalace", {}).get("path", "./data/mempalace")
        )

    if llm is None:
        ollama_cfg = cfg.get("ollama", {})
        llm = OllamaClient(
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
            model=ollama_cfg.get("model", "llama3.1:8b"),
        )

    search_wings: List[str] = cfg.get("server", {}).get("search_wings", [])

    app = FastAPI(
        title="Seshat",
        version="0.1.0",
        description="SOC AI assistant — OpenAI-compatible interface",
    )

    # ------------------------------------------------------------------
    # Health / info
    # ------------------------------------------------------------------

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    # ------------------------------------------------------------------
    # OpenAI-compatible endpoints (required by Open-WebUI)
    # ------------------------------------------------------------------

    @app.get("/v1/models")
    def list_models() -> dict:
        return {
            "object": "list",
            "data": [
                {
                    "id": "seshat",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "seshat",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        messages: List[dict] = body.get("messages", [])
        stream: bool = body.get("stream", False)

        # Use the last user turn as the analyst question
        question = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                question = msg.get("content", "").strip()
                break

        if not question:
            raise HTTPException(status_code=400, detail="No user message found")

        answer = _run_pipeline(llm, palace, question, search_wings)

        if stream:
            return StreamingResponse(
                _stream_sse(answer),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "seshat",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    # ------------------------------------------------------------------
    # Seshat-native API
    # ------------------------------------------------------------------

    @app.post("/api/question")
    async def api_question(request: Request) -> dict:
        """Single-shot Q&A: translate → search → grounded response."""
        body = await request.json()
        question: str = body.get("question", "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="'question' field is required")

        wing: Optional[str] = body.get("wing")
        n_results: int = int(body.get("n_results", 10))

        query = llm.translate_query(question)

        if wing:
            records = palace.search_all_rooms(wing, HALL, query, n_results)
        else:
            records = palace.search_global(HALL, query, n_results)

        answer = llm.grounded_response(question, records)
        return {
            "question": question,
            "search_query": query,
            "records_retrieved": len(records),
            "answer": answer,
        }

    @app.post("/api/ingest")
    async def api_ingest(request: Request) -> dict:
        """Ingest alerts from a source config file into MemPalace."""
        body = await request.json()
        config_path_str: str = body.get("config", "")
        if not config_path_str:
            raise HTTPException(status_code=400, detail="'config' field is required")

        source_cfg_path = Path(config_path_str)
        if not source_cfg_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Config not found: {config_path_str}",
            )

        source_cfg = yaml.safe_load(source_cfg_path.read_text(encoding="utf-8"))

        from seshat.ingestion import get_source

        source = get_source(source_cfg)
        palace_cfg = source_cfg.get("mempalace", {})
        wing = palace_cfg.get("wing", "alerts")
        room_field = palace_cfg.get("room_field", "severity")

        count = 0
        for alert in source.alerts():
            room_val = getattr(alert, room_field, alert.severity)
            room = room_val.value if hasattr(room_val, "value") else str(room_val)
            palace.store(
                wing=wing,
                room=room,
                hall=HALL,
                doc_id=alert.seshat_id,
                text=alert.to_text(),
                metadata=alert.to_mempalace_metadata(),
            )
            count += 1

        logger.info("Ingested %d alert(s) into wing=%r via API", count, wing)
        return {"ingested": count, "wing": wing}

    @app.get("/api/status")
    def api_status() -> dict:
        """Return collection names currently in MemPalace."""
        return {"collections": palace.list_collections()}

    return app


# ------------------------------------------------------------------
# Pipeline helpers
# ------------------------------------------------------------------

def _run_pipeline(
    llm: OllamaClient,
    palace: MemPalaceClient,
    question: str,
    wings: List[str],
    n_results: int = 10,
) -> str:
    """Translate → search → grounded response. Returns an error string on failure."""
    try:
        query = llm.translate_query(question)
        if wings:
            records: List[Dict[str, Any]] = []
            for wing in wings:
                records.extend(palace.search_all_rooms(wing, HALL, query, n_results))
            records.sort(key=lambda r: r.get("distance") or 1.0)
            records = records[:n_results]
        else:
            records = palace.search_global(HALL, query, n_results)

        logger.info(
            "pipeline: query=%r retrieved=%d record(s)", query, len(records)
        )
        return llm.grounded_response(question, records)
    except Exception as exc:
        logger.error("Pipeline error: %s", exc, exc_info=True)
        return (
            f"Seshat could not complete the request: {exc}\n\n"
            "Check that Ollama is running and MemPalace contains ingested data."
        )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _stream_sse(text: str) -> Iterator[str]:
    """Yield the full response as OpenAI SSE chunks, word by word."""
    cid = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    ts = int(time.time())

    # Opening role chunk
    yield _sse({
        "id": cid, "object": "chat.completion.chunk", "created": ts, "model": "seshat",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    })

    words = text.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == 0 else f" {word}"
        yield _sse({
            "id": cid, "object": "chat.completion.chunk", "created": ts, "model": "seshat",
            "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
        })

    # Stop chunk
    yield _sse({
        "id": cid, "object": "chat.completion.chunk", "created": ts, "model": "seshat",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    })
    yield "data: [DONE]\n\n"
