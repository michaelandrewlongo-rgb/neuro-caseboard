from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from eval.monitor.contracts import Issue, RunArtifacts


def default_build_fn(case_query: str) -> str:
    from neuro_caseboard.pipeline import build_dossier
    from neuro_caseboard.render_md import render_markdown
    return render_markdown(build_dossier(case_query))


def build_boards(case_query: str, k: int, build_fn) -> list[str]:
    return [build_fn(case_query) for _ in range(k)]


def run_detection(cases: list[dict], baseline: dict, detectors: list, *,
                  k: int, build_fn) -> list[Issue]:
    boards = {c["id"]: build_boards(c["case_query"], k, build_fn) for c in cases}
    art = RunArtifacts(cases=cases, boards=boards, baseline=baseline)
    issues: list[Issue] = []
    for detector in detectors:
        issues.extend(detector.detect(art))
    return issues


def write_cards(issues: list[Issue], issues_dir, *, run_id: str,
                git_sha: str) -> list[Path]:
    out = Path(issues_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for iss in issues:
        card = dataclasses.asdict(iss)
        card["status"] = "new"
        card["provenance"] = {"run_id": run_id, "git_sha": git_sha}
        path = out / f"{iss.fingerprint}.json"
        path.write_text(json.dumps(card, indent=2), encoding="utf-8")
        paths.append(path)
    return paths
