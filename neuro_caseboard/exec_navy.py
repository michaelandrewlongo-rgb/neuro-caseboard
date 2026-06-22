"""Shared print theme — the single source of the brand for the PDF renderers
(caseboard_pdf.py build dossier + briefing_pdf.py Q&A briefing), mirroring the web console
(web/). The "Neo Brutalism" identity — white ground, black 2px borders, red/yellow/blue,
square corners, hard offset shadows, DM Sans + Space Mono — is defined here, in one place.

The symbol is still named ``EXEC_NAVY_CSS`` for import compatibility; its contents are the
current (brutalist) theme.
"""
from __future__ import annotations

import base64
import html
import os
import re


EXEC_NAVY_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=Space+Mono:wght@400;700&display=swap');
:root{
  --ink:#000000; --muted:#333333; --faint:#666666; --line:#000000; --line-soft:#000000;
  --accent:#ff3333; --accent-soft:#000000; --blue:#0066ff; --yellow:#ffff00;
  --supported:#1aa11a; --verify:#d97706; --quar:#ff3333;
  --supported-bg:#1aa11a; --verify-bg:#d97706;
  --ui:'DM Sans',system-ui,sans-serif; --read:'DM Sans',system-ui,sans-serif;
  --mono:'Space Mono',ui-monospace,monospace;
}
@page{ size:A4; margin:0; }
*{ box-sizing:border-box; }
html,body{ margin:0; background:#ffffff; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
body{ font-family:var(--ui); color:var(--ink); font-size:10.5pt; line-height:1.5;
  font-variant-numeric:tabular-nums; }

.masthead{ background:#ffffff; color:#000; padding:13mm 18mm 8mm; border-bottom:3px solid #000; }
.mh-brand{ display:flex; align-items:center; gap:9px; font-family:var(--ui); font-weight:700;
  font-size:14pt; letter-spacing:-.01em; }
.mh-brand .sq{ width:14px; height:14px; border-radius:0; background:var(--accent); border:2px solid #000; }
.mh-eyebrow{ font-family:var(--mono); font-size:7pt; font-weight:700; letter-spacing:.2em;
  text-transform:uppercase; color:var(--accent); margin-top:3.5mm; }

.content{ padding:8mm 18mm 0; }
.eyebrow{ display:inline-block; font-family:var(--mono); font-size:6.6pt; font-weight:700;
  letter-spacing:.2em; text-transform:uppercase; color:#000; border:2px solid #000;
  background:var(--yellow); border-radius:0; padding:1.1mm 2.4mm; }
h1.title{ font-family:var(--ui); font-weight:700; font-size:22pt; letter-spacing:-.02em; line-height:1.1;
  margin:4.5mm 0 2mm; color:#000; }
.standfirst{ font-family:var(--read); font-size:12pt; line-height:1.45; color:var(--muted);
  margin:0 0 4mm; max-width:165mm; }
.rule{ height:2px; background:#000; margin:5mm 0; }

.evbar{ display:flex; height:8px; border-radius:0; overflow:hidden; background:#f0f0f0;
  border:2px solid #000; margin:0 0 4mm; max-width:165mm; }
.evbar > span{ display:block; height:100%; }
.evbar > span + span{ border-left:2px solid #000; }
.metrics{ display:flex; gap:4mm; margin:0 0 3mm; }
.metric{ flex:1; border:2px solid #000; border-radius:0; padding:3mm 4mm;
  box-shadow:3px 3px 0 0 #000; }
.metric .v{ font-family:var(--ui); font-weight:700; font-size:16pt; line-height:1; color:#000; }
.metric .k{ font-family:var(--mono); font-size:6.2pt; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); margin-top:1.8mm; }
.metric.supported .v{ color:var(--supported); } .metric.verify .v{ color:var(--verify); }
.metric.quar .v{ color:var(--quar); }
.legend{ display:flex; gap:6mm; margin:0 0 1mm; font-family:var(--ui); font-size:8.4pt; color:var(--muted); }
.legend .item{ display:flex; align-items:center; gap:2mm; }
.legend .sw{ width:9px; height:9px; border-radius:0; border:1px solid #000; }

.section{ margin-top:7mm; }
.sec-h{ display:flex; align-items:center; gap:3mm; padding-top:3mm; border-top:2px solid #000;
  margin-bottom:3mm; break-after:avoid; }
.sec-h .k{ font-family:var(--mono); font-size:7pt; font-weight:700; letter-spacing:.12em; color:var(--accent); }
.sec-h .t{ font-family:var(--ui); font-weight:700; font-size:13pt; color:#000; letter-spacing:-.01em; }
.sec-h .ln{ flex:1; height:2px; background:#000; }
.sec-intro{ font-family:var(--read); color:var(--muted); margin:0 0 3mm; max-width:165mm; }

.claim{ border:2px solid #000; border-left:5px solid #000; border-radius:0;
  padding:3mm 4mm; margin-bottom:2.6mm; break-inside:avoid; box-shadow:3px 3px 0 0 #000; }
.claim.supported{ border-left-color:var(--supported); }
.claim.verify{ border-left-color:var(--verify); }
.marker{ display:inline-block; font-family:var(--mono); font-size:6.4pt; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; padding:1mm 2.6mm; border-radius:0; border:2px solid #000; margin-bottom:2mm; }
.marker.supported{ color:#fff; background:var(--supported); }
.marker.verify{ color:#fff; background:var(--verify); }
.claim .ctext{ font-family:var(--read); font-size:11pt; line-height:1.46; color:#000; }
.claim .ctext b{ color:#000; font-weight:700; }
.figref{ font-family:var(--mono); font-size:6.8pt; font-weight:700; color:var(--accent); white-space:nowrap; }
.why{ font-family:var(--read); font-size:9.8pt; line-height:1.42; color:var(--muted);
  border-left:3px solid #000; padding-left:3mm; margin-top:2mm; }
.why b{ font-family:var(--mono); font-size:6.4pt; letter-spacing:.1em; text-transform:uppercase;
  color:var(--accent); font-weight:700; margin-right:2mm; }
.subs{ margin:2mm 0 0; padding:0; }
.subs li{ list-style:none; font-family:var(--read); font-size:9.8pt; color:#000; margin:0 0 1mm; padding-left:6mm;
  text-indent:-6mm; }
.subs li::before{ content:"\\2610"; color:#000; margin-right:2.4mm; }
.xnote{ font-family:var(--read); font-style:italic; color:var(--muted); font-size:9.4pt;
  border-left:3px solid #000; padding-left:3mm; margin:2mm 0; }

figure{ break-inside:avoid; margin:0 0 4mm; border:2px solid #000; border-radius:0; overflow:hidden;
  box-shadow:3px 3px 0 0 #000; }
figure img{ display:block; width:100%; max-height:115mm; object-fit:contain; background:#f0f0f0;
  border-bottom:2px solid #000; }
figcaption{ padding:3mm 4mm; font-family:var(--read); font-size:9.6pt; line-height:1.4; color:var(--muted); }
figcaption .fid{ font-family:var(--mono); font-size:7pt; color:var(--accent); font-weight:700; margin-right:2mm; }
figcaption .rel{ display:block; margin-top:1.4mm; color:#000; }
figcaption .cite{ color:var(--faint); }

.appendix{ margin-top:7mm; }
.appendix .ap-h{ font-family:var(--ui); font-weight:700; font-size:10pt; color:#000; margin:3mm 0 1.5mm; }
.appendix ul{ margin:0 0 2mm; padding-left:5mm; }
.appendix li{ font-family:var(--read); font-size:9.4pt; color:var(--muted); margin-bottom:.8mm; }
.footer{ margin-top:8mm; padding:4mm 18mm 10mm; border-top:2px solid #000;
  font-family:var(--mono); font-size:7pt; letter-spacing:.04em; color:var(--faint); }
"""


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
