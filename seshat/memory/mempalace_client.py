import logging
import re
from typing import Any, Dict, List, Optional

import chromadb

logger = logging.getLogger(__name__)

# ChromaDB collection names: 3-63 chars, alphanumeric/underscores/hyphens,
# must start and end with alphanumeric, no consecutive periods.
_INVALID_CHARS = re.compile(r"[^a-z0-9_-]")


def _sanitize(value: str) -> str:
    return _INVALID_CHARS.sub("_", value.lower().strip())


class MemPalaceClient:
    """Semantic memory store built on ChromaDB.

    Organisational hierarchy (mirrors the MemPalace concept):
      Wing  — source category (e.g. "Firewall", "EDR")
      Room  — sub-partition, typically severity level
      Hall  — record type, e.g. "alerts"

    Each Wing/Room/Hall triplet maps to one ChromaDB collection named
    ``{wing}__{room}__{hall}`` (lowercased, non-alphanumeric → ``_``).
    """

    def __init__(self, path: str = "./data/mempalace") -> None:
        self._client = chromadb.PersistentClient(path=path)
        logger.debug("MemPalaceClient initialised at %s", path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(
        self,
        wing: str,
        room: str,
        hall: str,
        doc_id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Upsert a single document into the specified Wing/Room/Hall."""
        collection = self._collection(wing, room, hall)
        # ChromaDB 1.x rejects empty dicts; pass None instead.
        meta = metadata if metadata else None
        collection.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
        logger.debug("Stored doc %s in %s", doc_id, self._collection_name(wing, room, hall))

    def search(
        self,
        wing: str,
        room: str,
        hall: str,
        query: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search within Wing/Room/Hall; returns up to *n_results* records."""
        collection = self._collection(wing, room, hall)
        count = collection.count()
        if count == 0:
            return []

        kwargs: dict = {
            "query_texts": [query],
            "n_results": min(n_results, count),
        }
        if where:
            kwargs["where"] = where

        raw = collection.query(**kwargs)
        return self._unpack(raw)

    def search_all_rooms(
        self,
        wing: str,
        hall: str,
        query: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search across every Room in a Wing, merging and re-ranking by distance."""
        results: List[Dict[str, Any]] = []
        for col_name in self._client.list_collections():
            name = col_name.name if hasattr(col_name, "name") else str(col_name)
            prefix = f"{_sanitize(wing)}__"
            suffix = f"__{_sanitize(hall)}"
            if name.startswith(prefix) and name.endswith(suffix):
                room = name[len(prefix):-len(suffix)]
                results.extend(self.search(wing, room, hall, query, n_results))
        results.sort(key=lambda r: r.get("distance") or 1.0)
        return results[:n_results]

    def search_global(
        self,
        hall: str,
        query: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search across ALL wings and rooms for the given hall, ranked by distance."""
        hall_suffix = f"__{_sanitize(hall)}"
        results: List[Dict[str, Any]] = []
        for col in self._client.list_collections():
            name = col.name if hasattr(col, "name") else str(col)
            if not name.endswith(hall_suffix):
                continue
            prefix = name[: -len(hall_suffix)]
            parts = prefix.split("__", 1)
            wing_s = parts[0]
            room_s = parts[1] if len(parts) == 2 else parts[0]
            results.extend(self.search(wing_s, room_s, hall, query, n_results))
        results.sort(key=lambda r: r.get("distance") or 1.0)
        return results[:n_results]

    def count(self, wing: str, room: str, hall: str) -> int:
        return self._collection(wing, room, hall).count()

    def list_collections(self) -> List[str]:
        cols = self._client.list_collections()
        return [c.name if hasattr(c, "name") else str(c) for c in cols]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collection_name(self, wing: str, room: str, hall: str) -> str:
        name = f"{_sanitize(wing)}__{_sanitize(room)}__{_sanitize(hall)}"
        # ChromaDB: 3-63 chars
        if len(name) < 3:
            name = name.ljust(3, "x")
        return name[:63]

    def _collection(self, wing: str, room: str, hall: str):
        return self._client.get_or_create_collection(
            self._collection_name(wing, room, hall)
        )

    @staticmethod
    def _unpack(raw: dict) -> List[Dict[str, Any]]:
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        return [
            {
                "id": ids[i],
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": distances[i] if i < len(distances) else None,
            }
            for i in range(len(ids))
        ]
