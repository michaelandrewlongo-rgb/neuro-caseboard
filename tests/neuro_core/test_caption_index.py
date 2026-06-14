from types import SimpleNamespace

from engine.caption_index import rank_captions
from engine.index import Hit
from engine.query import Engine


def _rows():
    return [
        {"figure_path": "/a", "book": "Rhoton", "chapter": None, "page": 1,
         "caption": "MCA middle cerebral artery M1 bifurcation with lenticulostriate perforators"},
        {"figure_path": "/b", "book": "Spine", "chapter": None, "page": 2,
         "caption": "Lumbar pedicle screw entry point and trajectory"},
        {"figure_path": "/c", "book": "Rhoton", "chapter": None, "page": 3,
         "caption": "Superior sagittal sinus and the dural venous drainage"},
    ]


def test_rank_captions_prefers_the_caption_that_names_the_anatomy():
    ranked = rank_captions(_rows(), "MCA bifurcation of the middle cerebral artery", k=5)
    assert ranked and ranked[0][1]["figure_path"] == "/a"
    paths = [r["figure_path"] for _s, r in ranked]
    assert "/b" not in paths and "/c" not in paths   # no >=2-term overlap -> excluded


def test_rank_captions_requires_two_matches():
    # "artery" alone is a single shared term with /a -> below the >=2 threshold
    assert rank_captions(_rows(), "artery", k=5) == []


def test_collect_figures_uses_caption_lane_and_shows_gemini_caption(tmp_path):
    png = tmp_path / "p1.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n fake-bytes")
    gem = "MCA (middle cerebral artery) M1 bifurcation with lenticulostriate perforators"

    class FakeCaptionIndex:
        caption_by_path = {str(png): gem}

        def caption_search(self, q, k):
            return [Hit(id="cap", book="Rhoton", chapter=None, page=82, text=gem,
                        score=9.0, has_figure=True, caption=gem, figure_path=str(png))]

    cfg = SimpleNamespace(visual_retrieval=False, caption_retrieval=True,
                          caption_retrieve_k=10, max_figure_images=5)
    eng = Engine(cfg, embedder=None, index=None, reranker=None, synth_client=None,
                 caption_index=FakeCaptionIndex())
    # no text hits and the visual lane off: the caption lane alone must surface the figure
    figs, imgs = eng._collect_figures("MCA bifurcation middle cerebral artery", top=[])
    assert len(figs) == 1 and figs[0].image_path == str(png)
    assert "middle cerebral" in figs[0].caption.lower()   # the Gemini caption is displayed
    assert len(imgs) == 1
