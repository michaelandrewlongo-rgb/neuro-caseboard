"""Shared print theme — the single source of the brand for the PDF renderers
(caseboard_pdf.py build dossier + briefing_pdf.py Q&A briefing), mirroring the web console
(web/). The theme is **token-driven**: one modern structural CSS body that references only
``var(--…)`` tokens, fed a ``:root{…}`` token block chosen at render time by ``base_css(theme)``.

Two token sets mirror the web ``@theme``: ``SIGNAL`` (dark, screen — the default identity) and
``PRINT`` (light, ink-friendly, no gradients). The module constant ``EXEC_NAVY_CSS`` is kept for
import compatibility and equals ``base_css("signal")``.
"""
from __future__ import annotations

import base64
import html
import os
import re


SIGNAL_TOKENS = """:root{
  --bg:#000000; --panel:#0a0a0a; --panel-grad:linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,.012));
  --ink:#ededed; --muted:#8a8a8a; --faint:#6b6b6b;
  --line:rgba(255,255,255,.09);
  --accent:#6b93ff; --blue:#6b93ff; --yellow:#ffc94d;
  --supported:#34e07f; --verify:#ffc94d; --quar:#ff5a5a;
  --ui:'DM Sans',system-ui,sans-serif; --read:'DM Sans',system-ui,sans-serif; --mono:'Space Mono',ui-monospace,monospace;
  --radius:7px; --border:1px;
}"""
PRINT_TOKENS = """:root{
  --bg:#ffffff; --panel:#fafafa; --panel-grad:none;
  --ink:#1a1a1a; --muted:#555555; --faint:#777777;
  --line:#e5e5e5;
  --accent:#2a52cc; --blue:#2a52cc; --yellow:#b45309;
  --supported:#1a7f4b; --verify:#b45309; --quar:#c8102e;
  --ui:'DM Sans',system-ui,sans-serif; --read:'DM Sans',system-ui,sans-serif; --mono:'Space Mono',ui-monospace,monospace;
  --radius:7px; --border:1px;
}"""

_STRUCTURE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=Space+Mono:wght@400;700&display=swap');
@page{ size:A4; margin:0; }
*{ box-sizing:border-box; }
html,body{ margin:0; background:var(--bg); -webkit-print-color-adjust:exact; print-color-adjust:exact; }
body{ font-family:var(--ui); color:var(--ink); font-size:10.5pt; line-height:1.5;
  font-variant-numeric:tabular-nums; }

.masthead{ background:var(--panel); background-image:var(--panel-grad); color:var(--ink);
  padding:13mm 18mm 8mm; border-bottom:var(--border) solid var(--line); }
.mh-brand{ display:flex; align-items:center; gap:9px; font-family:var(--ui); font-weight:700;
  font-size:14pt; letter-spacing:-.01em; }
.mh-brand .sq{ width:14px; height:14px; border-radius:var(--radius); background:var(--accent);
  border:var(--border) solid var(--line); }
.mh-eyebrow{ font-family:var(--mono); font-size:7pt; font-weight:700; letter-spacing:.2em;
  text-transform:uppercase; color:var(--accent); margin-top:3.5mm; }

.content{ padding:8mm 18mm 0; }
.eyebrow{ display:inline-block; font-family:var(--mono); font-size:6.6pt; font-weight:700;
  letter-spacing:.2em; text-transform:uppercase; color:var(--accent);
  border:var(--border) solid var(--line); background:transparent; border-radius:var(--radius);
  padding:1.1mm 2.4mm; }
h1.title{ font-family:var(--ui); font-weight:700; font-size:22pt; letter-spacing:-.02em; line-height:1.1;
  margin:4.5mm 0 2mm; color:var(--ink); }
.standfirst{ font-family:var(--read); font-size:12pt; line-height:1.45; color:var(--muted);
  margin:0 0 4mm; max-width:165mm; }
.rule{ height:var(--border); background:var(--line); margin:5mm 0; }

.evbar{ display:flex; height:8px; border-radius:var(--radius); overflow:hidden; background:var(--panel);
  border:var(--border) solid var(--line); margin:0 0 4mm; max-width:165mm; }
.evbar > span{ display:block; height:100%; }
.evbar > span + span{ border-left:var(--border) solid var(--line); }
.metrics{ display:flex; gap:4mm; margin:0 0 3mm; }
.metric{ flex:1; background:var(--panel); background-image:var(--panel-grad);
  border:var(--border) solid var(--line); border-radius:var(--radius); padding:3mm 4mm; }
.metric .v{ font-family:var(--ui); font-weight:700; font-size:16pt; line-height:1; color:var(--ink); }
.metric .k{ font-family:var(--mono); font-size:6.2pt; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); margin-top:1.8mm; }
.metric.supported .v{ color:var(--supported); } .metric.verify .v{ color:var(--verify); }
.metric.quar .v{ color:var(--quar); }
.legend{ display:flex; gap:6mm; margin:0 0 1mm; font-family:var(--ui); font-size:8.4pt; color:var(--muted); }
.legend .item{ display:flex; align-items:center; gap:2mm; }
.legend .sw{ width:9px; height:9px; border-radius:var(--radius); border:var(--border) solid var(--line); }

.section{ margin-top:7mm; }
.sec-h{ display:flex; align-items:center; gap:3mm; padding-top:3mm; border-top:var(--border) solid var(--line);
  margin-bottom:3mm; break-after:avoid; }
.sec-h .k{ font-family:var(--mono); font-size:7pt; font-weight:700; letter-spacing:.12em; color:var(--accent); }
.sec-h .t{ font-family:var(--ui); font-weight:700; font-size:13pt; color:var(--ink); letter-spacing:-.01em; }
.sec-h .ln{ flex:1; height:var(--border); background:var(--line); }
.sec-intro{ font-family:var(--read); color:var(--muted); margin:0 0 3mm; max-width:165mm; }

.claim{ background:var(--panel); background-image:var(--panel-grad);
  border:var(--border) solid var(--line); border-left:4px solid var(--line); border-radius:var(--radius);
  padding:3mm 4mm; margin-bottom:2.6mm; break-inside:avoid; }
.claim.supported{ border-left-color:var(--supported); }
.claim.verify{ border-left-color:var(--verify); }
.marker{ display:inline-block; font-family:var(--mono); font-size:6.4pt; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; padding:1mm 2.6mm; border-radius:var(--radius);
  border:var(--border) solid var(--line); margin-bottom:2mm; }
.marker.supported{ color:var(--bg); background:var(--supported); }
.marker.verify{ color:var(--bg); background:var(--verify); }
.claim .ctext{ font-family:var(--read); font-size:11pt; line-height:1.46; color:var(--ink); }
.claim .ctext b{ color:var(--ink); font-weight:700; }
.figref{ font-family:var(--mono); font-size:6.8pt; font-weight:700; color:var(--accent); white-space:nowrap; }
.why{ font-family:var(--read); font-size:9.8pt; line-height:1.42; color:var(--muted);
  border-left:3px solid var(--line); padding-left:3mm; margin-top:2mm; }
.why b{ font-family:var(--mono); font-size:6.4pt; letter-spacing:.1em; text-transform:uppercase;
  color:var(--accent); font-weight:700; margin-right:2mm; }
.subs{ margin:2mm 0 0; padding:0; }
.subs li{ list-style:none; font-family:var(--read); font-size:9.8pt; color:var(--ink); margin:0 0 1mm; padding-left:6mm;
  text-indent:-6mm; }
.subs li::before{ content:"\\2610"; color:var(--ink); margin-right:2.4mm; }
.xnote{ font-family:var(--read); font-style:italic; color:var(--muted); font-size:9.4pt;
  border-left:3px solid var(--line); padding-left:3mm; margin:2mm 0; }

figure{ break-inside:avoid; margin:0 0 4mm; background:var(--panel); background-image:var(--panel-grad);
  border:var(--border) solid var(--line); border-radius:var(--radius); overflow:hidden; }
figure img{ display:block; width:100%; max-height:115mm; object-fit:contain; background:var(--panel);
  border-bottom:var(--border) solid var(--line); }
figcaption{ padding:3mm 4mm; font-family:var(--read); font-size:9.6pt; line-height:1.4; color:var(--muted); }
figcaption .fid{ font-family:var(--mono); font-size:7pt; color:var(--accent); font-weight:700; margin-right:2mm; }
figcaption .rel{ display:block; margin-top:1.4mm; color:var(--ink); }
figcaption .cite{ color:var(--faint); }

.appendix{ margin-top:7mm; }
.appendix .ap-h{ font-family:var(--ui); font-weight:700; font-size:10pt; color:var(--ink); margin:3mm 0 1.5mm; }
.appendix ul{ margin:0 0 2mm; padding-left:5mm; }
.appendix li{ font-family:var(--read); font-size:9.4pt; color:var(--muted); margin-bottom:.8mm; }
.footer{ margin-top:8mm; padding:4mm 18mm 10mm; border-top:var(--border) solid var(--line);
  font-family:var(--mono); font-size:7pt; letter-spacing:.04em; color:var(--faint); }
"""


def base_css(theme: str = "signal") -> str:
    """Return the full stylesheet for ``theme`` — a ``:root`` token block + the structural body.

    ``theme`` in ``{"signal","print"}``; any other value (incl. legacy ``"exec"``) → ``"signal"``.
    """
    tokens = PRINT_TOKENS if theme == "print" else SIGNAL_TOKENS
    return tokens + _STRUCTURE_CSS


EXEC_NAVY_CSS = base_css("signal")


def inline(text: str) -> str:
    """Escape, then promote ``**bold**`` to <b> (the only inline markup claims/why use)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text or ""))


def img_data_uri(path: str) -> str:
    """Return a ``data:`` URI for the image at ``path`` (MIME derived from the filename)."""
    # `path` is the absolute build-time host path stored in the figures index; when the assets
    # tree is mounted elsewhere at runtime (container: /data/figures) the literal open() fails.
    # Resolve to the runtime ASSETS_DIR first — the same reroot the retrieval/serve/PDF lanes
    # use — so a remapped mount doesn't silently drop the plate. (Idempotent on native runs.)
    from neuro_core.asset_paths import resolve_asset_path
    from neuro_core.config import load_config
    resolved = resolve_asset_path(path, load_config().assets_dir)
    # Derive the extension from the basename only — a dot in a parent dir (e.g. /data/v1.2/figA)
    # or a missing extension must not corrupt the MIME type.
    name = os.path.basename(path)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, f"image/{ext}")
    with open(resolved, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
