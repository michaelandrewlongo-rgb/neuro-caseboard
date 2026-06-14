"""The Q&A figure lane filters EVERY source lane (text / visual / caption) at the fusion output:
an off-domain plate must not reach the answer regardless of which lane surfaced it. Real bug: a
spine laminoplasty plate (source book = Vaccaro spine) leaked onto an M1-thrombectomy answer via
the text/visual lane, which a caption-lane-only guard could not catch. Angiographic figures
(captions naming CT/CTA/DSA) must still survive (diagnostic-image guard stays board-only)."""
from neuro_core.query import Engine


class _Cfg:
    max_figure_images = 8
    caption_retrieval = False
    caption_retrieve_k = 8


class _FigHit:
    def __init__(self, book, page, figure_path, caption):
        self.book = book
        self.page = page
        self.figure_path = figure_path
        self.caption = caption
        self.has_figure = True
        self.chapter = ""
        self.score = 1.0


def _engine(monkeypatch):
    eng = Engine(_Cfg(), None, None, None, None)          # caption_index=None, visual_index=None
    monkeypatch.setattr(Engine, "_read_image", lambda self, p: b"img")
    monkeypatch.setattr(Engine, "_visual_hits", lambda self, q: [])
    return eng


def test_collect_figures_drops_offdomain_plate_from_text_visual_lane(monkeypatch):
    eng = _engine(monkeypatch)
    top = [
        _FigHit("Video Atlas of Neuroendovascular Procedures", 150, "/x/p150.png",
                "ADAPT thrombectomy of the right middle cerebral artery M1 occlusion"),
        _FigHit("Spine Surgery Tricks of the Trade Vaccaro", 45, "/x/p45.png",
                "Posterior cervical open-door laminoplasty, bicortical trough, spinal cord, lateral mass"),
    ]
    q = "mechanical thrombectomy for an M1 middle cerebral artery occlusion"
    figs, imgs = eng._collect_figures(q, top)
    paths = [f.image_path for f in figs]
    assert "/x/p150.png" in paths        # on-domain endovascular figure kept
    assert "/x/p45.png" not in paths     # spine plate dropped (book-aware cranial<->spine guard)
    assert len(imgs) == len(figs)


def test_collect_figures_keeps_angiographic_figures(monkeypatch):
    # angio captions name the modality ("computed tomography"); strict must NOT drop them
    eng = _engine(monkeypatch)
    top = [
        _FigHit("Video Atlas of Neuroendovascular Procedures", 309, "/x/p309.png",
                "CT (computed tomography) angiography and DSA of an ICA aneurysm treated with a PED"),
    ]
    q = "flow diverter for an internal carotid artery aneurysm"
    figs, _ = eng._collect_figures(q, top)
    assert [f.image_path for f in figs] == ["/x/p309.png"]
