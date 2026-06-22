"""Tests for the guarded parallel benchmark runner.

Most cover the money paths as pure functions (gate arithmetic, round-robin split, shard merge) — no
Vertex, no psutil. The final class is one end-to-end orchestration test that drives the real
shard→subprocess→merge path against a STUB runner (still no Vertex), so the sharding actually
executes rather than only its logic being asserted.
"""
import json

from evaluation.scripts import run_benchmark_parallel as rbp
from evaluation.scripts.run_benchmark_parallel import (
    choose_n,
    merge_records,
    parse_jsonl_tolerant,
    round_robin_split,
)


class TestChooseN:
    def test_ample_ram_picks_two(self):
        # (14 - 2) / 5.5 = 2.18 -> 2, capped at N_MAX
        assert choose_n(14.0) == 2

    def test_two_worker_threshold_is_13gb(self):
        assert choose_n(13.0) == 2          # (13-2)/5.5 = 2.0
        assert choose_n(12.9) == 1          # (12.9-2)/5.5 = 1.98 -> 1

    def test_tight_ram_degrades_to_one(self):
        assert choose_n(9.0) == 1           # (9-2)/5.5 = 1.27 -> 1

    def test_one_worker_lower_boundary_is_7_5gb(self):
        assert choose_n(7.5) == 1           # (7.5-2)/5.5 = 1.0
        assert choose_n(7.4) == 0           # (7.4-2)/5.5 = 0.98 -> abort

    def test_starved_ram_aborts(self):
        assert choose_n(3.0) == 0
        assert choose_n(0.0) == 0

    def test_never_exceeds_cap_even_with_huge_ram(self):
        assert choose_n(512.0) == 2

    def test_cap_is_configurable(self):
        assert choose_n(512.0, n_max=4) == 4


class TestRoundRobinSplit:
    def test_interleaves_across_shards(self):
        assert round_robin_split(["a", "b", "c", "d", "e"], 2) == [["a", "c", "e"], ["b", "d"]]

    def test_single_shard_keeps_order(self):
        assert round_robin_split(["a", "b", "c"], 1) == [["a", "b", "c"]]

    def test_more_shards_than_ids_yields_empty_shard(self):
        # orchestrator skips empties; the split itself returns exactly n lists
        assert round_robin_split(["a"], 2) == [["a"], []]


class TestMergeRecords:
    def test_combines_distinct_ids_in_first_seen_order(self):
        merged = merge_records([
            [{"question_id": "A"}, {"question_id": "C"}],
            [{"question_id": "B"}],
        ])
        assert [r["question_id"] for r in merged] == ["A", "C", "B"]

    def test_dedups_by_question_id_last_wins(self):
        merged = merge_records([
            [{"question_id": "A", "v": 1}],
            [{"question_id": "A", "v": 2}],
        ])
        assert merged == [{"question_id": "A", "v": 2}]


class TestParseJsonlTolerant:
    def test_parses_clean_jsonl(self):
        recs = parse_jsonl_tolerant('{"question_id": "A"}\n{"question_id": "B"}\n')
        assert [r["question_id"] for r in recs] == ["A", "B"]

    def test_skips_partial_trailing_line(self):
        # a crash mid-write leaves a truncated last line; resume must not choke on it
        recs = parse_jsonl_tolerant('{"question_id": "A"}\n{"quest')
        assert [r["question_id"] for r in recs] == ["A"]

    def test_skips_blank_lines(self):
        recs = parse_jsonl_tolerant('\n{"question_id": "A"}\n\n')
        assert [r["question_id"] for r in recs] == ["A"]


# A tiny stand-in for run_benchmark.py: writes one record to its --run-dir/run.jsonl per call.
# Lets us drive the real orchestration (gate → shard → subprocess → merge) with no Vertex/index.
_STUB_RUNNER = (
    "import argparse, json, pathlib\n"
    "ap = argparse.ArgumentParser()\n"
    "ap.add_argument('--run-dir'); ap.add_argument('--start-id'); ap.add_argument('--end-id')\n"
    "ap.add_argument('--resume', action='store_true')\n"
    "a = ap.parse_args()\n"
    "p = pathlib.Path(a.run_dir); p.mkdir(parents=True, exist_ok=True)\n"
    "with (p / 'run.jsonl').open('a') as f:\n"
    "    f.write(json.dumps({'question_id': a.start_id, 'answer': 'stub'}) + '\\n')\n"
)


class TestOrchestrationEndToEnd:
    def test_shards_run_and_merge(self, tmp_path, monkeypatch):
        stub = tmp_path / "stub_runner.py"
        stub.write_text(_STUB_RUNNER)
        monkeypatch.setattr(rbp, "RUNNER", stub)
        monkeypatch.setattr(rbp, "available_gb", lambda: 14.0)   # ample → N=2
        run = tmp_path / "run"
        rc = rbp.main(["--run-dir", str(run), "--ids", "A B C D E"])
        assert rc == 0
        # both shard dirs were created and the merge has every id exactly once
        assert (run / "shard-0").is_dir() and (run / "shard-1").is_dir()
        merged = [json.loads(line) for line in (run / "run.jsonl").read_text().splitlines()]
        assert sorted(r["question_id"] for r in merged) == ["A", "B", "C", "D", "E"]

    def test_aborts_when_memory_starved(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rbp, "available_gb", lambda: 6.0)    # < peak+cushion → N=0 → abort
        rc = rbp.main(["--run-dir", str(tmp_path / "run"), "--ids", "A B"])
        assert rc == 2
        assert not (tmp_path / "run" / "run.jsonl").exists()      # nothing run on abort
