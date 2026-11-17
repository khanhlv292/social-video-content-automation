import json
from pathlib import Path

from app.pipeline import load_topics, validate, TemplateContentGenerator


def test_generated_package_is_valid():
    topic = load_topics(Path("config/topics.json"))[0]
    package = TemplateContentGenerator().generate(topic, "test-package")
    validate(package)


def test_topics_file_is_json():
    assert isinstance(json.loads(Path("config/topics.json").read_text()), list)
