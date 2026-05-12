import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    UNKNOWN = "unknown"


class NetworkContext(BaseModel):
    src_ip: Optional[str] = None
    dst_ip: Optional[str] = None
    src_port: Optional[int] = None
    dst_port: Optional[int] = None
    protocol: Optional[str] = None
    direction: Optional[str] = None


class HostContext(BaseModel):
    hostname: Optional[str] = None
    ip: Optional[str] = None
    user: Optional[str] = None


class NormalizedAlert(BaseModel):
    seshat_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_type: str
    source_name: str
    timestamp: Optional[datetime] = None
    severity: AlertSeverity = AlertSeverity.UNKNOWN
    category: Optional[str] = None
    action: Optional[str] = None
    description: Optional[str] = None
    rule_name: Optional[str] = None
    network: NetworkContext = Field(default_factory=NetworkContext)
    host: HostContext = Field(default_factory=HostContext)
    raw: Dict[str, Any]

    def to_text(self) -> str:
        """Return a keyword-rich string used for semantic embedding."""
        parts = [
            f"severity={self.severity.value}",
            f"source={self.source_name}",
        ]
        if self.category:
            parts.append(f"category={self.category}")
        if self.action:
            parts.append(f"action={self.action}")
        if self.description:
            parts.append(self.description)
        if self.rule_name:
            parts.append(f"rule={self.rule_name}")
        if self.network.src_ip:
            parts.append(f"src={self.network.src_ip}")
        if self.network.dst_ip:
            parts.append(f"dst={self.network.dst_ip}")
        if self.network.protocol:
            parts.append(f"proto={self.network.protocol}")
        if self.host.hostname:
            parts.append(f"host={self.host.hostname}")
        if self.host.user:
            parts.append(f"user={self.host.user}")
        return " | ".join(parts)

    def to_mempalace_metadata(self) -> Dict[str, Any]:
        """Return a flat dict suitable for ChromaDB metadata (no nested objects, no None)."""
        return {
            "seshat_id": self.seshat_id,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "severity": self.severity.value,
            "category": self.category or "",
            "action": self.action or "",
            "rule_name": self.rule_name or "",
            "src_ip": self.network.src_ip or "",
            "dst_ip": self.network.dst_ip or "",
            "src_port": self.network.src_port or 0,
            "dst_port": self.network.dst_port or 0,
            "protocol": self.network.protocol or "",
            "direction": self.network.direction or "",
            "hostname": self.host.hostname or "",
            "host_ip": self.host.ip or "",
            "user": self.host.user or "",
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "ingested_at": self.ingested_at.isoformat(),
        }
