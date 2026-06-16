# Ask-Pathway Executive-Navy PDF Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `ask` (Q&A) responses be exported as a PDF in PR #7's Executive-Navy design, on both `caseboard ask --pdf` and the Streamlit Ask lane, with an offline fpdf2 fallback.

**Architecture:** Extract the shared print theme (`exec_navy.py`) and shared fpdf2 font setup (`fpdf_base.py`) so the brand lives in one place; rewrite the orphaned `briefing_pdf.py` from the old Signal design to Executive-Navy (walking the `QAResult` shape) and add an offline fpdf2 fallback to it; add `pipeline.render_ask_pdf()` as the single source of truth (mirrors `render_case_pdf()`); wire it into the CLI and the Streamlit Ask lane.

**Tech Stack:** Python 3.12, fpdf2 (offline PDF), Playwright/Chromium (HTML→PDF), pytest, Streamlit, PyMuPDF (`fitz`, test-only).

**Reference spec:** `docs/superpowers/specs/2026-06-16-ask-pdf-export-design.md`

**Conventions for every task:** run tests with `python -m pytest` from the repo root. Commit messages use Conventional Commits and end with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer. We are on the isolated worktree branch `worktree-ask-pdf-export-pr7-design`.

---

## Task 1: Extract shared fpdf2 font setup → `fpdf_base.py`

Behavior-preserving extraction so the new offline Q&A renderer (Task 4) and the existing
`render_pdf.py` share one font-registration + ASCII-fallback implementation.

**Files:**
- Create: `neuro_caseboard/fpdf_base.py`
- Modify: `neuro_caseboard/render_pdf.py` (lines 16-54: imports + `_REPL`/`_ascii`/`_register`/`_FONT_DIR`)
- Test: `tests/test_fpdf_base.py` (new), `tests/test_render_pdf.py` (existing — regression net)

- [ ] **Step 1: Write the failing test**

Create `tests/test_fpdf_base.py`:

```python
"""The shared fpdf2 font setup: register the Unicode font when present, and a deterministic
ASCII transliteration that never emits '?'."""
from fpdf import FPDF

from neuro_caseboard.fpdf_base import register_fonts, ascii_fallback


def test_register_fonts_returns_family_and_unicode_flag():
    fam, uni = register_fonts(FPDF(format="A4"))
    # The repo ships DejaVu under neuro_caseboard/assets/fonts, so this resolves to Unicode.
    assert fam == "DejaVu" and uni is True


def test_ascii_fallback_transliterates_known_glyphs_without_question_marks():
    out = ascii_fallback("≥ 5 ✓ ⚠ — “x”")
    assert ">=" in out and "[OK]" in out and "[!]" in out
    assert "?" not in out and "✓" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fpdf_base.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.fpdf_base'`.

- [ ] **Step 3: Create `neuro_caseboard/fpdf_base.py`**

```python
"""Shared fpdf2 font setup for the clinical (offline) PDF renderers.

Owns DejaVu Unicode font registration (so ✓ ⚠ — etc. render as real glyphs, never the latin-1
'?' replacement) and the deterministic ASCII transliteration used when those fonts can't be
embedded. Imported by render_pdf.py (Dossier) and briefing_pdf.py's clinical Q&A fallback.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from fpdf import FPDF

_FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# Deterministic ASCII fallback, used only when the Unicode font can't be embedded.
_REPL = {
    "≥": ">=", "≤": "<=", "×": "x", "→": "->", "—": "-", "–": "-",
    "“": '"', "”": '"', "‘": "'", "’": "'", "•": "-", "·": "-",
    "✓": "[OK]", "⚠": "[!]", "…": "...",
}


def ascii_fallback(s: str) -> str:
    for k, v in _REPL.items():
        s = s.replace(k, v)
    # strip any remaining non-ascii without ever producing '?'
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def register_fonts(pdf: FPDF):
    reg = _FONT_DIR / "DejaVuSans.ttf"
    bold = _FONT_DIR / "DejaVuSans-Bold.ttf"
    obl = _FONT_DIR / "DejaVuSans-Oblique.ttf"
    if reg.exists() and bold.exists() and obl.exists():
        pdf.add_font("DejaVu", "", str(reg))
        pdf.add_font("DejaVu", "B", str(bold))
        pdf.add_font("DejaVu", "I", str(obl))
        return "DejaVu", True
    return "Helvetica", False
```

- [ ] **Step 4: Point `render_pdf.py` at the shared module**

In `neuro_caseboard/render_pdf.py`:
- Remove the now-moved block (the `_FONT_DIR` line, the `_REPL` dict, `def _ascii`, `def _register`) and the `import unicodedata` line (no longer used).
- Add the import near the other imports: `from neuro_caseboard.fpdf_base import register_fonts, ascii_fallback`
- In `render_pdf()`, change `fam, uni = _register(pdf)` → `fam, uni = register_fonts(pdf)`.
- In `render_pdf()`, change the `t` helper body `return s if uni else _ascii(s)` → `return s if uni else ascii_fallback(s)`.

(Keep `import os` and `from pathlib import Path` — still used by `_render_figure` and `out_path`. The `_COLORS`, `_BLACK`, `_GRAY`, `_register`-free body otherwise unchanged.)

- [ ] **Step 5: Run tests to verify pass + no regression**

Run: `python -m pytest tests/test_fpdf_base.py tests/test_render_pdf.py -q`
Expected: PASS (the new module tests + the existing Dossier-render regression suite).

- [ ] **Step 6: Commit**

```bash
git add neuro_caseboard/fpdf_base.py neuro_caseboard/render_pdf.py tests/test_fpdf_base.py
git commit -m "refactor(pdf): extract shared fpdf2 font setup into fpdf_base

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Extract shared Executive-Navy theme → `exec_navy.py`

Behavior-preserving extraction so the build dossier renderer and the new Q&A briefing renderer
(Task 3) share one CSS token sheet and the two pure helpers — the brand defined in one place.

**Files:**
- Create: `neuro_caseboard/exec_navy.py`
- Modify: `neuro_caseboard/caseboard_pdf.py` (lines 16-24 imports, 25-118 `EXEC_NAVY_CSS`, 123-135 `_inline`/`_img_data_uri`, and their call sites)
- Test: `tests/test_exec_navy.py` (new), `tests/test_caseboard_pdf.py` (new — guard for the refactor, since the build HTML builder has no offline test today)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_exec_navy.py`:

```python
"""The shared Executive-Navy print theme: the brand CSS tokens + the two pure helpers."""
import base64

from neuro_caseboard.exec_navy import EXEC_NAVY_CSS, inline, img_data_uri


def test_inline_escapes_then_promotes_bold():
    assert inline("a <b> & **bold**") == "a &lt;b&gt; &amp; <b>bold</b>"


def test_img_data_uri_derives_mime_from_basename_only(tmp_path):
    p = tmp_path / "v1.2"
    p.mkdir()
    f = p / "figA.JPG"            # dotted parent dir must not corrupt the MIME
    f.write_bytes(b"\xff\xd8\xff")
    uri = img_data_uri(str(f))
    assert uri.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == b"\xff\xd8\xff"


def test_css_carries_the_brand_tokens():
    assert "--accent:#0e7490" in EXEC_NAVY_CSS
    assert "Archivo" in EXEC_NAVY_CSS and "IBM+Plex+Mono" in EXEC_NAVY_CSS
```

Create `tests/test_caseboard_pdf.py`:

```python
"""Guard the build (Dossier) Executive-Navy HTML builder — proves the exec_navy extraction
left the build pathway's output intact (this builder had no offline test before)."""
from neuro_caseboard.caseboard_pdf import build_caseboard_html
from neuro_caseboard.model import Dossier, EvidenceSummary, Section, Claim


def _dossier():
    return Dossier(
        title="C5–6 ACDF",
        summary=EvidenceSummary(supported=2, to_verify=1, quarantined=0),
        sections=[Section(
            heading="Anatomy at risk", intro="Structures near the approach.",
            claims=[Claim(text="The **vertebral artery** runs in the foramen transversarium.",
                          why="Avoid far-lateral dissection.", status="supported")])])


def test_build_caseboard_html_carries_exec_navy_tokens_and_content():
    doc = build_caseboard_html(_dossier(), subtitle="cervical case")
    assert "NEURO·CASEBOARD" in doc                      # masthead brand
    assert "Archivo" in doc and "Source+Serif+4" in doc  # three-font role system
    assert "#0e7490" in doc                              # deep-teal accent
    assert "C5–6 ACDF" in doc                            # title
    assert "<b>vertebral artery</b>" in doc              # inline bold via shared helper
    assert "Corpus-supported" in doc                     # status-marker label
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_exec_navy.py tests/test_caseboard_pdf.py -q`
Expected: FAIL — `test_exec_navy` fails with `ModuleNotFoundError: neuro_caseboard.exec_navy`; `test_caseboard_pdf` may PASS already (it exercises current behavior) — that's fine, it becomes the regression guard for Step 3-4.

- [ ] **Step 3: Create `neuro_caseboard/exec_navy.py`**

Move the `EXEC_NAVY_CSS = """ … """` string **verbatim** out of `caseboard_pdf.py` (lines 25-118) into this new file, and move the two helpers. File contents:

```python
"""Shared Executive-Navy print theme — the single source of the brand for the PDF renderers
(caseboard_pdf.py build dossier + briefing_pdf.py Q&A briefing), mirroring the web console
(app/signal_theme.py). The navy/teal/Source-Serif identity is defined here, in one place.
"""
from __future__ import annotations

import base64
import html
import os
import re

# >>> Paste the EXEC_NAVY_CSS string moved verbatim from caseboard_pdf.py here:
EXEC_NAVY_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=IBM+Plex+Mono:wght@500;600&display=swap');
:root{
  --ink:#16202c; --muted:#586676; --faint:#8a96a2; --line:#e7e9ee; --line-soft:#eef0f3;
  --accent:#0e7490; --accent-soft:rgba(14,116,144,.4);
  --supported:#0f766e; --verify:#a9781b; --quar:#b4493b;
  --supported-bg:rgba(15,118,110,.10); --verify-bg:rgba(169,120,27,.12);
  --ui:'Archivo',system-ui,sans-serif; --read:'Source Serif 4',Georgia,serif;
  --mono:'IBM Plex Mono',ui-monospace,monospace;
}
/* … REMAINDER OF THE EXISTING EXEC_NAVY_CSS, COPIED VERBATIM (do not retype from memory;
   cut-and-paste the whole block from caseboard_pdf.py lines 26-117) … */
"""


def inline(text: str) -> str:
    """Escape, then promote ``**bold**`` to <b> (the only inline markup claims/why use)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text or ""))


def img_data_uri(path: str) -> str:
    # Derive the extension from the basename only — a dot in a parent dir (e.g. /data/v1.2/figA)
    # or a missing extension must not corrupt the MIME type.
    name = os.path.basename(path)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, f"image/{ext}")
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
```

> IMPORTANT: copy the full CSS body by cut-and-paste from `caseboard_pdf.py`; the abbreviated comment above is a placeholder for the move, not the literal content.

- [ ] **Step 4: Point `caseboard_pdf.py` at the shared module**

In `neuro_caseboard/caseboard_pdf.py`:
- Remove `import base64`, `import os`, `import re` (now unused there). Keep `import datetime as dt` and `import html` (still used by `build_caseboard_html`).
- Remove the `EXEC_NAVY_CSS = """ … """` definition and the `def _inline` / `def _img_data_uri` functions.
- Add: `from neuro_caseboard.exec_navy import EXEC_NAVY_CSS, inline, img_data_uri`
- Replace every call `_inline(` → `inline(` and `_img_data_uri(` → `img_data_uri(` (in `_claim_html`, `_figure_html`, and `build_caseboard_html`).

- [ ] **Step 5: Run tests to verify pass + no regression**

Run: `python -m pytest tests/test_exec_navy.py tests/test_caseboard_pdf.py -q`
Expected: PASS (extraction is behavior-preserving; the guard test confirms the build HTML is intact).

- [ ] **Step 6: Commit**

```bash
git add neuro_caseboard/exec_navy.py neuro_caseboard/caseboard_pdf.py tests/test_exec_navy.py tests/test_caseboard_pdf.py
git commit -m "refactor(pdf): extract shared Executive-Navy theme into exec_navy

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Rewrite `briefing_pdf.py` to the Executive-Navy Q&A briefing

Replace the orphaned Signal design with Executive-Navy, keeping the public API
(`build_briefing_html` / `render_briefing_pdf`) and the content logic (markdown answer,
duck-typed access, literature, robust figure skipping).

**Files:**
- Modify (rewrite): `neuro_caseboard/briefing_pdf.py`
- Test: `tests/test_briefing_pdf.py` (rewrite token asserts), `tests/test_briefing_literature.py` (unchanged content asserts — verify still green)

- [ ] **Step 1: Rewrite the token assertions in `tests/test_briefing_pdf.py`**

Replace `test_build_briefing_html_has_signal_tokens_and_content` with the Executive-Navy
version (keep the other three tests as-is — their asserts are content/markdown, not design):

```python
def test_build_briefing_html_has_exec_navy_tokens_and_content():
    doc = build_briefing_html(_Result(), title="My Briefing Title", subtitle="a subtitle")
    # content
    assert "My Briefing Title" in doc and "a subtitle" in doc
    assert "Indications" in doc and "Sources" in doc
    assert "[1]" in doc and "Greenberg, Trauma, p.1102" in doc
    assert "<strong>refractory</strong>" in doc          # markdown bold -> html
    # Executive-Navy design tokens (replaces the old Signal asserts)
    assert "Archivo" in doc and "Source+Serif+4" in doc and "IBM+Plex+Mono" in doc
    assert "#0e7490" in doc                              # deep-teal accent
    assert "NEURO·CASEBOARD" in doc                      # masthead brand
    assert "Ask · Citation-grounded" in doc              # eyebrow chip
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_briefing_pdf.py::test_build_briefing_html_has_exec_navy_tokens_and_content -q`
Expected: FAIL — the current Signal output has no `Archivo` / `#0e7490` / `NEURO·CASEBOARD`.

- [ ] **Step 3: Rewrite `neuro_caseboard/briefing_pdf.py`**

Full new file content:

```python
"""Executive-Navy briefing PDF for Q&A (ask) results — the print sibling of caseboard_pdf.py
for the question-answer shape.

Renders a query result (markdown answer + numbered textbook citations + optional contemporary
PubMed literature + figures) in the current Executive-Navy identity (shared with the web console
and the build dossier via exec_navy.py): a deep-navy masthead over a bright report plane, the
three-font role system (Archivo UI / Source Serif 4 reading column / IBM Plex Mono micro-labels)
and one deep-teal accent.

``build_briefing_html`` is pure and dependency-light (unit-tested offline). ``render_briefing_pdf``
needs the ``briefing`` extra (Playwright + a Chromium binary). ``render_briefing_clinical_pdf`` is
the offline fpdf2 fallback (no Chromium) used when CASEBOARD_PDF_STYLE=clinical or Chromium is
unavailable.
"""
from __future__ import annotations

import datetime as dt
import html
import re

from neuro_caseboard.exec_navy import EXEC_NAVY_CSS, img_data_uri

DEFAULT_EYEBROW = "Ask · Citation-grounded"

# Q&A-only selectors layered on the shared Executive-Navy sheet (masthead, eyebrow chip, title,
# rule, section headers, figures and footer all come from EXEC_NAVY_CSS).
ASK_CSS = """
.answer{ font-family:var(--read); font-size:11pt; line-height:1.55; color:#1e2a36; max-width:165mm; }
.answer p{ margin:0 0 2.6mm; }
.answer ul{ margin:0 0 3mm; padding-left:6mm; } .answer li{ margin:0 0 1.2mm; }
.answer strong{ color:#0c2233; font-weight:600; }
.answer h2{ font-family:var(--ui); font-weight:700; font-size:13pt; color:var(--ink);
  letter-spacing:-.01em; margin:6mm 0 2mm; padding-top:3mm; border-top:1px solid var(--line); }
.answer h3{ font-family:var(--ui); font-weight:600; font-size:10.5pt; color:var(--accent);
  margin:4mm 0 1.5mm; }
.sources{ border:1px solid var(--line); border-radius:10px; padding:1mm 4mm; max-width:165mm;
  box-shadow:0 1px 2px rgba(16,32,48,.04); }
.src{ font-family:var(--read); font-size:9.6pt; color:#33424f; padding:1.8mm 0;
  border-top:1px solid var(--line-soft); }
.src:first-child{ border-top:none; }
.src .n, .src .ln{ font-family:var(--mono); font-size:7pt; color:var(--accent); font-weight:600;
  margin-right:2mm; }
.src a{ color:var(--accent); text-decoration:none; }
.litmeta{ color:var(--muted); }
"""


def _g(obj, key, default=None):
    """Read ``key`` from a dict or an attribute-bearing object (duck-typed result/citation/figure)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _fmt(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(s))


def _md_to_html(md: str) -> str:
    out, in_ul = [], False

    def close():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>"); in_ul = False

    for raw in (md or "").split("\n"):
        s = raw.strip()
        if not s:
            close(); continue
        if s.startswith("### "):
            close(); out.append(f"<h3>{_fmt(s[4:])}</h3>"); continue
        if s.startswith("## "):
            close(); out.append(f"<h2>{_fmt(s[3:])}</h2>"); continue
        if s[:2] in ("* ", "- ") or s.startswith("*\t"):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{_fmt(s[1:].strip())}</li>"); continue
        close(); out.append(f"<p>{_fmt(s)}</p>")
    close()
    return "\n".join(out)


def _sources_html(result) -> str:
    rows = []
    for c in (_g(result, "citations") or []):
        loc = html.escape(_g(c, "book") or "")
        if _g(c, "chapter"):
            loc += f", {html.escape(_g(c, 'chapter'))}"
        loc += f", p.{_g(c, 'page')}"
        rows.append(f'<div class="src"><span class="n">[{_g(c, "n")}]</span> {loc}</div>')
    return ('<div class="section"><div class="sec-h"><span class="k">SRC</span>'
            '<span class="t">Sources</span><span class="ln"></span></div>'
            f'<div class="sources">{"".join(rows)}</div></div>')


def _literature_html(result) -> str:
    """Render the Contemporary Literature section, or '' when absent/empty."""
    lit = _g(result, "literature")
    if not lit:
        return ""
    narrative = _g(lit, "narrative") or ""
    cites = _g(lit, "citations") or []
    if not narrative or not cites:
        return ""
    rows = []
    for c in cites:
        doi = _g(c, "doi") or ""
        href = f"https://doi.org/{doi}" if doi else (_g(c, "url") or "")
        meta = ", ".join(p for p in (html.escape(_g(c, "journal") or ""),
                                     str(_g(c, "year") or "")) if p)
        link = f' · <a href="{html.escape(href)}">link</a>' if href else ""
        rows.append(f'<div class="src"><span class="ln">[L{_g(c, "n")}]</span> '
                    f'{html.escape(_g(c, "title") or "")} '
                    f'<span class="litmeta">— {meta}</span>{link}</div>')
    return ('<div class="section"><div class="sec-h"><span class="k">LIT</span>'
            '<span class="t">Contemporary Literature</span><span class="ln"></span></div>'
            f'<div class="answer">{_md_to_html(narrative)}</div>'
            f'<div class="sources">{"".join(rows)}</div></div>')


def _figures_html(result) -> str:
    out = []
    for f in (_g(result, "figures") or []):
        try:
            src = img_data_uri(_g(f, "image_path"))
        except Exception:
            continue  # unreadable -> skip the whole figure, never a broken <figure>
        loc = f'{html.escape(_g(f, "book") or "")}, p.{_g(f, "page")}'
        out.append(f'<figure><img src="{src}"><figcaption>'
                   f'<span class="fid">Fig [{_g(f, "source_n")}]</span> '
                   f'{html.escape(_g(f, "caption") or "")} <span class="cite">— {loc}</span>'
                   '</figcaption></figure>')
    return "".join(out)


def build_briefing_html(result, *, title: str, subtitle: str = "",
                        eyebrow: str = DEFAULT_EYEBROW, today: str | None = None) -> str:
    """Pure: render a Q&A result to an Executive-Navy HTML briefing string. Figures whose image
    file can't be read are skipped (never crash, never emit a broken image)."""
    today = today or dt.date.today().isoformat()
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><style>",
        EXEC_NAVY_CSS, ASK_CSS,
        "</style></head><body>",
        '<div class="masthead"><div class="mh-brand"><span class="sq"></span>NEURO·CASEBOARD</div>',
        '<div class="mh-eyebrow">Neurosurgery Signal · clinical briefing</div></div>',
        '<div class="content">',
        f'<span class="eyebrow">{html.escape(eyebrow)}</span>',
        f'<h1 class="title">{html.escape(title)}</h1>',
    ]
    if subtitle:
        parts.append(f'<div class="standfirst">{html.escape(subtitle)}</div>')
    parts.append('<div class="rule"></div>')
    parts.append(f'<div class="answer">{_md_to_html(_g(result, "answer") or "")}</div>')
    parts.append(_sources_html(result))
    parts.append(_literature_html(result))
    parts.append(_figures_html(result))
    parts.append("</div>")  # /content
    parts.append('<div class="footer">Generated from the neurosurgery textbook corpus · '
                 f'decision-support only · {html.escape(today)}</div>')
    parts.append("</body></html>")
    return "".join(parts)


def render_briefing_pdf(result, out_path, *, title: str, subtitle: str = "",
                        eyebrow: str = DEFAULT_EYEBROW) -> str:
    """Render the briefing to an A4 PDF via Playwright/Chromium. Requires the ``briefing`` extra
    and an installed Chromium binary."""
    from playwright.sync_api import sync_playwright
    doc = build_briefing_html(result, title=title, subtitle=subtitle, eyebrow=eyebrow)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(doc, wait_until="networkidle")
        page.evaluate("async () => { await document.fonts.ready; }")
        page.pdf(path=str(out_path), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    return str(out_path)
```

(The fpdf2 fallback `render_briefing_clinical_pdf` is added in Task 4.)

- [ ] **Step 4: Run the briefing tests**

Run: `python -m pytest tests/test_briefing_pdf.py tests/test_briefing_literature.py -q`
Expected: PASS — the rewritten token test, the unchanged figure-skip / dict-shaped / assuming-bold tests, and both literature tests (`Contemporary Literature`, `[L1]`, `Tenecteplase before EVT`, `https://doi.org/10.1161/abc`, and absence-when-empty) all hold against the Exec-Navy output.

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_pdf.py tests/test_briefing_pdf.py
git commit -m "feat(ask-pdf): reskin the Q&A briefing to Executive-Navy

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Add the offline fpdf2 fallback `render_briefing_clinical_pdf`

**Files:**
- Modify: `neuro_caseboard/briefing_pdf.py` (append the fallback + two small helpers)
- Test: `tests/test_briefing_pdf.py` (append offline-PDF tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_briefing_pdf.py`:

```python
def test_render_briefing_clinical_pdf_is_real_offline_pdf(tmp_path):
    from neuro_caseboard.briefing_pdf import render_briefing_clinical_pdf
    out = tmp_path / "ask.pdf"
    render_briefing_clinical_pdf(_Result(), out, title="Offline Q", subtitle="sub")
    data = out.read_bytes()
    assert data[:5].startswith(b"%PDF")
    assert len(data) > 1000


def test_render_briefing_clinical_pdf_handles_no_citations(tmp_path):
    from neuro_caseboard.briefing_pdf import render_briefing_clinical_pdf
    out = tmp_path / "ask2.pdf"
    render_briefing_clinical_pdf({"answer": "Plain answer only.", "citations": [], "figures": []},
                                 out, title="No sources")
    assert out.read_bytes()[:5].startswith(b"%PDF")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_briefing_pdf.py -k clinical -q`
Expected: FAIL — `ImportError: cannot import name 'render_briefing_clinical_pdf'`.

- [ ] **Step 3: Append the fallback to `neuro_caseboard/briefing_pdf.py`**

```python
def _plain(s: str) -> str:
    """Flatten inline **bold** to plain text — the degraded offline path favours legibility."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s or "")


def _md_lines(md: str):
    """Yield (kind, text) for the minimal markdown the answer/narrative use."""
    for raw in (md or "").split("\n"):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("### "):
            yield ("h3", s[4:]); continue
        if s.startswith("## "):
            yield ("h2", s[3:]); continue
        if s[:2] in ("* ", "- ") or s.startswith("*\t"):
            yield ("li", s[1:].strip()); continue
        yield ("p", s)


def render_briefing_clinical_pdf(result, out_path, *, title: str, subtitle: str = "") -> str:
    """Offline fpdf2 fallback (no Chromium): a clean clinical briefing for the Q&A result. Used
    when CASEBOARD_PDF_STYLE=clinical or when Chromium is unavailable."""
    import os
    from pathlib import Path
    from fpdf import FPDF
    from neuro_caseboard.fpdf_base import register_fonts, ascii_fallback

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    fam, uni = register_fonts(pdf)

    def t(s) -> str:
        s = _plain(str(s if s is not None else ""))
        return s if uni else ascii_fallback(s)

    pdf.set_font(fam, "B", 18)
    pdf.multi_cell(0, 9, t(title), new_x="LMARGIN", new_y="NEXT")
    if subtitle:
        pdf.set_font(fam, "I", 10)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 5, t(subtitle), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    for kind, text in _md_lines(_g(result, "answer") or ""):
        if kind == "h2":
            pdf.ln(1); pdf.set_font(fam, "B", 13)
            pdf.multi_cell(0, 7, t(text), new_x="LMARGIN", new_y="NEXT")
        elif kind == "h3":
            pdf.set_font(fam, "B", 11)
            pdf.multi_cell(0, 6, t(text), new_x="LMARGIN", new_y="NEXT")
        elif kind == "li":
            pdf.set_font(fam, "", 10); pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(0, 5, t("- " + text), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(fam, "", 10)
            pdf.multi_cell(0, 5, t(text), new_x="LMARGIN", new_y="NEXT")

    cites = _g(result, "citations") or []
    if cites:
        pdf.ln(2); pdf.set_font(fam, "B", 13)
        pdf.multi_cell(0, 7, t("Sources"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 9)
        for c in cites:
            loc = _g(c, "book") or ""
            if _g(c, "chapter"):
                loc += f", {_g(c, 'chapter')}"
            loc += f", p.{_g(c, 'page')}"
            pdf.multi_cell(0, 4.6, t(f"[{_g(c, 'n')}] {loc}"), new_x="LMARGIN", new_y="NEXT")

    lit = _g(result, "literature")
    if lit and _g(lit, "narrative") and (_g(lit, "citations") or []):
        pdf.ln(2); pdf.set_font(fam, "B", 13)
        pdf.multi_cell(0, 7, t("Contemporary Literature"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 10)
        for kind, text in _md_lines(_g(lit, "narrative")):
            pdf.multi_cell(0, 5, t(("- " + text) if kind == "li" else text),
                           new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 9)
        for c in (_g(lit, "citations") or []):
            doi = _g(c, "doi") or ""
            href = f"https://doi.org/{doi}" if doi else (_g(c, "url") or "")
            meta = ", ".join(p for p in (_g(c, "journal") or "", str(_g(c, "year") or "")) if p)
            pdf.multi_cell(0, 4.6, t(f"[L{_g(c, 'n')}] {_g(c, 'title') or ''} — {meta} {href}"),
                           new_x="LMARGIN", new_y="NEXT")

    for f in (_g(result, "figures") or []):
        path = _g(f, "image_path")
        if path and os.path.exists(path):
            if pdf.get_y() + 70 > pdf.h - pdf.b_margin:
                pdf.add_page()
            try:
                pdf.image(path, w=min(pdf.epw, 110))
            except Exception:
                pass
        pdf.set_font(fam, "I", 8); pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 4, t(f"Fig [{_g(f, 'source_n')}] — {_g(f, 'caption') or ''} "
                               f"({_g(f, 'book') or ''}, p.{_g(f, 'page')})"),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    out_path = Path(out_path)
    pdf.output(str(out_path))
    return str(out_path)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_briefing_pdf.py -q`
Expected: PASS (all briefing tests, including the two new offline-PDF cases). `_Result`'s figure points at a bogus path → image skipped, caption still written, no crash.

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/briefing_pdf.py tests/test_briefing_pdf.py
git commit -m "feat(ask-pdf): offline fpdf2 fallback for the Q&A briefing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `pipeline.render_ask_pdf()` — single source of truth

**Files:**
- Modify: `neuro_caseboard/pipeline.py` (add `render_ask_pdf` after `render_case_pdf`, ~line 240)
- Test: `tests/test_pipeline.py` (append orchestration tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
def test_render_ask_pdf_clinical_style_uses_fpdf(monkeypatch, tmp_path):
    monkeypatch.setenv("CASEBOARD_PDF_STYLE", "clinical")
    from neuro_caseboard.pipeline import render_ask_pdf
    result = {"answer": "Answer [1].",
              "citations": [{"n": 1, "book": "Bk", "chapter": "", "page": 3}], "figures": []}
    out = render_ask_pdf(result, "Q?", tmp_path / "a.pdf")
    assert out.read_bytes()[:5].startswith(b"%PDF")


def test_render_ask_pdf_falls_back_when_chromium_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("CASEBOARD_PDF_STYLE", raising=False)
    import neuro_caseboard.briefing_pdf as bp

    def _boom(*a, **k):
        raise ImportError("no playwright")

    monkeypatch.setattr(bp, "render_briefing_pdf", _boom)
    from neuro_caseboard.pipeline import render_ask_pdf
    out = render_ask_pdf({"answer": "A.", "citations": [], "figures": []}, "Q?", tmp_path / "b.pdf")
    assert out.read_bytes()[:5].startswith(b"%PDF")  # fell back to fpdf2


def test_render_ask_pdf_reraises_real_bug(monkeypatch, tmp_path):
    import pytest
    monkeypatch.delenv("CASEBOARD_PDF_STYLE", raising=False)
    import neuro_caseboard.briefing_pdf as bp

    def _boom(*a, **k):
        raise AttributeError("genuine bug in the exec renderer")

    monkeypatch.setattr(bp, "render_briefing_pdf", _boom)
    from neuro_caseboard.pipeline import render_ask_pdf
    with pytest.raises(AttributeError):
        render_ask_pdf({"answer": "A.", "citations": [], "figures": []}, "Q?", tmp_path / "c.pdf")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -k render_ask_pdf -q`
Expected: FAIL — `ImportError: cannot import name 'render_ask_pdf'`.

- [ ] **Step 3: Add `render_ask_pdf` to `neuro_caseboard/pipeline.py`**

Insert directly after `render_case_pdf()` (before `def generate`):

```python
def render_ask_pdf(result, question, path):
    """Render the ask (Q&A) PDF — the single source of truth for every ``ask`` pathway
    (CLI ``caseboard ask --pdf`` and the Streamlit Ask lane).

    Default is the Executive-Navy briefing that matches the web console (``briefing_pdf``,
    HTML->PDF via Playwright/Chromium). Falls back to the offline fpdf2 renderer when the exec
    renderer is unavailable (e.g. no Chromium in CI) or when ``CASEBOARD_PDF_STYLE=clinical`` is
    set. Returns the written path."""
    style = os.environ.get("CASEBOARD_PDF_STYLE", "exec").strip().lower()
    if style != "clinical":
        try:
            from neuro_caseboard.briefing_pdf import render_briefing_pdf
            render_briefing_pdf(result, path, title=question)
            return Path(path)
        except Exception as e:
            if not _exec_renderer_unavailable(e):
                raise  # a real bug in the exec renderer — surface it, don't mask it
            logging.getLogger(__name__).warning(
                "Executive-Navy ask PDF renderer unavailable (%r); using the clinical fpdf2 "
                "fallback.", e)
    from neuro_caseboard.briefing_pdf import render_briefing_clinical_pdf
    render_briefing_clinical_pdf(result, path, title=question)
    return Path(path)
```

(`os`, `logging`, `Path`, and `_exec_renderer_unavailable` are already imported/defined in `pipeline.py`.)

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_pipeline.py -k render_ask_pdf -q`
Expected: PASS — clinical style → fpdf2; ImportError → fallback; AttributeError → re-raised.

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/pipeline.py tests/test_pipeline.py
git commit -m "feat(ask-pdf): render_ask_pdf single source of truth + fallback

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Wire `caseboard ask --pdf` into the CLI

**Files:**
- Modify: `neuro_caseboard/cli.py` (line 8 import; `_run_ask`; the `ask` subparser ~line 94-97)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_cli_ask_pdf_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEBOARD_PDF_STYLE", "clinical")  # offline fpdf2 path, no Chromium
    monkeypatch.setattr("neuro_core.query.query", lambda q, config=None, force=False: _Result())
    out = tmp_path / "ask.pdf"
    rc = cli.main(["ask", "facial nerve schwannoma", "--pdf", "-o", str(out)])
    assert rc == 0
    assert out.read_bytes()[:5].startswith(b"%PDF")


def test_cli_ask_clarification_writes_no_pdf(tmp_path, monkeypatch, capsys):
    from neuro_core.query import Clarification
    from neuro_core.query_analyze import VariantRewrite
    clar = Clarification(question="decompressive craniectomy steps?",
                         variants=[VariantRewrite("unilateral FTP hemicraniectomy", "a"),
                                   VariantRewrite("bifrontal (Kjellberg) decompression", "b")])
    import neuro_core.query as q
    monkeypatch.setattr(q, "query", lambda question, config=None, force=False: clar)
    out = tmp_path / "nope.pdf"
    rc = cli.main(["ask", "decompressive craniectomy steps?", "--pdf", "-o", str(out)])
    assert rc == 0
    assert not out.exists()                     # no answer -> no PDF
    assert "ambiguous" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_cli.py -k ask_pdf -q`
Expected: FAIL — argparse errors on the unknown `--pdf` flag (`SystemExit`).

- [ ] **Step 3: Edit `neuro_caseboard/cli.py`**

1. Change the import on line 8 to:
   ```python
   from neuro_caseboard.pipeline import generate, render_ask_pdf, _slug
   ```
2. In `_run_ask`, add the export just before the final `return 0` (after the figures block):
   ```python
       if getattr(args, "pdf", False):
           out_path = args.output or f"ask-{_slug(args.question)}.pdf"
           render_ask_pdf(result, args.question, out_path)
           print(f"\nWrote {out_path}")
       return 0
   ```
   (The `Clarification` and `GpuNotReadyError` branches already `return` earlier, so neither
   reaches this block — a clarification or GPU failure writes no PDF.)
3. In `main()`, extend the `ask` subparser (after the `--force` argument):
   ```python
       a.add_argument("--pdf", action="store_true",
                      help="Also export the answer as a PDF briefing")
       a.add_argument("-o", "--output", default=None,
                      help="PDF output path (default ask-<slug>.pdf)")
   ```

- [ ] **Step 4: Run to verify pass (+ no regression in existing ask tests)**

Run: `python -m pytest tests/test_cli.py -q`
Expected: PASS — the two new tests plus all existing ask/build/cards CLI tests.

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cli.py tests/test_cli.py
git commit -m "feat(ask-pdf): caseboard ask --pdf / -o exports the briefing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Wire the Streamlit Ask-lane "Prepare PDF" download

No AppTest harness exists for the app today, and the Ask lane calls `answer_question` directly
(not injectable), so this task is verified by the syntax gate + a manual `streamlit run`
spot-check (covered in Task 8). Keep the edit small and follow the Build-lane download pattern
(`streamlit_app.py:148-153`).

**Files:**
- Modify: `app/streamlit_app.py` (imports line 21; Ask lane, after the literature block ~line 104)

- [ ] **Step 1: Edit `app/streamlit_app.py`**

1. Extend the pipeline import on line 21:
   ```python
   from neuro_caseboard.pipeline import build_dossier, render_case_pdf, render_ask_pdf
   ```
2. In the `if mode == "Ask":` block, after the Contemporary-Literature section and **before**
   the `if st.button("Build a board from this", …)` button, add:
   ```python
           from neuro_caseboard.pipeline import _slug
           if st.checkbox("Prepare PDF", help="Render this answer as an Executive-Navy PDF"):
               with st.spinner("Rendering PDF…"):
                   with tempfile.TemporaryDirectory() as td:
                       pdf_path = render_ask_pdf(result, q, Path(td) / "ask.pdf")
                       pdf_bytes = Path(pdf_path).read_bytes()
               st.download_button("Download PDF", pdf_bytes,
                                  file_name=f"ask-{_slug(q)}.pdf", mime="application/pdf")
   ```
   (`tempfile` and `Path` are already imported at the top of the file. The checkbox keeps
   Chromium off the hot path — Ask answers render on every keystroke-run, so the PDF is built
   only when the user opts in. This code is only reachable for a real answer, since a
   `Clarification` already triggered `st.stop()` earlier in the block.)

- [ ] **Step 2: Verify the app still imports / byte-compiles**

Run: `python -m compileall -q app/streamlit_app.py && python -c "import ast, pathlib; ast.parse(pathlib.Path('app/streamlit_app.py').read_text()); print('app parses OK')"`
Expected: prints `app parses OK` (this is the same syntax gate `ci.yml` runs over `app/`).

- [ ] **Step 3: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(ask-pdf): Ask-lane 'Prepare PDF' download in the Streamlit console

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Re-label the optional-integration job + full verification

**Files:**
- Modify: `.github/workflows/optional-integration.yml` (comment line 27-28, job name line 30)

- [ ] **Step 1: Update the job description to Executive-Navy**

In `.github/workflows/optional-integration.yml`:
- Line 27-28 comment: change "renders the Signal-styled PDF" → "renders the Executive-Navy PDF".
- Line 30 `name:` → `name: ask briefing PDF (playwright + chromium)`.

(The job body already calls `render_briefing_pdf(result, …)` with a dict-shaped Q&A result — the
public API is unchanged, so it keeps working against the new design.)

- [ ] **Step 2: Run the full offline suite (the required gate)**

Run: `python -m pytest -p no:cacheprovider -q`
Expected: PASS — all tests, including the rewritten briefing tests, the new `exec_navy` /
`fpdf_base` / `caseboard_pdf` / `render_ask_pdf` / CLI tests, and the untouched build suite.

- [ ] **Step 3: Syntax gate (matches `ci.yml`)**

Run: `python -m compileall -q neuro_caseboard neuro_core app tests eval`
Expected: no output (clean exit 0).

- [ ] **Step 4: Manual exec-renderer spot-check (Chromium) — produces a real Executive-Navy PDF**

Run:
```bash
python - <<'PY'
import pathlib
from neuro_caseboard.briefing_pdf import render_briefing_pdf
result = {
    "answer": "### Indications\nDecompressive craniectomy relieves **refractory** ICP [1].\n\n- Flap ≥ 12×15 cm.",
    "citations": [{"n": 1, "book": "Greenberg", "chapter": "Trauma", "page": 1102}],
    "figures": [],
    "literature": {"narrative": "Recent RCTs support early decompression [L1].",
                   "citations": [{"n": 1, "title": "DECRA follow-up", "journal": "NEJM",
                                  "year": 2024, "doi": "10.1056/x", "url": ""}]},
}
out = pathlib.Path("ask-briefing-sample.pdf")
render_briefing_pdf(result, out, title="Decompressive hemicraniectomy", subtitle="worked example")
data = out.read_bytes()
assert data[:5].startswith(b"%PDF") and len(data) > 10_000, len(data)
print(f"rendered {len(data)} byte Executive-Navy ask PDF -> {out}")
PY
```
Expected: prints a byte count > 10 000. (Requires `pip install -e ".[briefing]" && playwright
install chromium`. If Chromium is unavailable in this environment, skip this step — the exec
render is exercised by `optional-integration.yml`; the offline path is already covered by the
suite.) Open `ask-briefing-sample.pdf` to confirm the navy masthead, the `Ask · Citation-grounded`
eyebrow, the Source-Serif answer column, the Sources + Contemporary Literature sections. Delete
the sample afterwards: `rm -f ask-briefing-sample.pdf`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/optional-integration.yml
git commit -m "ci: re-label the optional Q&A briefing PDF job (Executive-Navy)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (against `2026-06-16-ask-pdf-export-design.md`):
- §5.1 `exec_navy.py` extraction → Task 2. §5.2 `briefing_pdf.py` rewrite + `render_briefing_clinical_pdf` → Tasks 3 & 4. §5.3 `fpdf_base.py` → Task 1. §5.4 `render_ask_pdf` → Task 5.
- §6.1 CLI `ask --pdf`/`-o` → Task 6. §6.2 Streamlit "Prepare PDF" → Task 7.
- §7 design fidelity → Task 3 (masthead/eyebrow/title/answer column/Sources/Literature/figures/footer).
- §8 testing → tests in every task; build-side regression guarded by Tasks 1-2. §9 CI → Task 8.
- §10 risks: behavior-preserving extractions guarded by `test_render_pdf.py` (Task 1) and the new `test_caseboard_pdf.py` (Task 2).

**Placeholder scan:** the only intentional placeholder is the `EXEC_NAVY_CSS` body in Task 2 Step 3, explicitly flagged as a verbatim cut-and-paste from `caseboard_pdf.py` (the real source is in the repo) — not a content gap.

**Type/name consistency:** `register_fonts`/`ascii_fallback` (Task 1) used in Task 4; `EXEC_NAVY_CSS`/`inline`/`img_data_uri` (Task 2) used in Tasks 2-3; `build_briefing_html`/`render_briefing_pdf`/`render_briefing_clinical_pdf` (Tasks 3-4) used in Task 5; `render_ask_pdf` (Task 5) used in Tasks 6-7. `_g`, `_md_to_html`, `_md_lines`, `_plain`, `_fmt` all defined in `briefing_pdf.py` before use. `CASEBOARD_PDF_STYLE` and `_exec_renderer_unavailable` reused from existing `pipeline.py`.
