import hashlib
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "index_fingerprint", REPO / "evaluation" / "scripts" / "index_fingerprint.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_fingerprint_ids_is_order_independent():
    a = mod.fingerprint_ids(3, ["c", "a", "b"], ["text", "id"])
    b = mod.fingerprint_ids(3, ["a", "b", "c"], ["id", "text"])
    assert a == b
    assert a["rows"] == 3
    assert a["schema"] == ["id", "text"]
    assert a["id_sha256"] == hashlib.sha256("a\nb\nc".encode()).hexdigest()


def test_fingerprint_ids_changes_on_content():
    a = mod.fingerprint_ids(3, ["a", "b", "c"], ["id"])
    b = mod.fingerprint_ids(3, ["a", "b", "d"], ["id"])
    assert a["id_sha256"] != b["id_sha256"]
