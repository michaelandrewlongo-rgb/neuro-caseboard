"""Offline deterministic tests for the Operative Briefing Bundle PDF renderer (Plan 2).

Pure HTML/SVG builders + the fit ladder are exercised with fakes — no Chromium, no network.
The Chromium-bound orchestrator is tested only for its honest-error path and pure assembly.
"""
import io

import pypdf

from neuro_caseboard.operative_briefing_pdf import count_pdf_pages


def _blank_pdf(n: int) -> bytes:
    w = pypdf.PdfWriter()
    for _ in range(n):
        w.add_blank_page(width=595, height=842)  # A4 points
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_count_pdf_pages_counts_rendered_pages():
    assert count_pdf_pages(_blank_pdf(1)) == 1
    assert count_pdf_pages(_blank_pdf(3)) == 3


# --- Task 2: decision-algorithm SVG -------------------------------------------------
from neuro_caseboard.briefing_model import AlgoEdge, AlgoNode, DecisionAlgorithm
from neuro_caseboard.operative_briefing_pdf import build_algorithm_svg


def _algo():
    return DecisionAlgorithm(
        nodes=[AlgoNode(id="a", label="Ruptured?", kind="decision"),
               AlgoNode(id="b", label="Secure aneurysm", kind="action"),
               AlgoNode(id="c", label="Observe / interval imaging", kind="terminal")],
        edges=[AlgoEdge(src="a", dst="b", condition="yes"),
               AlgoEdge(src="a", dst="c", condition="no")],
    )


def test_algorithm_svg_renders_nodes_and_edges():
    svg = build_algorithm_svg(_algo())
    assert svg.startswith("<svg") and "</svg>" in svg
    assert svg.count("<rect") == 3                      # one box per node
    assert "Ruptured?" in svg and "Secure aneurysm" in svg
    assert "yes" in svg and "no" in svg                 # edge condition labels
    # colors come from a <style> block + classes, NOT var() in presentation attrs
    assert 'fill="var(' not in svg and "<style>" in svg


def test_algorithm_svg_empty_is_blank():
    assert build_algorithm_svg(None) == ""
    assert build_algorithm_svg(DecisionAlgorithm()) == ""


def test_algorithm_svg_drops_dangling_edges():
    algo = DecisionAlgorithm(
        nodes=[AlgoNode(id="a", label="A"), AlgoNode(id="b", label="B")],
        edges=[AlgoEdge(src="a", dst="b"), AlgoEdge(src="a", dst="ZZZ")],  # ZZZ unknown
    )
    svg = build_algorithm_svg(algo)
    # one valid edge drawn; no crash, no phantom node
    assert svg.count("<line") == 1


# --- Task 3: page-1 body, scalable CSS, generic equipment --------------------------
from neuro_caseboard.briefing_model import (
    BriefingItem, BriefingSection, CranialEquipment, EndovascularEquipment,
    OperativeBriefing, SpineEquipment, TreatmentModality)
from neuro_caseboard.operative_briefing_pdf import (
    _page1_body, build_briefing_page_html)


def _briefing(equipment=None):
    return OperativeBriefing(
        title="Basilar tip aneurysm",
        sections=[BriefingSection(key="pathology", title="Pathology", items=[
            BriefingItem(text="Wide-neck basilar apex aneurysm.", priority="critical",
                         source_refs=["T1", "L2"]),
            BriefingItem(text="Incidental low-risk note.", priority="optional",
                         source_refs=["T3"])])],
        modalities=[TreatmentModality(name="Endovascular coiling", preferred=True,
                                      advantages=["less invasive"], limitations=["recurrence"])],
        equipment=equipment,
        algorithm=_algo(),
        unknowns=["Rupture status not stated"],
        disclaimer="Decision support only; the surgeon verifies every recommendation.")


def test_page1_has_no_images_or_citation_markers():
    body = _page1_body(_briefing())
    assert "<img" not in body
    # the hidden source_refs map must not surface as markers or bare tokens on page 1
    assert "[T1]" not in body and "[L2]" not in body and "[T3]" not in body
    assert "T1" not in body and "L2" not in body and "T3" not in body
    assert "Wide-neck basilar apex aneurysm." in body
    assert "<svg" in body                            # decision algorithm is embedded inline


def test_page1_drop_removes_priority_keeps_critical():
    full = _page1_body(_briefing(), drop=())
    trimmed = _page1_body(_briefing(), drop=("optional",))
    assert "Incidental low-risk note." in full
    assert "Incidental low-risk note." not in trimmed
    assert "Wide-neck basilar apex aneurysm." in trimmed   # critical survives


def test_standalone_doc_sets_font_scale_and_theme_tokens():
    doc = build_briefing_page_html(_briefing(), fs=0.85, theme="signal")
    assert doc.startswith("<!doctype html>")
    assert "--fs:0.85" in doc
    assert "--bg:#000000" in doc                      # signal tokens
    print_doc = build_briefing_page_html(_briefing(), theme="print")
    assert "--bg:#ffffff" in print_doc                # print tokens


def test_equipment_renderer_is_subspecialty_specific():
    cranial = _page1_body(_briefing(CranialEquipment(head_fixation=["Mayfield 3-pin"])))
    spine = _page1_body(_briefing(SpineEquipment(cage_class_sizing=["PEEK 12mm lordotic"])))
    endo = _page1_body(_briefing(EndovascularEquipment(catheters_wires=["6F guide; 0.014 wire"])))
    assert "Head Fixation" in cranial and "Mayfield 3-pin" in cranial
    assert "Cage Class Sizing" in spine and "PEEK 12mm lordotic" in spine
    assert "Catheters Wires" in endo and "6F guide; 0.014 wire" in endo
    # negative controls: no cross-subspecialty bleed of equipment labels
    assert "Head Fixation" not in endo and "Cage Class Sizing" not in endo
    assert "Catheters Wires" not in cranial


# --- Task 4: fit ladder (<=2-page guarantee, injected measure/compress) -------------
from neuro_caseboard.operative_briefing_pdf import FitResult, fit_briefing_page


def test_fit_no_change_when_already_one_page():
    r = fit_briefing_page(_briefing(), measure=lambda doc: 1)
    assert isinstance(r, FitResult) and r.pages == 1 and r.fs == 1.0 and r.drop == ()


def test_fit_shrinks_font_before_trimming():
    # 1 page only once fs has dropped to <=0.9; never needs a trim.
    # Anchor on the closing quote so "--fs:0.95" can't match "--fs:0.9" by substring.
    def measure(doc):
        return 1 if ('--fs:0.9"' in doc or '--fs:0.85"' in doc or '--fs:0.82"' in doc) else 2
    r = fit_briefing_page(_briefing(), measure=measure)
    assert r.pages == 1 and r.fs <= 0.9 and r.drop == ()
    assert any(x.startswith("shrink") for x in r.rungs)


def test_fit_trims_optional_then_calls_compress():
    calls = {"n": 0}
    def compress(brief):
        calls["n"] += 1
        return brief                       # identity; we only assert it was invoked
    # never 1 page until compress has run AND optional trimmed
    def measure(doc):
        if calls["n"] >= 1 and "Incidental low-risk note." not in doc:
            return 1
        return 2
    r = fit_briefing_page(_briefing(), measure=measure, compress=compress)
    assert calls["n"] == 1 and r.pages == 1
    assert "Incidental low-risk note." not in r.fragment


def test_fit_allows_page_two_and_always_converges():
    r = fit_briefing_page(_briefing(), measure=lambda doc: 2)  # never fits 1 page
    assert r.pages <= 2                     # the hard invariant
    assert any(x.startswith("page2") for x in r.rungs)


# --- Task 5: figure atlas + references page ----------------------------------------
from neuro_caseboard.briefing_model import BriefingFigure, BriefingReference
from neuro_caseboard.operative_briefing_pdf import (
    build_figure_atlas_html, build_references_html)


def test_atlas_keeps_caption_when_image_unreadable():
    figs = [BriefingFigure(fig_id="BF1", image_path="/no/such/file.png",
                           caption="Circle of Willis", citation="Rhoton 2002", intent="anatomy")]
    html_ = build_figure_atlas_html(figs)
    assert "Circle of Willis" in html_ and "Rhoton 2002" in html_   # caption survives bad path
    assert "BF1" in html_
    assert build_figure_atlas_html([]) == ""


def test_references_keep_T_and_L_namespaces_distinct():
    refs = [
        BriefingReference(ref_id="T1", kind="textbook", citation="Youmans ch. 12, p. 210",
                          sections=["pathology"]),
        BriefingReference(ref_id="L1", kind="pubmed",
                          citation="Smith et al. Stroke 2024", meta={"pmid": "123"},
                          sections=["management"]),
    ]
    out = build_references_html(refs)
    assert "T1" in out and "L1" in out
    # distinct groups: textbook header precedes the literature header
    assert out.index("Textbook") < out.index("Literature")
    assert "Youmans ch. 12, p. 210" in out and "Smith et al. Stroke 2024" in out
    assert "123" in out                                  # pmid surfaced
    assert "pathology" in out and "management" in out    # support map
    assert build_references_html([]) == ""


# --- Task 6: full-doc assembly + orchestrator + compress factory --------------------
import sys

import pytest

from neuro_caseboard.operative_briefing_pdf import (
    _assemble_full_doc, _make_compress, render_operative_briefing_pdf)


def test_assemble_orders_briefing_then_atlas_then_refs():
    doc = _assemble_full_doc("PAGE1", "ATLAS", "REFS", fs=0.9, theme="signal",
                             title="T", topic="x")
    assert doc.startswith("<!doctype html>")
    assert "--fs:0.9" in doc
    assert doc.index("PAGE1") < doc.index("ATLAS") < doc.index("REFS")   # strict ordering
    assert "--bg:#000000" in doc                                         # signal tokens present


def test_make_compress_none_without_client():
    assert _make_compress(None) is None


def test_make_compress_tightens_item_text_via_client():
    class FakeClient:
        model = "fake"
        def generate(self, system, user, images):
            return "Short A\nShort B"          # one tightened line per input item
    brief = OperativeBriefing(title="t", sections=[BriefingSection(
        key="pathology", title="Pathology", items=[
            BriefingItem(text="Long original A ...", priority="critical"),
            BriefingItem(text="Long original B ...", priority="high")])])
    compress = _make_compress(FakeClient())
    out = compress(brief)
    texts = [i.text for s in out.sections for i in s.items]
    assert texts == ["Short A", "Short B"]    # mapped back by order; counts preserved
    # original untouched (compress returns a copy)
    assert brief.sections[0].items[0].text.startswith("Long original A")


def test_render_raises_honest_error_without_chromium(monkeypatch, tmp_path):
    # simulate Playwright import failure -> honest "renderer unavailable"
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    bundle = type("B", (), {"briefing": OperativeBriefing(title="t"),
                            "figures": [], "references": [], "topic": "x"})()
    with pytest.raises(RuntimeError, match="renderer unavailable"):
        render_operative_briefing_pdf(bundle, tmp_path / "out.pdf")
