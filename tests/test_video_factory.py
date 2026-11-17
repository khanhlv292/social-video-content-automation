import json
from pathlib import Path

from app.pipeline import TemplateContentGenerator, load_topics
from app.video_factory import build_video_plan, write_srt


def test_video_plan_has_scenes_and_license_manifest():
    topic = load_topics(Path("config/topics.json"))[0]
    package = TemplateContentGenerator().generate(topic, "test-video")
    plan = build_video_plan({"id": package.id, "title": package.title, "script": package.script})
    assert plan.scenes
    assert all(asset.license for asset in plan.asset_manifest.assets)


def test_srt_has_timestamps(tmp_path):
    topic = load_topics(Path("config/topics.json"))[0]
    package = TemplateContentGenerator().generate(topic, "test-srt")
    plan = build_video_plan({"id": package.id, "title": package.title, "script": package.script})
    path = write_srt(plan.scenes, tmp_path / "captions.srt")
    assert "-->" in path.read_text()
