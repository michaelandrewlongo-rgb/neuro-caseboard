"""Export a cross-encoder checkpoint to ONNX and INT8-quantize it, for CPU/low-RAM deploys.

    python -m neuro_core.scripts.quantize_cross_encoder \
        --model BAAI/bge-reranker-base --out ~/models/bge-reranker-base-onnx-int8

Then point RERANK_MODEL at the output DIRECTORY (a directory selects the ONNX path in rerank.py;
a bare hub id keeps torch). Needs the `onnx-export` extra (optimum, torch) — export-time only, NOT
a runtime dep of the deploy image, which only needs onnxruntime + tokenizers.

Measured on BAAI/bge-reranker-base (WSL2, 320 real corpus pairs vs the fp32 torch CrossEncoder):
weights 1112MB->279MB, peak RSS 1675MB->889MB, 3.3x faster scoring, and ranking agreement of
0.91 mean top-8 overlap / 0.88 Kendall tau — i.e. roughly one passage in eight differs at the
margin. Re-measure agreement if you swap checkpoints; INT8 is not free.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="BAAI/bge-reranker-base", help="hub id or local checkpoint")
    ap.add_argument("--out", required=True, help="output directory for the quantized model")
    args = ap.parse_args(argv)

    from onnxruntime.quantization import QuantType, quantize_dynamic
    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        ORTModelForSequenceClassification.from_pretrained(
            args.model, export=True).save_pretrained(tmp)
        # tokenizer.json + config.json ride along: the runtime loads the tokenizer with the Rust
        # `tokenizers` lib (no torch) and NLIVerifier reads id2label out of the config.
        AutoTokenizer.from_pretrained(args.model).save_pretrained(out)
        shutil.copy(tmp / "config.json", out / "config.json")
        quantize_dynamic(tmp / "model.onnx", out / "model.onnx", weight_type=QuantType.QInt8)
        fp32_mb = (tmp / "model.onnx").stat().st_size / 1e6

    int8_mb = (out / "model.onnx").stat().st_size / 1e6
    if int8_mb < 1:
        raise SystemExit(f"quantized model is {int8_mb:.2f}MB — export failed, refusing to ship it")
    if not (out / "tokenizer.json").exists():
        raise SystemExit(f"{out}/tokenizer.json missing — the runtime cannot tokenize without it")
    print(f"fp32={fp32_mb:.0f}MB -> int8={int8_mb:.0f}MB  ({out})")
    print(f"set RERANK_MODEL={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
