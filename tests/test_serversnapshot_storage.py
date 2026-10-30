import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("snapshot_storage", Path(__file__).parents[1] / "serversnapshot" / "storage.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def test_finalize_and_verify(tmp_path):
    root = s.secure_directory(tmp_path / "private")
    s.private_write(root / "metadata.json", {"hello": "world"})
    with s.private_jsonl(root / "messages" / "123.jsonl") as f:
        f.write(json.dumps({"id": "123", "content": "hi"}) + "\n")
    s.finalize(root)
    result = s.verify(root)
    assert len(result["files"]) == 2
    (root / "messages" / "123.jsonl").write_text("tampered")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        s.verify(root)


def test_reject_extra_file(tmp_path):
    root = s.secure_directory(tmp_path / "private")
    s.private_write(root / "metadata.json", {})
    s.finalize(root)
    (root / "another_file").write_text("test")
    with pytest.raises(ValueError, match="Unexpected or missing"):
        s.verify(root)


def test_reject_ids(tmp_path):
    with pytest.raises(ValueError):
        s.checked_snapshot(tmp_path, "../etc", "bad")
    with pytest.raises(ValueError):
        s.checked_snapshot(tmp_path, "123456789012345678", "../../etc/passwd")


def test_permissions(tmp_path):
    root = s.secure_directory(tmp_path / "private")
    assert root.stat().st_mode & 0o077 == 0
    s.private_write(root / "metadata.json", {"content": "private"})
    assert (root / "metadata.json").stat().st_mode & 0o077 == 0
