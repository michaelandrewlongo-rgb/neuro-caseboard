"""The ONNX rerank path: directory-vs-hub-id dispatch, and scoring shape/activation.

The real onnxruntime session is not exercised here (no model in CI) — a fake session/tokenizer
covers the logic this module actually owns: feed construction, sigmoid on 1-logit rerank heads,
raw logits for multi-class NLI heads, and id2label passthrough.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from neuro_core.rerank import Reranker


class _FakeEncoding:
    def __init__(self, n):
        self.ids = [101, 2000, 102][:n] or [101]
        self.attention_mask = [1] * len(self.ids)
        self.type_ids = [0] * len(self.ids)


class _FakeTokenizer:
    def __init__(self):
        self.truncation = None
        self.padded = False
        self.seen = None

    def enable_truncation(self, max_length):
        self.truncation = max_length

    def enable_padding(self):
        self.padded = True

    def encode_batch(self, pairs):
        self.seen = pairs
        return [_FakeEncoding(3) for _ in pairs]


class _FakeSession:
    def __init__(self, logits, input_names=("input_ids", "attention_mask", "token_type_ids")):
        self._logits = logits
        self._inputs = [types.SimpleNamespace(name=n) for n in input_names]
        self.feeds = None

    def get_inputs(self):
        return self._inputs

    def run(self, _outputs, feeds):
        import numpy as np
        self.feeds = feeds
        return [np.array(self._logits)]


@pytest.fixture
def onnx_dir(tmp_path):
    """A model directory shaped like a real export (contents are never parsed by the fakes)."""
    (tmp_path / "model.onnx").write_bytes(b"not-a-real-onnx-graph")
    (tmp_path / "tokenizer.json").write_text("{}")
    (tmp_path / "config.json").write_text(json.dumps(
        {"id2label": {"0": "contradiction", "1": "neutral", "2": "entailment"}}))
    return tmp_path


def _install_fakes(monkeypatch, session, tokenizer):
    ort = types.ModuleType("onnxruntime")
    ort.SessionOptions = lambda: types.SimpleNamespace(intra_op_num_threads=0)
    ort.InferenceSession = lambda *a, **k: session
    monkeypatch.setitem(sys.modules, "onnxruntime", ort)
    toks = types.ModuleType("tokenizers")
    toks.Tokenizer = types.SimpleNamespace(from_file=lambda _p: tokenizer)
    monkeypatch.setitem(sys.modules, "tokenizers", toks)


def test_rerank_head_scores_are_sigmoided_and_ordered(monkeypatch, onnx_dir):
    from neuro_core.onnx_rerank import OnnxCrossEncoder
    tokenizer = _FakeTokenizer()
    _install_fakes(monkeypatch, _FakeSession([[2.0], [-2.0]]), tokenizer)

    scores = OnnxCrossEncoder(onnx_dir).predict([("q", "hit"), ("q", "miss")])

    assert scores[0] == pytest.approx(0.8808, abs=1e-3)   # sigmoid(2.0)
    assert scores[1] == pytest.approx(0.1192, abs=1e-3)   # sigmoid(-2.0)
    assert tokenizer.truncation == 512 and tokenizer.padded
    assert tokenizer.seen == [("q", "hit"), ("q", "miss")]


def test_multiclass_head_returns_raw_logit_rows(monkeypatch, onnx_dir):
    """NLIVerifier softmaxes these itself and indexes by id2label — don't pre-activate them."""
    from neuro_core.onnx_rerank import OnnxCrossEncoder
    _install_fakes(monkeypatch, _FakeSession([[0.1, 0.2, 3.0]]), _FakeTokenizer())

    enc = OnnxCrossEncoder(onnx_dir)

    assert enc.predict([("p", "h")]) == [[0.1, 0.2, 3.0]]
    assert enc.config.id2label["2"] == "entailment"


def test_only_declared_model_inputs_are_fed(monkeypatch, onnx_dir):
    """Distilled exports omit token_type_ids; feeding an undeclared input makes ORT throw."""
    from neuro_core.onnx_rerank import OnnxCrossEncoder
    session = _FakeSession([[1.0]], input_names=("input_ids", "attention_mask"))
    _install_fakes(monkeypatch, session, _FakeTokenizer())

    OnnxCrossEncoder(onnx_dir).predict([("q", "p")])

    assert set(session.feeds) == {"input_ids", "attention_mask"}


def test_empty_pairs_short_circuit(monkeypatch, onnx_dir):
    from neuro_core.onnx_rerank import OnnxCrossEncoder
    session = _FakeSession([[1.0]])
    _install_fakes(monkeypatch, session, _FakeTokenizer())

    assert OnnxCrossEncoder(onnx_dir).predict([]) == []
    assert session.feeds is None


def test_missing_graph_fails_loudly(monkeypatch, tmp_path):
    from neuro_core.onnx_rerank import OnnxCrossEncoder
    _install_fakes(monkeypatch, _FakeSession([[1.0]]), _FakeTokenizer())

    with pytest.raises(FileNotFoundError):
        OnnxCrossEncoder(tmp_path)


def test_reranker_uses_onnx_for_a_directory(monkeypatch, onnx_dir):
    """A directory RERANK_MODEL selects ONNX; sentence_transformers must not be imported."""
    _install_fakes(monkeypatch, _FakeSession([[3.0], [-1.0]]), _FakeTokenizer())
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # import -> ImportError

    scorer = Reranker(str(onnx_dir)).scorer

    assert type(scorer).__name__ == "OnnxCrossEncoder"


def test_reranker_uses_crossencoder_for_a_hub_id(monkeypatch):
    built = {}
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.CrossEncoder = lambda name, device=None: built.setdefault("name", name)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)

    Reranker("BAAI/bge-reranker-base").scorer

    assert built["name"] == "BAAI/bge-reranker-base"


def test_reranker_orders_hits_by_onnx_score(monkeypatch, onnx_dir):
    """End-to-end through Reranker.rerank: the higher-logit hit must come first."""
    _install_fakes(monkeypatch, _FakeSession([[-1.0], [3.0]]), _FakeTokenizer())
    hits = [types.SimpleNamespace(text="weak", score=0.0),
            types.SimpleNamespace(text="strong", score=0.0)]

    out = Reranker(str(onnx_dir)).rerank("q", hits, top_k=2)

    assert [h.text for h in out] == ["strong", "weak"]
    assert out[0].score > out[1].score
