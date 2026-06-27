"""Qwen3-Reranker-0.6B as a drop-in scorer for ``neuro_core.rerank.Reranker``.

Qwen3-Reranker is a causal LM, not a cross-encoder: relevance is the probability of the
``"yes"`` token at the final position given a judge prompt. Exposes the same
``predict(pairs) -> list[float]`` interface the CrossEncoder scorer offers (higher = more
relevant), so ``Reranker`` needs no other change. Model + tokenizer load lazily on first
``predict`` so constructing the scorer (and the routing test) stays cheap.
"""

MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"
TASK = "Given a neurosurgery question, retrieve relevant textbook passages that answer the question"

_PREFIX = (
    "<|im_start|>system\n"
    "Judge whether the Document meets the requirements based on the Query and the Instruct "
    'provided. Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n<|im_start|>user\n"
)
# Pre-fill an empty <think></think> so Qwen3 skips reasoning and emits the yes/no token next.
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_MAX_LENGTH = 8192


class Qwen3Reranker:
    def __init__(self, task=TASK, device=None, batch_size=16):
        self.task = task
        self.device = device
        self.batch_size = batch_size
        self._tok = None
        self._model = None
        self._prefix_ids = None
        self._suffix_ids = None
        self._yes_id = None
        self._no_id = None

    def _load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        dev = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        tok = AutoTokenizer.from_pretrained(MODEL_ID, padding_side="left")
        model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.float16)
        self._tok = tok
        self._model = model.to(dev).eval()
        self._prefix_ids = tok.encode(_PREFIX, add_special_tokens=False)
        self._suffix_ids = tok.encode(_SUFFIX, add_special_tokens=False)
        self._yes_id = tok.convert_tokens_to_ids("yes")
        self._no_id = tok.convert_tokens_to_ids("no")

    def _format(self, query, doc):
        return f"<Instruct>: {self.task}\n<Query>: {query}\n<Document>: {doc}"

    def _score_batch(self, pairs):
        import torch
        import torch.nn.functional as F

        texts = [self._format(q, d) for q, d in pairs]
        budget = _MAX_LENGTH - len(self._prefix_ids) - len(self._suffix_ids)
        enc = self._tok(texts, padding=False, truncation="longest_first",
                        return_attention_mask=False, max_length=budget)
        for i, ids in enumerate(enc["input_ids"]):
            enc["input_ids"][i] = self._prefix_ids + ids + self._suffix_ids
        inputs = self._tok.pad(enc, padding=True, return_tensors="pt", max_length=_MAX_LENGTH)
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = self._model(**inputs).logits[:, -1, :]  # last position
        stacked = torch.stack([logits[:, self._no_id], logits[:, self._yes_id]], dim=1)
        return F.log_softmax(stacked, dim=1)[:, 1].exp().tolist()  # P(yes) in [0, 1]

    def predict(self, pairs):
        """pairs = [(query, doc_text), ...] -> [P(relevant), ...] (higher = more relevant)."""
        if not pairs:
            return []
        self._load()
        scores = []
        for i in range(0, len(pairs), self.batch_size):
            scores.extend(self._score_batch(pairs[i:i + self.batch_size]))
        return scores
