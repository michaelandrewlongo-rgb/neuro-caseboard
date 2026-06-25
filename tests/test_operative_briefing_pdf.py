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
