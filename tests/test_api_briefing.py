from fastapi.testclient import TestClient

import api.server as server
from neuro_caseboard.pipeline import build_briefing_bundle


class FakeSynth:
    def generate(self, system, user, images):
        from neuro_caseboard import briefing_synth as bs
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        if key == "equipment":
            return "positioning_monitoring: prone; SSEP\nrefs: T1\n"
        if key == "modalities":
            return "### ACDF\nrole: decompress\npreferred: yes\nrefs: T1\n"
        return f"[critical] {key} claim {{T1}}\n"


class TRec:
    def __init__(self, n):
        self.id = f"rec-{n}"
        self.title = f"Youmans chapter {n}"
        self.source = "corpus"
        self.text = f"passage {n}"
        self.metadata = {"citation": f"Youmans p.{n}", "book": "Youmans", "page": n}


class TextRetriever:
    def retrieve(self, query, top_n=6, **kwargs):
        return [TRec(1)]


def _bundle():
    return build_briefing_bundle("C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
                                 fig_retriever=None, synth_client=FakeSynth(), literature=False)


def test_briefing_response_augments_figures_and_injects_build_id():
    b = _bundle()
    # give one figure a path so the augmentation has something to resolve
    from neuro_caseboard.briefing_model import BriefingFigure
    b.figures = [BriefingFigure(fig_id="BF1", image_path="/no/such.png", caption="x")]
    resp = server._briefing_response(b, "abc123")
    assert resp["kind"] == "briefing" and resp["build_id"] == "abc123"
    fig = resp["figures"][0]
    assert "image_url" in fig and "image_available" in fig
    assert fig["image_url"].startswith("/api/figure?path=")     # browser-loadable URL
    assert fig["image_available"] is False                      # bogus path -> not served
    assert "image_path" in fig                                  # original kept (PDF renderer reads it)


def test_briefing_cache_is_lru_bounded():
    server._BRIEFING_CACHE.clear()
    for i in range(server._BRIEFING_CACHE_MAX + 3):
        server._cache_briefing(f"topic {i}", True, True, True, object())
    assert len(server._BRIEFING_CACHE) == server._BRIEFING_CACHE_MAX


def test_post_briefing_returns_serialized_bundle(monkeypatch):
    b = _bundle()
    monkeypatch.setattr(server, "_do_build_briefing", lambda *a, **k: b)
    client = TestClient(server.app)
    r = client.post("/api/briefing", json={"topic": "C5-6 ACDF", "use_prefs": False})
    assert r.status_code == 200
    data = r.json()
    assert data["kind"] == "briefing" and data["build_id"]
    assert data["briefing"]["sections"]                          # real briefing rode through
    assert data["build_id"] in server._BRIEFING_CACHE            # cached for the PDF endpoint


def test_post_briefing_empty_topic_is_422():
    client = TestClient(server.app)
    r = client.post("/api/briefing", json={"topic": "  "})
    assert r.status_code == 422 and r.json()["kind"] == "error"


def test_briefing_pdf_requires_cached_build_id():
    client = TestClient(server.app)
    r = client.post("/api/briefing/pdf", json={"build_id": "does-not-exist"})
    assert r.status_code == 404
    assert "build" in r.json()["error"].lower()                 # honest "no cached build" message


def test_briefing_pdf_serves_cached_bundle(monkeypatch, tmp_path):
    b = _bundle()
    build_id = server._cache_briefing("C5-6 ACDF", True, True, True, b)
    seen = {}

    def fake_render(bundle, out_path, *, synth_client=None):
        seen["bundle"] = bundle
        from pathlib import Path
        Path(out_path).write_bytes(b"%PDF-1.4 fake")
        return str(out_path)

    monkeypatch.setattr("neuro_caseboard.operative_briefing_pdf.render_operative_briefing_pdf",
                        fake_render)
    client = TestClient(server.app)
    r = client.post("/api/briefing/pdf", json={"build_id": build_id})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert seen["bundle"] is b                                  # the CACHED object, not a rebuild


def test_briefing_pdf_renderer_unavailable_is_503(monkeypatch):
    b = _bundle()
    build_id = server._cache_briefing("C5-6 ACDF", True, True, True, b)

    def boom(bundle, out_path, *, synth_client=None):
        raise RuntimeError("renderer unavailable: needs the briefing extra")

    monkeypatch.setattr("neuro_caseboard.operative_briefing_pdf.render_operative_briefing_pdf", boom)
    client = TestClient(server.app)
    r = client.post("/api/briefing/pdf", json={"build_id": build_id})
    assert r.status_code == 503
    assert "renderer unavailable" in r.json()["error"]
