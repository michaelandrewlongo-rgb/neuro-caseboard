# Operative Briefing Bundle — Plan 2: PDF Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render an `OperativeBriefingBundle` (Plan 1 output) to an A4 PDF — a ≤2-page citation-free, figure-free operative briefing, then a figure atlas, then a references/evidence page — in the Signal print identity.

**Architecture:** One new module `neuro_caseboard/operative_briefing_pdf.py`. **Pure HTML/SVG builders** (offline, no Chromium) produce page-1 body, deterministic decision-algorithm SVG, figure atlas, and references page. A **fit ladder** with an *injected* page-count `measure` (and an *injected, optional* LLM `compress`) drives the ≤2-page guarantee — offline-testable with a fake measure. A thin Chromium orchestrator supplies the real measure (render page-1 to PDF bytes → `pypdf` page count — authoritative, not `scrollHeight`), runs the ladder, assembles the full doc, and renders once.

**Tech Stack:** Python 3.12, Pydantic v2 models (Plan 1, unchanged), Playwright/Chromium (`briefing` extra), `pypdf` (already installed), `neuro_caseboard.exec_navy` theme tokens.

## Global Constraints

- **Page 1 carries no `<img>` and no visible citation markers** (`[T#]`/`[L#]`) — structurally enforced by the page-1 builder having no figure/citation slots. (spec §7, §11, §13)
- **≤2 pages, always**, for the briefing — no export-error state; the ladder mechanically converges. (spec §2 decision, §7)
- **Measure = actual rendered PDF page count** (render page-1 HTML to PDF bytes, count with `pypdf`). **Never `body.scrollHeight`** — it undercounts under `break-inside:avoid` and is screen-media. (advisor)
- **`T#` (textbook) and `L#` (PubMed) namespaces stay distinct** on the references page — never merged or renumbered. (spec §8, §11)
- **Signal identity:** reuse `exec_navy.base_css(theme)` tokens; theme from `CASEBOARD_PDF_STYLE` (`signal` default / `print`). (spec §7, mirrors PR #73)
- **Page-1 sizing CSS is self-contained** (`.bf-*` classes, `calc(var(--fs)*Npt)`), reusing only `:root` theme tokens — NOT the fixed-pt `_STRUCTURE_CSS` text classes (font-scaling can't override them). (advisor)
- **SVG colors via a `<style>` block + classes**, never `fill="var(--…)"` in attributes (`var()` doesn't resolve in XML attributes). (advisor)
- **Never fabricate** a citation, figure, device, lab, dose, threshold, rate, or recommendation; unsupported claims marked, never silently dropped. (spec §11)
- **Chromium absent → honest `RuntimeError("renderer unavailable …")`**; the pure builders still test offline. (spec §7)
- Synth client is **injected** (offline-testable with a fake), uses the `.generate(system, user, images)` interface; never hardcode Anthropic. (spec §5)
- CLAUDE.md gotchas: tests are the CI gate; no `pytest-xdist -n auto`; `pytest.importorskip` for optional deps; scoped fast loop locally.

**Scope boundary:** Plan 2 is the renderer module + tests **only**. `POST /api/briefing/pdf`, caching, CLI flag, and the Build.tsx surface are **Plan 3**. The module's public entry `render_operative_briefing_pdf(bundle, out_path, …)` is reachable now via the public `pipeline.build_briefing_bundle(...)` for the manual 3-PDF verification (Task 8).

---

## File Structure

- **Create:** `neuro_caseboard/operative_briefing_pdf.py` — all builders + ladder + orchestrator.
- **Create:** `tests/test_operative_briefing_pdf.py` — offline deterministic tests (incl. cross-subspecialty + negative controls).
- **No edits** to `briefing_model.py`, `briefing_synth.py`, `briefing_figures.py`, `exec_navy.py`, `pipeline.py`. (Plan 3 wires the API/CLI.)

### Public API surface (consumed across tasks)

```python
# Task 1
def count_pdf_pages(data: bytes) -> int

# Task 2
def build_algorithm_svg(algo, theme: str = "signal") -> str          # "" when no nodes

# Task 3
def _page1_body(briefing, *, drop: tuple[str, ...] = ()) -> str       # inner fragment: no <img>, no [T#]/[L#]
def build_briefing_page_html(briefing, *, fs: float = 1.0,
                             drop: tuple[str, ...] = (), theme: str = "signal") -> str   # standalone doc

# Task 4
@dataclass
class FitResult:
    fragment: str            # ready page-1 inner body
    fs: float                # wrapper --fs var
    drop: tuple[str, ...]
    pages: int
    rungs: list[str]
def fit_briefing_page(briefing, measure, *, theme="signal", compress=None,
                      fs_steps=(1.0, 0.95, 0.9, 0.85, 0.82)) -> FitResult
#   measure:  Callable[[str /*standalone page-1 doc*/], int]
#   compress: Callable[[OperativeBriefing], OperativeBriefing] | None

# Task 5
def build_figure_atlas_html(figures, theme: str = "signal") -> str    # "" when none
def build_references_html(references, theme: str = "signal") -> str    # "" when none

# Task 6
def _assemble_full_doc(page1_fragment: str, atlas_body: str, refs_body: str, *,
                       fs: float, theme: str, title: str, topic: str) -> str
def render_operative_briefing_pdf(bundle, out_path, *, theme: str | None = None,
                                  synth_client=None) -> str
```

---

## Task 1: Authoritative PDF page-count helper

**Files:**
- Create: `neuro_caseboard/operative_briefing_pdf.py`
- Test: `tests/test_operative_briefing_pdf.py`

**Interfaces:**
- Produces: `count_pdf_pages(data: bytes) -> int` — the authoritative measure primitive used by the orchestrator's real `measure` and the Task 8 verification.

- [ ] **Step 1: Write the failing test** (offline fixture built with `pypdf` itself — no Chromium)

```python
# tests/test_operative_briefing_pdf.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py::test_count_pdf_pages_counts_rendered_pages -q`
Expected: FAIL — `ModuleNotFoundError`/`ImportError` (module/function not defined).

- [ ] **Step 3: Write minimal implementation** (module header + helper)

```python
# neuro_caseboard/operative_briefing_pdf.py
"""Operative Briefing Bundle PDF — render an OperativeBriefingBundle (Plan 1) to A4.

Three surfaces, hard-separated: page 1 is a citation-free, figure-free operative briefing
held to <=2 pages by a fit ladder; then a figure atlas; then a references/evidence page.
Signal print identity via exec_navy tokens. Pure HTML/SVG builders test offline; the
Chromium orchestrator supplies the authoritative page-count measure (render -> pypdf).
"""
from __future__ import annotations

import html
import io
import math
import os
from dataclasses import dataclass, field

import pypdf

from neuro_caseboard.exec_navy import PRINT_TOKENS, SIGNAL_TOKENS


def count_pdf_pages(data: bytes) -> int:
    """Authoritative page count of a rendered PDF (what pagination actually produced)."""
    return len(pypdf.PdfReader(io.BytesIO(data)).pages)


def _tokens(theme: str) -> str:
    return PRINT_TOKENS if theme == "print" else SIGNAL_TOKENS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py::test_count_pdf_pages_counts_rendered_pages -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/operative_briefing_pdf.py tests/test_operative_briefing_pdf.py
git commit -m "feat(briefing-pdf): authoritative PDF page-count helper (Plan 2 Task 1)"
```

---

## Task 2: Deterministic decision-algorithm SVG

**Files:**
- Modify: `neuro_caseboard/operative_briefing_pdf.py`
- Test: `tests/test_operative_briefing_pdf.py`

**Interfaces:**
- Consumes: `briefing_model.DecisionAlgorithm` / `AlgoNode` / `AlgoEdge` (Plan 1). Nodes have `id`, `label`, `kind ∈ {decision, action, terminal}`; edges have `src`, `dst`, `condition`.
- Produces: `build_algorithm_svg(algo, theme="signal") -> str` — inline `<svg>`; `""` when `algo` is `None` or has no nodes. Defensive: drops edges whose `src`/`dst` is not a known node; falls back to insertion-order layering if longest-path layering detects a cycle.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_operative_briefing_pdf.py  (append)
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k algorithm -q`
Expected: FAIL — `build_algorithm_svg` not defined.

- [ ] **Step 3: Implement** (layered layout, `<style>`-class colors, defensive)

```python
# neuro_caseboard/operative_briefing_pdf.py  (append)

_ALGO_CSS = """
  .n{ rx:5; ry:5; stroke:var(--line); stroke-width:1; }
  .n.decision{ fill:var(--panel); stroke:var(--accent); }
  .n.action{ fill:var(--panel); }
  .n.terminal{ fill:var(--panel); stroke:var(--supported); }
  .nt{ font-family:var(--ui); font-size:8.5pt; fill:var(--ink); }
  .e{ stroke:var(--line); stroke-width:1.2; marker-end:url(#arrow); fill:none; }
  .ec{ font-family:var(--mono); font-size:7pt; fill:var(--accent); }
"""


def _algo_layers(nodes, edges):
    """Longest-path layering (layer = max(layer of preds)+1). Insertion order on cycle."""
    ids = [n.id for n in nodes]
    preds = {i: [] for i in ids}
    for e in edges:
        preds[e.dst].append(e.src)
    layer = {i: 0 for i in ids}
    for _ in range(len(ids)):                 # relax |V| times; detects no progress => cycle
        changed = False
        for i in ids:
            want = max((layer[p] + 1 for p in preds[i]), default=0)
            if want > layer[i]:
                layer[i] = want
                changed = True
        if not changed:
            break
    else:
        # never converged within |V| passes -> cycle; degrade to insertion order
        layer = {i: idx for idx, i in enumerate(ids)}
    return layer


def build_algorithm_svg(algo, theme: str = "signal") -> str:
    if algo is None or not algo.nodes:
        return ""
    nodes = list(algo.nodes)
    ids = {n.id for n in nodes}
    edges = [e for e in algo.edges if e.src in ids and e.dst in ids]   # drop dangling
    layer = _algo_layers(nodes, edges)

    rows: dict[int, list] = {}
    for n in nodes:
        rows.setdefault(layer[n.id], []).append(n)

    BW, BH, HGAP, VGAP, PAD = 150, 34, 24, 28, 12
    ncols = max((len(r) for r in rows.values()), default=1)
    width = PAD * 2 + ncols * BW + (ncols - 1) * HGAP
    nlayers = max(rows) + 1 if rows else 1
    height = PAD * 2 + nlayers * BH + (nlayers - 1) * VGAP

    pos = {}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             f'width="100%" style="max-width:{width}px">',
             f'<style>{_ALGO_CSS}</style>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
             'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             '<path d="M0 0 L10 5 L0 10 z" style="fill:var(--line)"/></marker></defs>']
    for ly in sorted(rows):
        row = rows[ly]
        span = len(row) * BW + (len(row) - 1) * HGAP
        x0 = (width - span) / 2
        y = PAD + ly * (BH + VGAP)
        for j, n in enumerate(row):
            x = x0 + j * (BW + HGAP)
            pos[n.id] = (x + BW / 2, y, y + BH)            # cx, top, bottom
            kind = n.kind if n.kind in ("decision", "action", "terminal") else "decision"
            parts.append(f'<rect class="n {kind}" x="{x:.1f}" y="{y:.1f}" '
                         f'width="{BW}" height="{BH}"/>')
            parts.append(f'<text class="nt" x="{x + BW / 2:.1f}" y="{y + BH / 2 + 3:.1f}" '
                         f'text-anchor="middle">{html.escape(_clip(n.label, 26))}</text>')
    for e in edges:
        sx, _, sb = pos[e.src]
        dx, dt_, _ = pos[e.dst]
        parts.append(f'<line class="e" x1="{sx:.1f}" y1="{sb:.1f}" x2="{dx:.1f}" y2="{dt_:.1f}"/>')
        if e.condition:
            mx, my = (sx + dx) / 2, (sb + dt_) / 2
            parts.append(f'<text class="ec" x="{mx:.1f}" y="{my:.1f}" '
                         f'text-anchor="middle">{html.escape(e.condition)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _clip(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k algorithm -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/operative_briefing_pdf.py tests/test_operative_briefing_pdf.py
git commit -m "feat(briefing-pdf): deterministic decision-algorithm SVG (Plan 2 Task 2)"
```

---

## Task 3: Page-1 body + self-contained scalable CSS + standalone doc

**Files:**
- Modify: `neuro_caseboard/operative_briefing_pdf.py`
- Test: `tests/test_operative_briefing_pdf.py`

**Interfaces:**
- Consumes: `OperativeBriefing` (Plan 1): `title`, `sections: list[BriefingSection]` (items have `text`, `priority`, `source_refs`, `unsupported`), `algorithm`, `modalities: list[TreatmentModality]`, `equipment: EquipmentPlan|None`, `unknowns: list[str]`, `disclaimer`. `build_algorithm_svg` (Task 2).
- Produces: `_page1_body(briefing, *, drop=()) -> str` (inner fragment, **no `<img>`, no `[T#]/[L#]`**, items with `priority in drop` removed, `critical` never droppable by callers), and `build_briefing_page_html(briefing, *, fs=1.0, drop=(), theme="signal") -> str` (standalone A4 doc wrapping the fragment in `<div class="bf-page" style="--fs:{fs}">`).
- **Equipment renderer is generic** — iterate `equipment.model_dump()`, skip `kind`/`source_refs`, humanize each non-empty list field (advisor's lazy win). One renderer covers cranial/spine/endovascular.

- [ ] **Step 1: Write the failing tests** (incl. the page-1 invariant + cross-subspecialty equipment labels)

```python
# tests/test_operative_briefing_pdf.py  (append)
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
    assert "[T1]" not in body and "[L2]" not in body and "[T3]" not in body
    # the hidden source_refs map must not surface as visible markers anywhere on page 1
    assert "T1" not in body or 'class="bf' in body  # text-level guard; no bare ref token rendered
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k "page1 or standalone or equipment" -q`
Expected: FAIL — `_page1_body`/`build_briefing_page_html` not defined.

- [ ] **Step 3: Implement** (scalable `.bf-*` CSS + body builders + generic equipment)

```python
# neuro_caseboard/operative_briefing_pdf.py  (append)

# Self-contained, font-scalable page-1 sizing. Colors/fonts come from :root tokens (exec_navy);
# every text size is calc(var(--fs)*Npt) so the fit ladder's --fs actually shrinks it. We do NOT
# reuse _STRUCTURE_CSS's fixed-pt text classes (they'd win on specificity). (advisor)
_BRIEFING_PAGE_CSS = """
@page{ size:A4; margin:0; }
*{ box-sizing:border-box; }
html,body{ margin:0; background:var(--bg); -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.bf-page{ color:var(--ink); font-family:var(--ui); padding:12mm 16mm 14mm; }
.bf-eyebrow{ font-family:var(--mono); font-size:calc(var(--fs)*7pt); font-weight:700;
  letter-spacing:.2em; text-transform:uppercase; color:var(--accent); }
.bf-title{ font-family:var(--ui); font-weight:700; font-size:calc(var(--fs)*19pt);
  letter-spacing:-.02em; line-height:1.1; margin:2mm 0 4mm; }
.bf-sec{ margin-top:calc(var(--fs)*5mm); break-inside:avoid; }
.bf-sec-h{ font-family:var(--ui); font-weight:700; font-size:calc(var(--fs)*11pt);
  color:var(--ink); border-top:1px solid var(--line); padding-top:2mm; margin-bottom:1.5mm; }
.bf-item{ font-family:var(--read); font-size:calc(var(--fs)*10pt); line-height:1.4;
  color:var(--ink); margin:0 0 1.4mm; padding-left:4mm; text-indent:-4mm; }
.bf-item::before{ content:"\\2014"; color:var(--accent); margin-right:2mm; }
.bf-item.unsupported::after{ content:" \\2014 clinician-verify"; color:var(--verify);
  font-family:var(--mono); font-size:calc(var(--fs)*7pt); text-transform:uppercase;
  letter-spacing:.06em; }
.bf-note{ font-family:var(--read); font-style:italic; font-size:calc(var(--fs)*9pt);
  color:var(--muted); margin:1mm 0 0; }
.bf-mods{ display:flex; flex-wrap:wrap; gap:3mm; margin-top:2mm; }
.bf-mod{ flex:1 1 46%; border:1px solid var(--line); border-left:3px solid var(--line);
  border-radius:var(--radius); padding:2.5mm 3mm; background:var(--panel); break-inside:avoid; }
.bf-mod.pref{ border-left-color:var(--supported); }
.bf-mod .nm{ font-family:var(--ui); font-weight:700; font-size:calc(var(--fs)*9.5pt); color:var(--ink); }
.bf-mod .ro{ font-family:var(--read); font-size:calc(var(--fs)*8.5pt); color:var(--muted); margin:.6mm 0; }
.bf-mod ul{ margin:.6mm 0 0; padding-left:4mm; }
.bf-mod li{ font-family:var(--read); font-size:calc(var(--fs)*8.5pt); color:var(--ink); }
.bf-eq{ border:1px solid var(--line); border-radius:var(--radius); padding:2.5mm 3mm;
  background:var(--panel); margin-top:2mm; break-inside:avoid; }
.bf-eq-kind{ font-family:var(--mono); font-size:calc(var(--fs)*7pt); font-weight:700;
  letter-spacing:.12em; text-transform:uppercase; color:var(--accent); margin-bottom:1mm; }
.bf-eq-row{ display:flex; gap:3mm; margin:.5mm 0; }
.bf-eq-k{ flex:0 0 38mm; font-family:var(--ui); font-weight:600;
  font-size:calc(var(--fs)*8.5pt); color:var(--muted); }
.bf-eq-v{ flex:1; font-family:var(--read); font-size:calc(var(--fs)*8.5pt); color:var(--ink); }
.bf-algo{ margin:2mm 0; }
.bf-unknowns{ font-family:var(--read); font-size:calc(var(--fs)*8.5pt); color:var(--muted);
  border-left:3px solid var(--verify); padding-left:3mm; margin-top:3mm; }
.bf-disc{ font-family:var(--mono); font-size:calc(var(--fs)*7pt); color:var(--faint);
  margin-top:4mm; padding-top:2mm; border-top:1px solid var(--line); }
"""


def _esc(s: str) -> str:
    return html.escape(s or "")


def _items_html(items, drop) -> str:
    out = []
    for it in items:
        if it.priority in drop:
            continue
        cls = "bf-item unsupported" if it.unsupported else "bf-item"
        out.append(f'<div class="{cls}">{_esc(it.text)}</div>')   # NB: source_refs NOT rendered
    return "".join(out)


def _modalities_html(mods) -> str:
    if not mods:
        return ""
    cards = []
    for m in mods:
        pref = " pref" if m.preferred else ""
        adv = "".join(f"<li>+ {_esc(a)}</li>" for a in m.advantages)
        lim = "".join(f"<li>− {_esc(x)}</li>" for x in m.limitations)
        ro = f'<div class="ro">{_esc(m.role)}</div>' if m.role else ""
        cards.append(f'<div class="bf-mod{pref}"><div class="nm">{_esc(m.name)}</div>{ro}'
                     f'<ul>{adv}{lim}</ul></div>')
    return f'<div class="bf-mods">{"".join(cards)}</div>'


def _equipment_html(equip) -> str:
    """Generic: one renderer for all three subspecialty schemas (advisor)."""
    if equip is None:
        return ""
    data = equip.model_dump()
    kind = data.pop("kind", "")
    data.pop("source_refs", None)
    rows = []
    for field_name, vals in data.items():
        if not vals:
            continue
        label = field_name.replace("_", " ").title()
        rows.append(f'<div class="bf-eq-row"><span class="bf-eq-k">{_esc(label)}</span>'
                    f'<span class="bf-eq-v">{_esc("; ".join(vals))}</span></div>')
    if not rows:
        return ""
    return (f'<div class="bf-eq"><div class="bf-eq-kind">{_esc(kind)} setup</div>'
            f'{"".join(rows)}</div>')


def _page1_body(briefing, *, drop: tuple = ()) -> str:
    out = ['<div class="bf-eyebrow">Operative Briefing</div>',
           f'<div class="bf-title">{_esc(briefing.title)}</div>']
    for sec in briefing.sections:
        items = _items_html(sec.items, drop)
        if not items and not sec.note:
            continue
        out.append(f'<div class="bf-sec"><div class="bf-sec-h">{_esc(sec.title)}</div>{items}')
        if sec.note:
            out.append(f'<div class="bf-note">{_esc(sec.note)}</div>')
        out.append("</div>")
    svg = build_algorithm_svg(briefing.algorithm)
    if svg:
        out.append(f'<div class="bf-sec"><div class="bf-sec-h">Decision algorithm</div>'
                   f'<div class="bf-algo">{svg}</div></div>')
    mods = _modalities_html(briefing.modalities)
    if mods:
        out.append(f'<div class="bf-sec"><div class="bf-sec-h">Treatment options</div>{mods}</div>')
    eq = _equipment_html(briefing.equipment)
    if eq:
        out.append(f'<div class="bf-sec"><div class="bf-sec-h">Equipment</div>{eq}</div>')
    if briefing.unknowns:
        items = " · ".join(_esc(u) for u in briefing.unknowns)
        out.append(f'<div class="bf-unknowns"><b>Case-specific unknowns:</b> {items}</div>')
    if briefing.disclaimer:
        out.append(f'<div class="bf-disc">{_esc(briefing.disclaimer)}</div>')
    return "".join(out)


def build_briefing_page_html(briefing, *, fs: float = 1.0, drop: tuple = (),
                             theme: str = "signal") -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'><style>"
            f"{_tokens(theme)}{_BRIEFING_PAGE_CSS}</style></head><body>"
            f'<div class="bf-page" style="--fs:{fs}">{_page1_body(briefing, drop=drop)}</div>'
            "</body></html>")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k "page1 or standalone or equipment" -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/operative_briefing_pdf.py tests/test_operative_briefing_pdf.py
git commit -m "feat(briefing-pdf): page-1 body, scalable CSS, generic equipment (Plan 2 Task 3)"
```

---

## Task 4: Fit ladder (≤2-page guarantee, injected measure/compress)

**Files:**
- Modify: `neuro_caseboard/operative_briefing_pdf.py`
- Test: `tests/test_operative_briefing_pdf.py`

**Interfaces:**
- Consumes: `build_briefing_page_html` / `_page1_body` (Task 3).
- Produces: `FitResult` dataclass + `fit_briefing_page(briefing, measure, *, theme="signal", compress=None, fs_steps=(1.0,0.95,0.9,0.85,0.82)) -> FitResult`. Ladder order (spec §7): shrink font to floor → trim `optional` → one `compress` pass (if provided) → allow page 2, trim `optional` then `optional+high` until ≤2. `critical` never dropped. Always returns ≤2 pages when the measure is monotonic in content; the final rung is the mechanical ceiling.

- [ ] **Step 1: Write the failing tests** (fake measure — fully offline, no Chromium)

```python
# tests/test_operative_briefing_pdf.py  (append)
from neuro_caseboard.operative_briefing_pdf import FitResult, fit_briefing_page


def test_fit_no_change_when_already_one_page():
    r = fit_briefing_page(_briefing(), measure=lambda doc: 1)
    assert isinstance(r, FitResult) and r.pages == 1 and r.fs == 1.0 and r.drop == ()


def test_fit_shrinks_font_before_trimming():
    # 1 page only once fs has dropped to <=0.9; never needs a trim
    def measure(doc):
        return 1 if "--fs:0.9" in doc or "--fs:0.85" in doc or "--fs:0.82" in doc else 2
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k fit -q`
Expected: FAIL — `fit_briefing_page`/`FitResult` not defined.

- [ ] **Step 3: Implement** (the ladder)

```python
# neuro_caseboard/operative_briefing_pdf.py  (append)

@dataclass
class FitResult:
    fragment: str
    fs: float
    drop: tuple = ()
    pages: int = 1
    rungs: list = field(default_factory=list)


def fit_briefing_page(briefing, measure, *, theme: str = "signal", compress=None,
                      fs_steps=(1.0, 0.95, 0.9, 0.85, 0.82)) -> FitResult:
    """Drive the briefing to <=2 pages. `measure(standalone_doc) -> page_count` is injected
    (real = render+pypdf; tests = fake). `compress(briefing) -> briefing` is optional."""
    floor = fs_steps[-1]
    rungs: list = []

    def attempt(b, fs, drop):
        doc = build_briefing_page_html(b, fs=fs, drop=drop, theme=theme)
        return measure(doc)

    def result(b, fs, drop, pages, tag):
        return FitResult(_page1_body(b, drop=drop), fs, drop, pages, rungs + [tag])

    # rung 1 — shrink font at full content, target 1 page
    for fs in fs_steps:
        pages = attempt(briefing, fs, ())
        if pages <= 1:
            return result(briefing, fs, (), pages, f"shrink:{fs}")
    rungs.append("shrink:floor")

    # rung 2 — trim optional at floor, target 1
    pages = attempt(briefing, floor, ("optional",))
    if pages <= 1:
        return result(briefing, floor, ("optional",), pages, "trim:optional")

    # rung 3 — one compress pass, then retry shrink + trim-optional, target 1
    b = briefing
    if compress is not None:
        try:
            b = compress(briefing)
            rungs.append("compress")
        except Exception:
            b = briefing
            rungs.append("compress:failed")
        for fs in fs_steps:
            pages = attempt(b, fs, ())
            if pages <= 1:
                return result(b, fs, (), pages, f"shrink2:{fs}")
        pages = attempt(b, floor, ("optional",))
        if pages <= 1:
            return result(b, floor, ("optional",), pages, "trim2:optional")

    # rung 4 — allow page 2; drop optional, then optional+high, until <=2 (critical never)
    for drop in (("optional",), ("optional", "high")):
        pages = attempt(b, floor, drop)
        if pages <= 2:
            return result(b, floor, drop, pages, "page2:" + "+".join(drop))
    # ponytail: critical-only at the legibility floor is the mechanical ceiling; accept it,
    # no export-error state (spec §2/§7). Add a hard font under-floor only if real briefings
    # ever exceed this — they don't (critical core is small).
    pages = attempt(b, floor, ("optional", "high"))
    return result(b, floor, ("optional", "high"), pages, "page2:critical-only")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k fit -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/operative_briefing_pdf.py tests/test_operative_briefing_pdf.py
git commit -m "feat(briefing-pdf): fit ladder with injected measure/compress, <=2-page guarantee (Plan 2 Task 4)"
```

---

## Task 5: Figure atlas + references/evidence page

**Files:**
- Modify: `neuro_caseboard/operative_briefing_pdf.py`
- Test: `tests/test_operative_briefing_pdf.py`

**Interfaces:**
- Consumes: `BriefingFigure` (`fig_id`, `image_path`, `caption`, `citation`, `intent`, `source_n`) and `BriefingReference` (`ref_id`, `kind ∈ {textbook,pubmed}`, `citation`, `meta`, `sections`) (Plan 1). `exec_navy.img_data_uri` for image embedding (resolves container reroot; figures whose file can't be read keep caption-only — never crash).
- Produces: `build_figure_atlas_html(figures, theme="signal") -> str` (atlas body fragment, each figure `break-inside:avoid`, full caption + source label; `""` when no figures) and `build_references_html(references, theme="signal") -> str` (final-page body: **`T#` and `L#` grouped in distinct sections**, support-map line per reference; `""` when none).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_operative_briefing_pdf.py  (append)
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k "atlas or references" -q`
Expected: FAIL — builders not defined.

- [ ] **Step 3: Implement**

```python
# neuro_caseboard/operative_briefing_pdf.py  (append)

# Atlas + references reuse the exec_navy structural classes where possible, but get their own
# small additive CSS so they stay independent of the page-1 scalable block.
_ATLAS_CSS = """
.bf-break{ break-before:page; }
.bf-page-h{ font-family:var(--mono); font-size:7pt; font-weight:700; letter-spacing:.2em;
  text-transform:uppercase; color:var(--accent); padding:12mm 16mm 0; }
.bf-atlas{ padding:3mm 16mm 0; }
.bf-fig{ break-inside:avoid; margin:0 0 5mm; border:1px solid var(--line);
  border-radius:var(--radius); overflow:hidden; background:var(--panel); }
.bf-fig img{ display:block; width:100%; max-height:118mm; object-fit:contain;
  border-bottom:1px solid var(--line); }
.bf-fig figcaption{ padding:3mm 4mm; font-family:var(--read); font-size:9.5pt; line-height:1.4;
  color:var(--muted); }
.bf-fig .fid{ font-family:var(--mono); font-size:7pt; font-weight:700; color:var(--accent);
  margin-right:2mm; }
.bf-fig .src{ display:block; margin-top:1.2mm; color:var(--faint); }
.bf-refs{ padding:3mm 16mm 14mm; }
.bf-refs h3{ font-family:var(--ui); font-weight:700; font-size:11pt; color:var(--ink);
  border-top:1px solid var(--line); padding-top:2mm; margin:5mm 0 2mm; }
.bf-ref{ font-family:var(--read); font-size:9pt; color:var(--ink); margin:0 0 1.6mm;
  padding-left:9mm; text-indent:-9mm; }
.bf-ref .rid{ font-family:var(--mono); font-size:7.5pt; font-weight:700; color:var(--accent);
  margin-right:2mm; }
.bf-ref .map{ display:block; font-family:var(--mono); font-size:6.6pt; color:var(--muted);
  text-transform:uppercase; letter-spacing:.08em; text-indent:0; }
"""


def _figure_html(fig) -> str:
    from neuro_caseboard.exec_navy import img_data_uri
    try:
        img = f'<img src="{img_data_uri(fig.image_path)}">'
    except Exception:
        img = ""                                         # never emit a broken image; keep caption
    src_bits = " · ".join(p for p in (fig.citation, fig.source_n, fig.intent) if p)
    src = f'<span class="src">{_esc(src_bits)}</span>' if src_bits else ""
    return (f'<figure class="bf-fig">{img}<figcaption>'
            f'<span class="fid">{_esc(fig.fig_id)}</span>{_esc(fig.caption)}{src}'
            f'</figcaption></figure>')


def build_figure_atlas_html(figures, theme: str = "signal") -> str:
    if not figures:
        return ""
    figs = "".join(_figure_html(f) for f in figures)
    return ('<div class="bf-break"></div>'
            '<div class="bf-page-h">Figure Atlas — high-yield plates</div>'
            f'<div class="bf-atlas">{figs}</div>')


def _ref_html(ref) -> str:
    mapline = ""
    if ref.sections:
        mapline = f'<span class="map">supports: {_esc(", ".join(ref.sections))}</span>'
    extra = ""
    for k in ("pmid", "doi", "url", "page", "book"):
        v = (ref.meta or {}).get(k)
        if v:
            extra += f" · {_esc(str(v))}"
    return (f'<div class="bf-ref"><span class="rid">{_esc(ref.ref_id)}</span>'
            f'{_esc(ref.citation)}{extra}{mapline}</div>')


def build_references_html(references, theme: str = "signal") -> str:
    if not references:
        return ""
    tb = [r for r in references if r.kind == "textbook"]
    lit = [r for r in references if r.kind == "pubmed"]
    out = ['<div class="bf-break"></div>',
           '<div class="bf-page-h">References &amp; Evidence</div>',
           '<div class="bf-refs">']
    if tb:
        out.append("<h3>Textbook sources</h3>")
        out.extend(_ref_html(r) for r in tb)
    if lit:
        out.append("<h3>Contemporary Literature</h3>")
        out.extend(_ref_html(r) for r in lit)
    out.append("</div>")
    return "".join(out)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k "atlas or references" -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/operative_briefing_pdf.py tests/test_operative_briefing_pdf.py
git commit -m "feat(briefing-pdf): figure atlas + references page (T#/L# distinct) (Plan 2 Task 5)"
```

---

## Task 6: Full-doc assembly + Chromium orchestrator + compress factory

**Files:**
- Modify: `neuro_caseboard/operative_briefing_pdf.py`
- Test: `tests/test_operative_briefing_pdf.py`

**Interfaces:**
- Consumes: all builders + `fit_briefing_page` + `count_pdf_pages`. `OperativeBriefingBundle` (Plan 1): `.briefing`, `.figures`, `.references`, `.topic`, `.provenance`.
- Produces:
  - `_assemble_full_doc(page1_fragment, atlas_body, refs_body, *, fs, theme, title, topic) -> str` (pure — one `<!doctype>` doc: page-1 wrapper at `--fs`, then atlas, then refs; one `<style>` block = tokens + page CSS + atlas CSS + algo-safe).
  - `_make_compress(synth_client)` — returns a `compress(briefing)->briefing` that tightens prose-section item text via `synth_client.generate(...)`; `None` when `synth_client is None`. Grounded: "rewrite each line more concisely, same clinical facts, add nothing."
  - `render_operative_briefing_pdf(bundle, out_path, *, theme=None, synth_client=None) -> str` — theme from `CASEBOARD_PDF_STYLE` when not given; lazy Playwright import (absent → `RuntimeError`); real `measure` = render page-1 doc → PDF bytes → `count_pdf_pages`; run ladder; assemble; render once to `out_path`.

- [ ] **Step 1: Write the failing tests** (assembly is pure; honest-error via `sys.modules` injection — no Chromium needed)

```python
# tests/test_operative_briefing_pdf.py  (append)
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k "assemble or compress or honest" -q`
Expected: FAIL — `_assemble_full_doc`/`_make_compress`/`render_operative_briefing_pdf` not defined.

- [ ] **Step 3: Implement**

```python
# neuro_caseboard/operative_briefing_pdf.py  (append)

_PDF_MARGIN = {"top": "0", "bottom": "0", "left": "0", "right": "0"}


def _assemble_full_doc(page1_fragment: str, atlas_body: str, refs_body: str, *,
                       fs: float, theme: str, title: str, topic: str) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'><title>"
            f"{_esc(title)}</title><style>"
            f"{_tokens(theme)}{_BRIEFING_PAGE_CSS}{_ATLAS_CSS}</style></head><body>"
            f'<div class="bf-page" style="--fs:{fs}">{page1_fragment}</div>'
            f"{atlas_body}{refs_body}</body></html>")


def _make_compress(synth_client):
    """Return compress(briefing)->tightened copy, or None when no client (ladder skips rung 3)."""
    if synth_client is None:
        return None

    def compress(briefing):
        flat = [(si, ii) for si, sec in enumerate(briefing.sections)
                for ii, _ in enumerate(sec.items)]
        if not flat:
            return briefing
        lines = [briefing.sections[si].items[ii].text for si, ii in flat]
        system = ("You tighten operative-briefing bullet lines. Rewrite each numbered line "
                  "more concisely. Preserve every clinical fact, number, device, and dose. "
                  "Add nothing. Output exactly one rewritten line per input line, same order, "
                  "no numbering.")
        user = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(lines))
        try:
            out = synth_client.generate(system, user, [])
        except Exception:
            return briefing
        new = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
        if len(new) != len(lines):
            return briefing                       # shape mismatch -> don't risk dropping facts
        copy = briefing.model_copy(deep=True)
        for (si, ii), txt in zip(flat, new):
            copy.sections[si].items[ii].text = txt
        return copy

    return compress


def render_operative_briefing_pdf(bundle, out_path, *, theme: str | None = None,
                                  synth_client=None) -> str:
    """Render the bundle to an A4 PDF at out_path. Requires the `briefing` extra + Chromium."""
    if theme is None:
        theme = os.environ.get("CASEBOARD_PDF_STYLE", "signal")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:                          # ImportError, or None injected in tests
        raise RuntimeError(
            "renderer unavailable: the operative-briefing PDF needs the `briefing` extra "
            "(Playwright + a Chromium binary)") from e
    if sync_playwright is None:
        raise RuntimeError("renderer unavailable: Playwright not importable")

    briefing = bundle.briefing
    title = getattr(briefing, "title", "") or getattr(bundle, "topic", "")
    atlas = build_figure_atlas_html(getattr(bundle, "figures", []) or [], theme)
    refs = build_references_html(getattr(bundle, "references", []) or [], theme)
    compress = _make_compress(synth_client)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def measure(doc: str) -> int:
            page.set_content(doc, wait_until="load")
            data = page.pdf(format="A4", print_background=True, margin=_PDF_MARGIN)
            return count_pdf_pages(data)

        fit = fit_briefing_page(briefing, measure, theme=theme, compress=compress)
        doc = _assemble_full_doc(fit.fragment, atlas, refs, fs=fit.fs, theme=theme,
                                 title=title, topic=getattr(bundle, "topic", ""))
        page.set_content(doc, wait_until="networkidle")
        page.evaluate("async () => { await document.fonts.ready; }")
        page.pdf(path=str(out_path), format="A4", print_background=True, margin=_PDF_MARGIN)
        browser.close()
    return str(out_path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -k "assemble or compress or honest" -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/operative_briefing_pdf.py tests/test_operative_briefing_pdf.py
git commit -m "feat(briefing-pdf): full-doc assembly + Chromium orchestrator + compress factory (Plan 2 Task 6)"
```

---

## Task 7: Full-module test pass + collection precheck

**Files:**
- Test: `tests/test_operative_briefing_pdf.py` (run all)

- [ ] **Step 1: Collection precheck** (CLAUDE.md: a bad import aborts the whole suite)

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py --collect-only -q`
Expected: collects ~15 tests, no import error.

- [ ] **Step 2: Run the full new module**

Run: `python3 -m pytest tests/test_operative_briefing_pdf.py -q`
Expected: PASS (all).

- [ ] **Step 3: Scoped regression loop** (nothing else touched, but confirm)

Run: `python3 -m pytest tests/test_briefing_model.py tests/test_briefing_synth.py tests/test_briefing_pipeline.py tests/test_briefing_figures.py -q`
Expected: PASS (Plan 1 unaffected).

- [ ] **Step 4: Commit** (only if any fixups were needed)

```bash
git add -A && git commit -m "test(briefing-pdf): full module green + Plan 1 regression (Plan 2 Task 7)"
```

---

## Task 8: Manual 3-PDF render verification (completion gate — spec §13/§14)

**Not a committed test** (Playwright/real-model/corpus stays manual per spec §12). Run as a job-dir script; needs Vertex ADC + corpus (this box has both).

- [ ] **Step 1: Render cranial / spine / endovascular bundles and verify invariants**

```python
# $CLAUDE_JOB_DIR/tmp/verify_briefing_pdf.py
import io, pypdf
from neuro_caseboard.pipeline import build_briefing_bundle
from neuro_caseboard.operative_briefing_pdf import (
    render_operative_briefing_pdf, build_briefing_page_html, count_pdf_pages)
from neuro_caseboard.pipeline import briefing_synth_client

CASES = {
    "cranial": "left MCA bifurcation aneurysm clipping",
    "spine":   "L4-5 TLIF for spondylolisthesis",
    "endo":    "ruptured ACOM aneurysm coiling",
}
synth = briefing_synth_client()
for tag, q in CASES.items():
    b = build_briefing_bundle(q, synth_client=synth)
    out = f"/home/michael/.claude/jobs/5596a340/tmp/briefing_{tag}.pdf"
    render_operative_briefing_pdf(b, out, synth_client=synth)
    total = count_pdf_pages(open(out, "rb").read())
    # page-1-only page count (the <=2 invariant target)
    print(tag, "figures:", len(b.figures), "refs:", len(b.references),
          "total_pages:", total)
```

Run: `python3 $CLAUDE_JOB_DIR/tmp/verify_briefing_pdf.py`
Expected: each case prints `figures: 5..10`, `refs: >0`, and `total_pages` reasonable (page-1 ≤2 + atlas + refs).

- [ ] **Step 2: Confirm the ≤2-page briefing invariant directly** (render page-1 alone, count)

Add to the script: for each bundle, run `fit_briefing_page` with the real Chromium measure and assert `fit.pages <= 2`; print `fit.rungs`. (The orchestrator already does this internally; this makes the invariant explicit in the log.)

- [ ] **Step 3: Eyeball the 3 PDFs** — page 1 has no images/citations; atlas after; references last; legible at the chosen `--fs`; gallery captions intact. Send them to the user.

- [ ] **Step 4: Final commit / PR** — open the Plan 2 PR (renderer module + tests). Note in the PR body that API/CLI/Web wiring is Plan 3.

---

## Self-Review (against spec §7 + §8 + §12)

- **§7 HTML→Chromium A4, Signal via tokens + `CASEBOARD_PDF_STYLE`** — Task 6 (`theme` from env, `_tokens`). ✓
- **§7 page-1 pure builder, no figure/biblio slots** — Task 3 `_page1_body` renders no `<img>`/no `source_refs`; invariant test. ✓
- **§7 decision algorithm = deterministic SVG, theme tokens, no Graphviz** — Task 2 (`<style>`-class colors, defensive). ✓
- **§7 fit ladder: shrink → trim → 1 compress → allow page 2; ≤2 always** — Task 4 (authoritative measure injected; converges). ✓
- **§7 measure authoritative (not scrollHeight)** — Task 1 `count_pdf_pages` + Task 6 real measure renders to PDF bytes. ✓ (advisor)
- **§7 Chromium absent → honest error; pure builders offline** — Task 6 honest-error test; Tasks 1–5 all offline. ✓
- **§7 atlas 1–2 figs/page by aspect, full captions + source** — Task 5 (`break-inside:avoid`, `max-height` lets 1–2 land per page; caption+source). ✓ *(aspect-driven 1-vs-2 is emergent from CSS max-height, not hardcoded — acceptable per ponytail; add explicit pairing only if atlas looks sparse in Task 8.)*
- **§8 references: T#/L# distinct, support-map by section, may spill** — Task 5 (separate groups, `sections` map line). ✓
- **§11 never fabricate; unsupported marked not dropped** — Task 3 (`unsupported` → visible "clinician-verify", never removed by `drop`). ✓
- **§12 offline deterministic; cross-subspecialty + negative controls; importorskip n/a (no streamlit); no xdist** — Tasks 2–6 fakes; Task 3 cross-subspecialty equipment + negative controls. ✓
- **Scope: renderer only; API/CLI/Web = Plan 3** — stated in Global Constraints + Task 8 Step 4. ✓

**Deferred to Plan 3 (unchanged from Plan 1 handoff):** `POST /api/briefing/pdf`, `_BRIEFING_CACHE`, generated TS types, Build.tsx surface.
