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


def main(argv=None) -> int:
    import argparse
    import datetime
    import subprocess

    from eval.coverage import HERE as EVAL_DIR
    from eval.monitor.baseline import load_baseline
    from eval.monitor.detectors.coverage_drop import CoverageDropDetector
    from eval.monitor.digest import render_digest
    from eval.monitor.suppress import filter_suppressed, load_suppressions

    mon = Path(__file__).parent
    ap = argparse.ArgumentParser(description="Eval monitor — detection sweep")
    ap.add_argument("--k", type=int, default=3, help="builds per case (worst-of-K)")
    ap.add_argument("--cases", default=str(EVAL_DIR / "cases.json"))
    ap.add_argument("--baseline", default=str(mon / "baseline.json"))
    ap.add_argument("--suppressions", default=str(mon / "suppressions.json"))
    ap.add_argument("--issues-dir", default=str(mon / "issues"))
    args = ap.parse_args(argv)

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    baseline = load_baseline(args.baseline)
    suppressed = load_suppressions(args.suppressions)

    issues = run_detection(
        cases, baseline, [CoverageDropDetector()],
        k=args.k, build_fn=default_build_fn)
    issues = filter_suppressed(issues, suppressed)

    run_id = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        git_sha = "unknown"
    write_cards(issues, args.issues_dir, run_id=run_id, git_sha=git_sha)
    Path(args.issues_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.issues_dir) / "digest.md").write_text(
        render_digest(issues), encoding="utf-8")
    print(f"[monitor] {len(issues)} issue(s); digest at {args.issues_dir}/digest.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
