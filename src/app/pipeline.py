from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .metrics import write_pending_metrics
from .publishing import Approval, load_approval, publish_youtube, save_approval
from .video_factory import write_video_artifacts


BLOCKED_TERMS = {
    "guaranteed income",
    "kiếm tiền chắc chắn",
    "lợi nhuận chắc chắn",
    "cure",
    "chữa khỏi",
}


@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    audience: str
    angle: str


@dataclass(frozen=True)
class ContentPackage:
    id: str
    topic: str
    audience: str
    title: str
    script: str
    caption: str
    hashtags: list[str]
    disclosure: str
    created_at: str


class TemplateContentGenerator:
    def generate(self, topic: Topic, package_id: str) -> ContentPackage:
        title = f"{topic.name}: 1 mẹo nhỏ bạn có thể thử hôm nay"
        script = (
            f"Mở đầu: Nếu bạn là {topic.audience}, hãy thử mẹo này. "
            f"Hôm nay chúng ta nói về {topic.name.lower()}. "
            f"{topic.angle.capitalize()}. "
            "Hãy thử trong phạm vi phù hợp với hoàn cảnh của bạn và tự kiểm chứng kết quả. "
            "Lưu video để xem lại và chia sẻ với người cần nó."
        )
        caption = (
            f"Một gợi ý ngắn về {topic.name.lower()} cho {topic.audience}. "
            "Nội dung mang tính giáo dục, không phải cam kết kết quả."
        )
        return ContentPackage(
            id=package_id,
            topic=topic.slug,
            audience=topic.audience,
            title=title,
            script=script,
            caption=caption,
            hashtags=[f"#{topic.slug.replace('-', '')}", "#shorts", "#learn"],
            disclosure="Nội dung giáo dục; không phải tư vấn chuyên môn hay cam kết thu nhập.",
            created_at=datetime.now(UTC).isoformat(),
        )


def load_topics(path: Path) -> list[Topic]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Không thể đọc topics file: {path}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError("topics file phải là một mảng không rỗng")
    return [Topic(**item) for item in data]


def validate(package: ContentPackage) -> None:
    text = " ".join((package.title, package.script, package.caption)).lower()
    found = sorted(term for term in BLOCKED_TERMS if term in text)
    if found:
        raise ValueError(f"Nội dung chứa từ khóa cần duyệt thủ công: {', '.join(found)}")
    if not 80 <= len(package.script) <= 900:
        raise ValueError("Kịch bản phải dài từ 80 đến 900 ký tự")
    if not package.disclosure:
        raise ValueError("Thiếu disclosure")


def publish_webhook(package: ContentPackage, url: str) -> dict[str, Any]:
    payload = json.dumps(asdict(package), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return {"status": response.status, "response": body[:1000]}
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Publisher webhook thất bại: {exc}") from exc


def run(
    topic_name: str | None,
    output_dir: Path,
    render: bool = False,
    approve: bool = False,
    publish: bool = False,
) -> Path:
    topics = load_topics(Path(os.getenv("TOPICS_FILE", "config/topics.json")))
    topic = next((item for item in topics if item.name == topic_name or item.slug == topic_name), topics[0])
    package_id = f"{date.today().isoformat()}-{re.sub(r'[^a-z0-9-]', '-', topic.slug)}"
    package = TemplateContentGenerator().generate(topic, package_id)
    validate(package)

    destination = output_dir / date.today().isoformat()
    destination.mkdir(parents=True, exist_ok=True)
    package_path = destination / "content.json"
    package_path.write_text(json.dumps(asdict(package), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if render:
        write_video_artifacts(asdict(package), destination)
        write_pending_metrics(destination)
        approval_path = destination / "approval.json"
        approval = Approval(
            status="approved" if approve else "pending",
            reviewer=os.getenv("APPROVAL_REVIEWER", "local-user") if approve else "",
            notes="Approved by CLI" if approve else "Waiting for review",
        )
        save_approval(approval_path, approval)

    mode = os.getenv("PUBLISH_MODE", "dry-run").lower()
    approval = load_approval(destination / "approval.json") if render else Approval("pending", "", "")
    if mode == "webhook":
        if approval.status != "approved":
            raise RuntimeError("Publishing requires an approved rendered video")
        url = os.getenv("PUBLISH_WEBHOOK_URL")
        if not url:
            raise RuntimeError("PUBLISH_WEBHOOK_URL bắt buộc khi PUBLISH_MODE=webhook")
        result = publish_webhook(package, url)
        (destination / "publish-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    elif publish:
        if approval.status != "approved":
            raise RuntimeError("Publishing requires an approved rendered video")
        result = publish_youtube(destination / "video.mp4", asdict(package))
        (destination / "publish-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    elif mode != "dry-run":
        raise ValueError("PUBLISH_MODE chỉ nhận dry-run hoặc webhook")
    return package_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a safe social video content package")
    parser.add_argument("--topic", help="Topic slug or exact topic name")
    parser.add_argument("--output", default="artifacts", help="Artifact directory")
    parser.add_argument("--render", action="store_true", help="Render a 9:16 MP4 and run video QA")
    parser.add_argument("--approve", action="store_true", help="Mark the generated video approved")
    parser.add_argument("--publish", action="store_true", help="Publish approved video to YouTube")
    args = parser.parse_args()
    try:
        path = run(args.topic, Path(args.output), render=args.render, approve=args.approve, publish=args.publish)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(path)
