import logging
from typing import Any, Dict, List, Optional

import httpx

from .prompts import GROUNDED_RESPONSE_PROMPT, TRANSLATE_QUERY_PROMPT

logger = logging.getLogger(__name__)


class OllamaClient:
    """HTTP client for a local Ollama instance.

    Handles both pipeline steps:
    1. Query translation  — natural language → compact search string
    2. Grounded response  — retrieved records + question → structured answer
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        """Send a completion request and return the model's response string."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        logger.debug("Ollama generate: model=%s prompt_len=%d", self.model, len(prompt))
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["response"]

    def translate_query(self, question: str) -> str:
        """Translate a natural-language question into a semantic search query string."""
        prompt = TRANSLATE_QUERY_PROMPT.format(question=question)
        result = self.generate(prompt, temperature=0.0).strip()
        logger.debug("Translated query: %r → %r", question, result)
        return result

    def grounded_response(self, question: str, records: List[Dict[str, Any]]) -> str:
        """Produce a grounded structured answer from retrieved alert records.

        The prompt explicitly forbids the model from guessing anything not
        present in *records*.
        """
        if records:
            records_text = "\n\n".join(
                f"[Record {i + 1}]\n{r['text']}" for i, r in enumerate(records)
            )
        else:
            records_text = "(no records retrieved)"

        prompt = GROUNDED_RESPONSE_PROMPT.format(
            question=question,
            records=records_text,
        )
        return self.generate(prompt, temperature=0.1)

    def answer(
        self,
        question: str,
        wing: str,
        hall: str,
        palace,
        n_results: int = 10,
    ) -> str:
        """Full two-step pipeline: translate → search → respond.

        *palace* must be a :class:`~seshat.memory.MemPalaceClient` instance.
        Searches across all rooms in the given wing.
        """
        search_query = self.translate_query(question)
        records = palace.search_all_rooms(wing, hall, search_query, n_results=n_results)
        logger.info(
            "answer(): query=%r retrieved=%d records from wing=%s",
            search_query, len(records), wing,
        )
        return self.grounded_response(question, records)
