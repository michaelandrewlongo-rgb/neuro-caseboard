from __future__ import annotations

from eval.coverage import ANCHORS, score_board
from eval.monitor.baseline import is_regression
from eval.monitor.contracts import Evidence, Issue, RunArtifacts
from eval.monitor.fingerprint import fingerprint


class CoverageDropDetector:
    name = "coverage_drop"

    def __init__(self, *, rel_margin: float = 0.05, abs_floor: float = 0.70):
        self.rel_margin = rel_margin
        self.abs_floor = abs_floor

    def detect(self, art: RunArtifacts) -> list[Issue]:
        issues: list[Issue] = []
        for case in art.cases:
            cid = case["id"]
            items = ANCHORS.get(cid)
            boards = art.boards.get(cid)
            if not items or not boards:
                continue
            scored = [score_board(b, items) for b in boards]
            fracs = [len(cov) / len(items) for cov, _missing in scored]
            after = min(fracs)                       # worst-of-K
            _cov, missing = scored[fracs.index(after)]
            before = art.baseline.get(cid, {}).get("coverage")
            if not is_regression(before, after, rel_margin=self.rel_margin,
                                 abs_floor=self.abs_floor):
                continue
            signature = "|".join(sorted(missing))
            evidence = [Evidence(case_id=cid, detail=m, before=before, after=after)
                        for m in missing]
            issues.append(Issue(
                kind="coverage_drop",
                severity="high" if after < self.abs_floor else "medium",
                title=f"{cid}: coverage {after:.0%} ({len(missing)} must_cover missing)",
                evidence=evidence,
                locus="author (explore_llm.py)",
                proposed_tier="knob-only",
                proposed_fix=(
                    "Strengthen the author/critic prompt or ontology dimensions to cover: "
                    + ", ".join(missing[:3]) + ("…" if len(missing) > 3 else "")),
                fingerprint=fingerprint("coverage_drop", cid, signature),
            ))
        return issues
