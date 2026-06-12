"""Markdown renderer for a Dossier.

Owns defect #4 (legend) and the textual side of #1/#5/#6/#7/#8/#9. The structured
fixes already live in the Dossier; this just lays them out so the actionable claim
scans first and the rationale sits on its own line.
"""

from __future__ import annotations

from neuro_caseboard.model import Dossier, MARK


def _legend() -> str:
    return f"**Markers:** {MARK['supported']} corpus-supported   {MARK['verify']} needs clinician verification"


def _summary(s) -> str:
    return (f"**Evidence:** {MARK['supported']} {s.supported} corpus-supported · "
            f"{MARK['verify']} {s.verify} need verification · "
            f"{s.quarantined} quarantined · "
            f"{s.no_evidence} no retrievable evidence")


def render_markdown(dossier: Dossier) -> str:
    L: list[str] = [f"# {dossier.title}", "", _legend(), "", _summary(dossier.summary), ""]

    has_appendix = not dossier.appendix.is_empty()
    if has_appendix:
        L += ["_See the appendix for evidence sources and off-target claims._", ""]

    for sec in dossier.sections:
        L.append(f"## {sec.heading}")
        if sec.intro:
            L.append(f"*{sec.intro}*")
        L.append("")
        for c in sec.claims:
            mark = MARK.get(c.status, "")
            figref = ""
            if c.figure_ids:
                figref = "  (see " + ", ".join(f"Fig {fid}" for fid in c.figure_ids) + ")"
            L.append(f"- {mark} {c.text}{figref}")
            if c.why:
                L.append(f"  - *Why:* {c.why}")
            for item in c.sub_items:
                L.append(f"  - [ ] {item}")
            L.append("")
        if sec.figures:
            L.append("**Figures**")
            for fig in sec.figures:
                L.append(f"- **Fig {fig.fig_id}** — {fig.caption}")
                if fig.relevance:
                    L.append(f"  - {fig.relevance}")
                if fig.claim_ref:
                    L.append(f'  - supports: "{fig.claim_ref}"')
                L.append(f"  - ![{fig.fig_id}]({fig.image_path})")
            L.append("")
        for ref in sec.cross_refs:
            L.append(f"> {ref}")
        if sec.cross_refs:
            L.append("")

    if has_appendix:
        L += ["---", "", "## Appendix — evidence sources & off-target claims", ""]
        for e in dossier.appendix.entries:
            L.append(f"### {e.heading}")
            for it in e.items:
                L.append(f"- {it}")
            for sr in e.sources:
                L.append(f"- {sr}")
            L.append("")

    return "\n".join(L).rstrip() + "\n"
