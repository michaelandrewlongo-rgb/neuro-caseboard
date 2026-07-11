"""Lane C: frozen full-text journal-literature corpus retrieval (SQLite FTS5, ``[D#]``).

A third evidence lane for the woven Ask path, alongside the textbook lane ([n]) and the
PubMed lane ([L#]). Sources are 10 subspecialty SQLite DBs of section-tagged neurosurgery
full text through March 2026 (no embeddings) — so retrieval is BM25 over a *contentless*
FTS5 sidecar built by ``scripts/build_corpus_fts.py``. The matched rowid is joined back to
the read-only source for content + work metadata.

Additive and failure-safe by design: disabled unless ``CORPUS_RETRIEVAL`` is on, and any
error (missing sidecar, locked DB, bad query) yields ``[]`` so Lane A is never blocked.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

# cerebrovascular-relevant subspecialties (see cv-curric/BUILD_STATE.md "only use relevant data").
RELEVANT_DBS = ["cerebrovascular", "neurointerventional", "radiosurgery", "neurocritical_care",
                "trauma_general", "pediatrics", "tumor_skull_base",
                "spine", "functional_epilepsy", "peripheral_nerve"]

# Phase 2.1 domain router: map a question to the subspecialty corpora worth querying, so the [D#]
# lane does not pull (say) a stroke trial into a spine answer — the documented crowding regression.
# Keyword-only (deterministic, no LLM). Recall-safe: a question matching nothing queries ALL DBs.
_DOMAIN_KEYWORDS = {
    "cerebrovascular": ("aneurysm", "avm", "arteriovenous", "subarachnoid", " sah", "moyamoya",
                        "cavernoma", "cavernous malformation", "bypass", "carotid", "vascular",
                        "hemorrhage", "haemorrhage", "vasospasm", "dural fistula"),
    "neurointerventional": ("thrombectomy", "embolization", "embolisation", "coiling", "flow divert",
                            "stent", "endovascular", "large vessel occlusion", " lvo", "aspiration",
                            "middle meningeal"),
    "radiosurgery": ("radiosurgery", "gamma knife", " srs", "stereotactic radiation", "cyberknife"),
    "neurocritical_care": (" icp", "intracranial pressure", "neurocritical", " icu", "ventilator",
                           "status epilepticus", "hyperosmolar", "cerebral edema"),
    "trauma_general": ("trauma", " tbi", "head injury", "traumatic brain", " gcs", "decompressive",
                       "contusion", "epidural hematoma", "subdural"),
    "pediatrics": ("pediatric", "paediatric", "child", "infant", "congenital", "neonat"),
    "tumor_skull_base": ("tumor", "tumour", "glioma", "glioblastoma", " gbm", "meningioma",
                         "schwannoma", "metastas", "skull base", "pituitary", "adenoma",
                         "vestibular", "chordoma", "ependymoma"),
    "spine": ("spine", "spinal", "vertebr", "fusion", "discectomy", "laminectomy", "cervical",
              "lumbar", "thoracic", "myelopathy", "scoliosis", "stenosis", "spondyl", "corpectomy",
              "pedicle"),
    "functional_epilepsy": ("epilepsy", "seizure", " dbs", "deep brain", "parkinson", "tremor",
                            "functional neurosurg", "movement disorder", "dystonia", "vagus nerve"),
    "peripheral_nerve": ("peripheral nerve", "carpal tunnel", "ulnar", "brachial plexus",
                         "entrapment", "cubital", "nerve graft", "neuroma"),
}


def route_domains(question: str, available: "list[str]") -> "list[str]":
    """The subset of ``available`` DBs whose keywords appear in ``question``. Recall-safe: no match
    -> all available (never returns []). Deterministic; used to scope the [D#] lane per question."""
    q = f" {(question or '').lower()} "
    hit = [db for db in available if db in _DOMAIN_KEYWORDS
           and any(k in q for k in _DOMAIN_KEYWORDS[db])]
    return hit or list(available)

# Evidence sections weigh more than framing sections; title/intro/other weigh less.
_SECTION_BOOST = {"results": 1.15, "conclusion": 1.15, "methods": 1.08, "discussion": 1.08,
                  "case_report": 1.0, "abstract": 0.95, "introduction": 0.75, "title": 0.6,
                  "other": 0.85}

_STOP = set(
    "a an the of and or to in for with without on at by from as is are was were be been being "
    "this that these those it its their his her our your they we you i he she them us who whom "
    "which what when where why how not no nor but if then than so such can could may might must "
    "will would should do does did done have has had having between during within into over "
    "under about above below after before more most less least also both each any all some "
    "vs versus using use used via per case cases study studies group groups patient patients "
    "result results method methods conclusion background objective purpose aim aims "
    # pedagogical wrapper words — never let curriculum framing steer clinical retrieval
    "teach teaching learner learners student students curriculum lesson competency competencies "
    "master mastery level levels awareness education educational trainee write cover section "
    "header headers depth appropriate scaffold framework expand verify ratify skeleton".split())


def _flag(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class CorpusConfig:
    enabled: bool
    fts_dir: str
    source_dir: str
    dbs: list
    k: int
    per_db_candidates: int
    max_per_work: int
    excerpt_chars: int


def load_corpus_config() -> "CorpusConfig":
    # Reuse the literature lane's dependency-free .env loader (real env always wins).
    from neuro_caseboard.literature.config import _load_dotenv_once
    _load_dotenv_once()
    dbs = [s.strip() for s in os.environ.get("CORPUS_DBS", "").split(",") if s.strip()]
    return CorpusConfig(
        enabled=_flag(os.environ.get("CORPUS_RETRIEVAL", "false")),
        fts_dir=os.environ.get("CORPUS_FTS_DIR",
                               str(Path.home() / ".cache" / "neuro_caseboard" / "corpus_fts")),
        source_dir=os.environ.get("CORPUS_SOURCE_DIR", "/mnt/c/dev/NSGY_DB_lean/fulltext"),
        dbs=dbs or list(RELEVANT_DBS),
        k=int(os.environ.get("CORPUS_K", "10")),
        per_db_candidates=int(os.environ.get("CORPUS_PER_DB_CANDIDATES", "40")),
        max_per_work=int(os.environ.get("CORPUS_MAX_PER_WORK", "1")),
        excerpt_chars=int(os.environ.get("CORPUS_EXCERPT_CHARS", "700")),
    )


@dataclass
class CorpusRecord:
    work_id: str
    title: str
    journal: str
    year: "int | None"
    study_design: str
    section_type: str
    content: str
    pmid: str = ""
    doi: str = ""
    source_db: str = ""
    score: float = 0.0


def _fts_match_query(question: str) -> "str | None":
    """Salient content terms OR'd into an FTS5 MATCH string; each term double-quoted so
    hyphens/punctuation are treated as literal phrases, never FTS operators."""
    seen, out = set(), []
    for t in re.findall(r"[a-z][a-z0-9\-]{2,}", (question or "").lower()):
        if t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append('"%s"' % t.replace('"', ""))
        if len(out) >= 14:
            break
    return " OR ".join(out) if out else None


def _query_db(name: str, cfg: "CorpusConfig", match: str) -> list:
    src = Path(cfg.source_dir) / f"{name}_fulltext.sqlite"
    fts = Path(cfg.fts_dir) / f"{name}_fts.sqlite"
    if not src.exists() or not fts.exists():
        return []
    try:
        # Open the FTS sidecar as main so bm25(passages_fts) is unambiguous; attach source ro.
        con = sqlite3.connect(f"file:{fts}?mode=ro", uri=True)
        con.execute("ATTACH DATABASE ? AS src", (f"file:{src}?mode=ro",))
    except sqlite3.Error:
        return []
    try:
        hits = con.execute(
            "SELECT rowid, bm25(passages_fts) FROM passages_fts "
            "WHERE passages_fts MATCH ? ORDER BY 2 LIMIT ?",
            (match, cfg.per_db_candidates)).fetchall()
        if not hits:
            return []
        score_by_rowid = {rid: s for rid, s in hits}
        ph = ",".join("?" * len(score_by_rowid))
        meta = con.execute(
            "SELECT tp.rowid, tp.work_id, tp.section_type, tp.content, "
            "       w.title, w.journal_title, w.pub_year, w.study_design "
            "FROM src.text_passages tp JOIN src.works w ON w.id = tp.work_id "
            f"WHERE tp.rowid IN ({ph})", list(score_by_rowid)).fetchall()
    except sqlite3.Error:
        _log.debug("corpus query failed for %s", name, exc_info=True)
        return []
    finally:
        con.close()

    out = []
    for rowid, work_id, sect, content, title, journal, year, design in meta:
        boost = _SECTION_BOOST.get((sect or "").lower(), 1.0)
        # bm25() returns more-negative == better; flip sign so higher == better, then weight.
        rank = (-float(score_by_rowid[rowid])) * boost
        out.append(CorpusRecord(work_id=work_id, title=title or "", journal=journal or "",
                                year=year, study_design=design or "", section_type=sect or "",
                                content=content or "", source_db=name, score=rank))
    return out


def _enrich_ids(records: list, cfg: "CorpusConfig") -> None:
    by_db = defaultdict(list)
    for r in records:
        by_db[r.source_db].append(r)
    for name, recs in by_db.items():
        src = Path(cfg.source_dir) / f"{name}_fulltext.sqlite"
        if not src.exists():
            continue
        ids = list({r.work_id for r in recs})
        try:
            con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
            rows = con.execute(
                "SELECT work_id, scheme, value FROM identifiers "
                "WHERE scheme IN ('pmid','doi') AND work_id IN (%s)" % ",".join("?" * len(ids)),
                ids).fetchall()
            con.close()
        except sqlite3.Error:
            continue
        pmid, doi = {}, {}
        for wid, scheme, val in rows:
            (pmid if scheme == "pmid" else doi).setdefault(wid, val)
        for r in recs:
            r.pmid = pmid.get(r.work_id, "")
            r.doi = doi.get(r.work_id, "")


def retrieve_corpus(question: str, cfg: "CorpusConfig | None" = None) -> list:
    """Top-k corpus passages across the configured DBs, section-weighted, deduped per work."""
    cfg = cfg or load_corpus_config()
    if not cfg.enabled:
        return []
    match = _fts_match_query(question)
    if not match:
        return []
    pooled = []
    for name in route_domains(question, cfg.dbs):   # scope to the question's subspecialty (§2.1)
        pooled.extend(_query_db(name, cfg, match))
    pooled.sort(key=lambda r: r.score, reverse=True)
    picked, per_work = [], defaultdict(int)
    for r in pooled:
        if per_work[r.work_id] >= cfg.max_per_work:
            continue
        per_work[r.work_id] += 1
        picked.append(r)
        if len(picked) >= cfg.k:
            break
    _enrich_ids(picked, cfg)
    return picked


def retrieve_corpus_for_weave(question: str, cfg: "CorpusConfig | None" = None) -> list:
    """Failure-safe wrapper for the woven orchestrator (mirrors the literature lane)."""
    try:
        return retrieve_corpus(question, cfg)
    except Exception:
        _log.debug("corpus lane failed", exc_info=True)
        return []


def format_corpus_studies(records: list, excerpt_chars: int = 700) -> str:
    """Numbered [D#] block for the woven prompt: header (title/journal/year/design/PMID/section)
    + a bounded passage excerpt (the verification premise for that claim)."""
    blocks = []
    for i, r in enumerate(records, 1):
        meta = ", ".join(x for x in (r.journal, str(r.year or ""), r.study_design) if x)
        pid = f", PMID {r.pmid}" if r.pmid else ""
        head = f"[D{i}] {r.title} — {meta}{pid} [{r.section_type}]"
        blocks.append(f"{head}\n{(r.content or '')[:excerpt_chars]}")
    return "\n\n".join(blocks)


def _selfcheck() -> None:
    assert _fts_match_query("") is None
    q = _fts_match_query("Large-core thrombectomy selection in the extended window?")
    assert q and '"thrombectomy"' in q and " OR " in q and '"the"' not in q, q
    recs = [CorpusRecord("w1", "TESLA trial", "Stroke", 2024, "rct", "results", "x" * 999)]
    out = format_corpus_studies(recs, excerpt_chars=50)
    assert out.startswith("[D1] TESLA trial — Stroke, 2024, rct [results]") and "x" * 50 in out
    assert "x" * 51 not in out
    print("corpus selfcheck OK")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--selfcheck":
        _selfcheck()
    elif len(sys.argv) > 1:
        cfg = load_corpus_config()
        cfg = CorpusConfig(**{**cfg.__dict__, "enabled": True})  # force-on for manual probe
        for r in retrieve_corpus(" ".join(sys.argv[1:]), cfg):
            print(f"[{r.score:.2f}] {r.source_db}/{r.section_type}  {r.title[:70]}  ({r.year}, PMID {r.pmid})")
    else:
        _selfcheck()
