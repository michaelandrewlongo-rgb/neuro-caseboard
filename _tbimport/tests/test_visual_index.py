import numpy as np
import pytest

from engine.visual_index import build_visual_index, VisualIndex
from engine.index import Hit


class FakeVisualEmbedder:
    """Deterministic 2-D image vectors keyed by filename for predictable search."""
    def embed_images(self, paths):
        out = []
        for p in paths:
            out.append([1.0, 0.0] if "rhoton" in str(p).lower() else [0.0, 1.0])
        return np.array(out, dtype="float32")


def _pages():
    return [
        {"book": "Rhoton", "chapter": "Sellar", "page": 531,
         "figure_path": "/x/rhoton_p531.png", "caption": "Figure: cavernous sinus"},
        {"book": "Benzel", "chapter": "Fusion", "page": 20,
         "figure_path": "/x/benzel_p20.png", "caption": "Figure: pedicle screw"},
    ]


@pytest.mark.integration
def test_build_and_image_search(tmp_path):
    emb = FakeVisualEmbedder()
    build_visual_index(_pages(), emb, tmp_path / "idx")
    vidx = VisualIndex(tmp_path / "idx")

    hits = vidx.image_search([1.0, 0.0], k=2)  # closest to the "rhoton" vector
    assert isinstance(hits[0], Hit)
    assert hits[0].book == "Rhoton"
    assert hits[0].page == 531
    assert hits[0].figure_path == "/x/rhoton_p531.png"
    assert hits[0].has_figure is True
    assert "cavernous sinus" in hits[0].caption


@pytest.mark.integration
def test_missing_table_raises(tmp_path):
    with pytest.raises(Exception):
        VisualIndex(tmp_path / "empty")
