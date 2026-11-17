from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformMetrics:
    platform: str
    content_id: str | None
    status: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    retention_percent: float | None = None
    revenue: float | None = None
    currency: str = "USD"


def write_pending_metrics(destination: Path, platform: str = "youtube") -> Path:
    path = destination / "metrics.json"
    metrics = PlatformMetrics(platform=platform, content_id=None, status="pending_collection")
    path.write_text(json.dumps(asdict(metrics), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
