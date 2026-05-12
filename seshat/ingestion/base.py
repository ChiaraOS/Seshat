from abc import ABC, abstractmethod
from typing import Iterator

from .schema import NormalizedAlert


class BaseAlertSource(ABC):
    """Abstract base for all alert source adapters.

    Subclass this and implement ``alerts()``. Register the subclass in
    ``seshat/ingestion/__init__.py`` to make it available by name.
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.source_name: str = config.get("source_name", "unknown")
        self.source_type: str = config.get("source_type", "unknown")

    @abstractmethod
    def alerts(self) -> Iterator[NormalizedAlert]:
        """Yield :class:`NormalizedAlert` objects from the source."""
        ...
