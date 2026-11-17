from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Approval:
    status: str
    reviewer: str
    notes: str


def load_approval(path: Path) -> Approval:
    if not path.exists():
        return Approval(status="pending", reviewer="", notes="")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Approval(**data)


def save_approval(path: Path, approval: Approval) -> None:
    path.write_text(json.dumps(approval.__dict__, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish_youtube(video_path: Path, package: dict) -> dict:
    token = os.getenv("YOUTUBE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("YOUTUBE_ACCESS_TOKEN is required for YouTube publishing")
    metadata = {
        "snippet": {
            "title": package["title"][:100],
            "description": package["caption"] + "\n\n" + package["disclosure"],
            "tags": package["hashtags"],
            "categoryId": "27",
        },
        "status": {"privacyStatus": os.getenv("YOUTUBE_PRIVACY_STATUS", "private")},
    }
    init_request = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video_path.stat().st_size),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(init_request, timeout=60) as response:
            upload_url = response.headers.get("Location")
        if not upload_url:
            raise RuntimeError("YouTube did not return a resumable upload URL")
        upload_request = urllib.request.Request(
            upload_url,
            data=video_path.read_bytes(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"},
            method="PUT",
        )
        with urllib.request.urlopen(upload_request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
            return {"platform": "youtube", "status": response.status, "video_id": body.get("id")}
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"YouTube upload failed: {exc}") from exc
