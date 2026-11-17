import json

from app.publishing import Approval, load_approval, save_approval


def test_approval_round_trip(tmp_path):
    path = tmp_path / "approval.json"
    save_approval(path, Approval(status="approved", reviewer="tester", notes="ok"))
    assert load_approval(path).status == "approved"
    assert json.loads(path.read_text())["reviewer"] == "tester"
