import json

from app.metrics import write_pending_metrics


def test_pending_metrics_artifact(tmp_path):
    path = write_pending_metrics(tmp_path)
    assert json.loads(path.read_text())["status"] == "pending_collection"
