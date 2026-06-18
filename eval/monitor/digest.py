from __future__ import annotations

from eval.monitor.contracts import Issue

_ORDER = {"high": 0, "medium": 1, "low": 2}


def render_digest(issues: list[Issue]) -> str:
    if not issues:
        return "# Monitor digest\n\nNo new issues. ✓\n"
    lines = ["# Monitor digest", "", f"{len(issues)} new issue(s):", ""]
    for iss in sorted(issues, key=lambda i: _ORDER.get(i.severity, 3)):
        lines.append(f"## [{iss.severity}] {iss.title}")
        lines.append(
            f"- **kind:** {iss.kind} · **locus:** {iss.locus} "
            f"· **proposed tier:** {iss.proposed_tier} · **fingerprint:** `{iss.fingerprint}`")
        lines.append(f"- **proposed fix:** {iss.proposed_fix}")
        for ev in iss.evidence:
            before = "—" if ev.before is None else f"{ev.before:.0%}"
            after = "—" if ev.after is None else f"{ev.after:.0%}"
            lines.append(f"  - {ev.case_id}: {ev.detail}  ({before} → {after})")
        lines.append("")
    return "\n".join(lines)
