"""Shared Executive-Navy print theme — the single source of the brand for the PDF renderers
(caseboard_pdf.py build dossier + briefing_pdf.py Q&A briefing), mirroring the web console
(app/signal_theme.py). The navy/teal/Source-Serif identity is defined here, in one place.
"""
from __future__ import annotations

import base64
import html
import os
import re


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
@page{ size:A4; margin:0; }
*{ box-sizing:border-box; }
html,body{ margin:0; background:#ffffff; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
body{ font-family:var(--ui); color:var(--ink); font-size:10.5pt; line-height:1.5;
  font-variant-numeric:tabular-nums; }

.masthead{ background:linear-gradient(105deg,#0c1626 0%,#0a1320 100%); color:#eef3f8; padding:13mm 18mm 9mm; }
.mh-brand{ display:flex; align-items:center; gap:9px; font-family:var(--ui); font-weight:800;
  font-size:13.5pt; letter-spacing:-.01em; }
.mh-brand .sq{ width:13px; height:13px; border-radius:3px; background:#2bc4d4; }
.mh-eyebrow{ font-family:var(--mono); font-size:7pt; letter-spacing:.2em; text-transform:uppercase;
  color:#9fb0c4; margin-top:3.5mm; }

.content{ padding:8mm 18mm 0; }
.eyebrow{ display:inline-block; font-family:var(--mono); font-size:6.6pt; font-weight:600;
  letter-spacing:.2em; text-transform:uppercase; color:var(--accent); border:1px solid rgba(14,116,144,.28);
  background:rgba(14,116,144,.06); border-radius:4px; padding:1.1mm 2.4mm; }
h1.title{ font-family:var(--ui); font-weight:700; font-size:21pt; letter-spacing:-.02em; line-height:1.12;
  margin:4.5mm 0 2mm; color:var(--ink); }
.standfirst{ font-family:var(--read); font-size:12pt; line-height:1.45; color:var(--muted);
  margin:0 0 4mm; max-width:165mm; }
.rule{ height:1px; background:var(--line); margin:5mm 0; }

.evbar{ display:flex; height:7px; border-radius:999px; overflow:hidden; background:var(--line-soft);
  box-shadow:inset 0 0 0 1px rgba(16,32,48,.06); margin:0 0 4mm; max-width:165mm; }
.evbar > span{ display:block; height:100%; }
.evbar > span + span{ box-shadow:inset 1px 0 0 rgba(255,255,255,.7); }
.metrics{ display:flex; gap:4mm; margin:0 0 3mm; }
.metric{ flex:1; border:1px solid var(--line); border-radius:10px; padding:3mm 4mm;
  box-shadow:0 1px 2px rgba(16,32,48,.04); }
.metric .v{ font-family:var(--ui); font-weight:700; font-size:16pt; line-height:1; color:var(--ink); }
.metric .k{ font-family:var(--mono); font-size:6.2pt; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); margin-top:1.8mm; }
.metric.supported .v{ color:var(--supported); } .metric.verify .v{ color:var(--verify); }
.metric.quar .v{ color:var(--quar); }
.legend{ display:flex; gap:6mm; margin:0 0 1mm; font-family:var(--ui); font-size:8.4pt; color:var(--muted); }
.legend .item{ display:flex; align-items:center; gap:2mm; }
.legend .sw{ width:8px; height:8px; border-radius:50%; }

.section{ margin-top:7mm; }
.sec-h{ display:flex; align-items:center; gap:3mm; padding-top:3mm; border-top:1px solid var(--line);
  margin-bottom:3mm; break-after:avoid; }
.sec-h .k{ font-family:var(--mono); font-size:7pt; font-weight:600; letter-spacing:.12em; color:var(--accent); }
.sec-h .t{ font-family:var(--ui); font-weight:700; font-size:13pt; color:var(--ink); letter-spacing:-.01em; }
.sec-h .ln{ flex:1; height:1px; background:var(--line); }
.sec-intro{ font-family:var(--read); font-style:italic; color:var(--muted); margin:0 0 3mm; max-width:165mm; }

.claim{ border:1px solid var(--line); border-left:3px solid var(--line); border-radius:9px;
  padding:3mm 4mm; margin-bottom:2.6mm; break-inside:avoid; box-shadow:0 1px 2px rgba(16,32,48,.04); }
.claim.supported{ border-left-color:var(--supported); }
.claim.verify{ border-left-color:var(--verify); }
.marker{ display:inline-block; font-family:var(--mono); font-size:6.4pt; font-weight:600; letter-spacing:.1em;
  text-transform:uppercase; padding:1mm 2.6mm; border-radius:999px; margin-bottom:2mm; }
.marker.supported{ color:var(--supported); background:var(--supported-bg); }
.marker.verify{ color:var(--verify); background:var(--verify-bg); }
.claim .ctext{ font-family:var(--read); font-size:11pt; line-height:1.46; color:#1e2a36; }
.claim .ctext b{ color:#0c2233; font-weight:600; }
.figref{ font-family:var(--mono); font-size:6.8pt; color:var(--accent); white-space:nowrap; }
.why{ font-family:var(--read); font-size:9.8pt; line-height:1.42; color:var(--muted);
  border-left:2px solid var(--accent-soft); padding-left:3mm; margin-top:2mm; }
.why b{ font-family:var(--mono); font-size:6.4pt; letter-spacing:.1em; text-transform:uppercase;
  color:var(--accent); font-weight:600; margin-right:2mm; }
.subs{ margin:2mm 0 0; padding:0; }
.subs li{ list-style:none; font-family:var(--read); font-size:9.8pt; color:#33424f; margin:0 0 1mm; padding-left:6mm;
  text-indent:-6mm; }
.subs li::before{ content:"\\2610"; color:var(--accent); margin-right:2.4mm; }
.xnote{ font-family:var(--read); font-style:italic; color:var(--muted); font-size:9.4pt;
  border-left:2px solid var(--line); padding-left:3mm; margin:2mm 0; }

figure{ break-inside:avoid; margin:0 0 4mm; border:1px solid var(--line); border-radius:11px; overflow:hidden;
  box-shadow:0 1px 2px rgba(16,32,48,.04); }
figure img{ display:block; width:100%; max-height:115mm; object-fit:contain; background:#f3f5f7; }
figcaption{ padding:3mm 4mm; font-family:var(--read); font-size:9.6pt; line-height:1.4; color:var(--muted); }
figcaption .fid{ font-family:var(--mono); font-size:7pt; color:var(--accent); font-weight:600; margin-right:2mm; }
figcaption .rel{ display:block; margin-top:1.4mm; color:#33424f; }
figcaption .cite{ color:var(--faint); }

.appendix{ margin-top:7mm; }
.appendix .ap-h{ font-family:var(--ui); font-weight:700; font-size:10pt; color:var(--ink); margin:3mm 0 1.5mm; }
.appendix ul{ margin:0 0 2mm; padding-left:5mm; }
.appendix li{ font-family:var(--read); font-size:9.4pt; color:var(--muted); margin-bottom:.8mm; }
.footer{ margin-top:8mm; padding:4mm 18mm 10mm; border-top:1px solid var(--line);
  font-family:var(--mono); font-size:7pt; letter-spacing:.04em; color:var(--faint); }
"""


def inline(text: str) -> str:
    """Escape, then promote ``**bold**`` to <b> (the only inline markup claims/why use)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text or ""))


def img_data_uri(path: str) -> str:
    """Return a ``data:`` URI for the image at ``path`` (MIME derived from the filename)."""
    # Derive the extension from the basename only — a dot in a parent dir (e.g. /data/v1.2/figA)
    # or a missing extension must not corrupt the MIME type.
    name = os.path.basename(path)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, f"image/{ext}")
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
