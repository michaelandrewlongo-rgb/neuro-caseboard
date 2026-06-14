import numpy as np

from .config import resolve_device


def _l2_normalize(arr):
    arr = np.asarray(arr, dtype="float32")
    if arr.size == 0:
        return arr
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


class OpenClipBackend:
    """Real open_clip backend (BiomedCLIP / SigLIP / OpenCLIP). Not unit-tested;
    validated by the figure gate. Targets open_clip_torch >= 2.24."""

    def __init__(self, model_name, device):
        import open_clip
        import torch
        self.torch = torch
        self.model, self.preprocess = open_clip.create_model_from_pretrained(model_name)
        self.tokenizer = open_clip.get_tokenizer(model_name)
        self.device = device
        self.model.eval().to(device)

    def encode_images(self, paths):
        from PIL import Image
        imgs = [self.preprocess(Image.open(p).convert("RGB")) for p in paths]
        batch = self.torch.stack(imgs).to(self.device)
        with self.torch.no_grad():
            feats = self.model.encode_image(batch)
        return feats.cpu().numpy()

    def encode_text(self, text):
        toks = self.tokenizer([text]).to(self.device)
        with self.torch.no_grad():
            feat = self.model.encode_text(toks)
        return feat.cpu().numpy()[0]


class VisualEmbedder:
    def __init__(self, model_name, device="cpu", backend=None):
        self.model_name = model_name
        self.device = device
        self._backend = backend

    @property
    def backend(self):
        if self._backend is None:
            self._backend = OpenClipBackend(self.model_name, resolve_device(self.device))
        return self._backend

    def embed_images(self, paths):
        paths = list(paths)
        if not paths:
            return np.zeros((0, 0), dtype="float32")
        return _l2_normalize(self.backend.encode_images(paths))

    def embed_query(self, text):
        vec = self.backend.encode_text(text)
        return _l2_normalize(np.asarray([vec], dtype="float32"))[0]
