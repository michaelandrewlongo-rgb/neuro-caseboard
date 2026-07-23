"""INT8/ONNX cross-encoder scorer — a drop-in for ``sentence_transformers.CrossEncoder.predict``.

Why: the deploy box has ~1.8GB RAM free and 2 vCPUs, so the fp32 torch cross-encoder is both the
rerank latency cost and the reason the NLI gate runs ``lexical``. An INT8-quantized ONNX export of
the same checkpoint is ~4x smaller on disk and runs on onnxruntime's CPU kernels instead of torch.

Used automatically when ``RERANK_MODEL`` names a DIRECTORY (an exported model) rather than a hub id;
build one with ``python -m neuro_core.scripts.quantize_cross_encoder``.

Only ``predict(pairs)`` is implemented — that is the whole surface ``rerank.py`` and
``neuro_caseboard.entailment`` use. ``config`` is exposed because NLIVerifier reads ``id2label``.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

# ponytail: fixed 512-token truncation (the checkpoint's own max_position_embeddings); a shorter
# cap would be faster but silently drops the tail of long corpus chunks, changing what gets scored.
MAX_LENGTH = 512


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x > -700 else 0.0


class OnnxCrossEncoder:
    """Scores (query, passage) pairs with an exported ONNX cross-encoder on CPU."""

    def __init__(self, model_dir, *, intra_op_threads: int = 0) -> None:
        import onnxruntime as ort  # lazy: optional deps, only on the ONNX path
        from tokenizers import Tokenizer

        self.model_dir = Path(model_dir)
        model_path = self.model_dir / "model.onnx"
        if not model_path.exists():
            raise FileNotFoundError(f"no model.onnx in {self.model_dir}")

        opts = ort.SessionOptions()
        # 0 = let onnxruntime pick. On the 2-vCPU box, over-threading a batch this small costs more
        # in contention than it saves; override with RERANK_ONNX_THREADS if that turns out wrong.
        if intra_op_threads:
            opts.intra_op_num_threads = intra_op_threads
        self._session = ort.InferenceSession(str(model_path), opts,
                                             providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self._session.get_inputs()}
        # The Rust `tokenizers` lib directly, NOT transformers.AutoTokenizer: importing transformers
        # pulls torch into the process (measured: +1.0GB RSS), which defeats the whole point.
        self._tokenizer = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=MAX_LENGTH)
        self._tokenizer.enable_padding()

        cfg_path = self.model_dir / "config.json"
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        # id2label keys are strings in JSON; NLIVerifier does int(idx) so either works.
        self.config = SimpleNamespace(id2label=cfg.get("id2label"),
                                      num_labels=len(cfg.get("id2label") or {}) or 1)

    def predict(self, pairs):
        """(query, passage) pairs -> scores. 1-logit rerank heads get sigmoid (matching
        CrossEncoder's default activation); multi-class heads return raw logits per class,
        which is what NLIVerifier softmaxes."""
        if not pairs:
            return []
        import numpy as np

        encoded = self._tokenizer.encode_batch([(str(q), str(p)) for q, p in pairs])
        available = {
            "input_ids": lambda e: e.ids,
            "attention_mask": lambda e: e.attention_mask,
            "token_type_ids": lambda e: e.type_ids,
        }
        feeds = {name: np.array([get(e) for e in encoded], dtype=np.int64)
                 for name, get in available.items() if name in self._input_names}
        logits = self._session.run(None, feeds)[0]
        if logits.shape[-1] == 1:
            return [_sigmoid(float(row[0])) for row in logits]
        return [[float(v) for v in row] for row in logits]
