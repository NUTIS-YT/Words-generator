from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class GenerationStats:
    target: int
    added: int = 0
    duplicates: int = 0
    invalid_responses: int = 0
    api_requests: int = 0
    api_errors: int = 0
    total_latency_seconds: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "running"
    message: str = ""

    @property
    def progress_percent(self) -> float:
        if self.target <= 0:
            return 0.0
        return min(100.0, self.added / self.target * 100.0)

    @property
    def average_latency_seconds(self) -> float:
        if self.api_requests <= 0:
            return 0.0
        return self.total_latency_seconds / self.api_requests

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["progress_percent"] = self.progress_percent
        result["average_latency_seconds"] = self.average_latency_seconds
        return result
