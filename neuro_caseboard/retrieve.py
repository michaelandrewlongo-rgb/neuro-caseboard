"""Retriever wiring for the live pipeline.

Deliberately avoids caseprep's heavy lanes (SemanticCorpusRetriever / board_cards need a
pgvector DB that may be unavailable and blocks for a long time). Uses the offline FTS5
``CorpusRetriever``, plus an optional textbook lane: in-process via textbook-rag's
no-GPU lexical ``engine.index.Index.text_search`` when the repo + LanceDB index are
present, else the subprocess ``TextbookRetriever`` when the ``textbook-rag`` CLI is on
PATH. Any lane that fails to construct is simply skipped.

The textbook lane is enabled with ``CASEPREP_TEXTBOOK=1``; the repo and index locations
default to ``/home/michael/neuro-textbook-rag`` and ``<repo>/index`` and are overridable
via ``TEXTBOOK_RAG_REPO`` / ``TEXTBOOK_INDEX_DIR``.
"""

from __future__ import annotations

import os
import shutil
import sys


import re

# Tiny stoplist so FTS5 queries keep the informative clinical terms.
_STOP = {
    "the", "and", "for", "with", "this", "that", "from", "are", "any", "its",
    "confirm", "identify", "which", "what", "when", "before", "after", "into",
    "relative", "during", "case", "patient", "plan", "vs", "or", "of", "to", "in",
    "on", "at", "is", "be", "if", "a", "an",
}


class _SanitizingCorpus:
    """Wrap caseprep's FTS5 CorpusRetriever so query punctuation/operators can't trip
    the MATCH parser. caseprep passes the raw question (which contains '?', '/', '(',
    '->', '>=') straight into FTS5; we reduce it to bare informative terms first."""

    def __init__(self, inner, *, max_terms: int = 6):
        self._inner = inner
        self._max_terms = max_terms

    @staticmethod
    def _clean(query: str, max_terms: int) -> str:
        terms: list[str] = []
        for tok in re.findall(r"[A-Za-z0-9]+", (query or "").lower()):
            if len(tok) < 3 or tok in _STOP or tok in terms:
                continue
            terms.append(tok)
            if len(terms) >= max_terms:
                break
        return " ".join(terms)

    def retrieve(self, query, *, top_n: int = 5, subdomain=None):
        cleaned = self._clean(query, self._max_terms)
        if not cleaned:
            return []
        try:
            return self._inner.retrieve(cleaned, top_n=top_n)
        except Exception:
            return []


def _corpus_lane():
    try:
        from caseprep.retrievers.corpus import CorpusRetriever
        return _SanitizingCorpus(CorpusRetriever())
    except Exception:
        return None


def _cite(hit) -> str:
    book = hit.get("book") or ""
    pp = hit.get("printed_page") or hit.get("page")
    return f"{book}, p.{pp}" if book else ""


class InProcessTextbookRetriever:
    """Normalise textbook-rag in-process search hits into EvidenceRecords (metadata
    intact, so figures/folios survive for figure->claim linkage)."""

    def __init__(self, search_fn):
        self._search = search_fn

    def retrieve(self, query, *, subdomain=None, top_n=6):
        from caseprep.core.contracts import EvidenceRecord
        hits = self._search(query, top_n) or []
        out = []
        for h in list(hits)[:top_n]:
            book = h.get("book") or ""
            page = h.get("page")
            if not book or page is None:
                continue
            meta = {
                "book": book, "chapter": h.get("chapter") or "", "page": page,
                "printed_page": h.get("printed_page"), "score": h.get("score"),
                "citation": _cite(h), "retrieval_source": "textbook_rag_inproc",
            }
            if h.get("figure_path"):
                meta["figure_path"] = h["figure_path"]
                meta["caption"] = h.get("caption") or ""
            out.append(EvidenceRecord(
                id=f"textbook-{book}-p{page}", source="textbook",
                title=f"{book} (p.{h.get('printed_page') or page})",
                text=h.get("text") or "", metadata=meta))
        return out


def _default_textbook_repo() -> str:
    return os.environ.get("TEXTBOOK_RAG_REPO") or "/home/michael/neuro-textbook-rag"


def _default_index_dir() -> str:
    return os.environ.get("TEXTBOOK_INDEX_DIR") or os.path.join(_default_textbook_repo(), "index")


def _hit_to_dict(h) -> dict:
    """Convert a textbook-rag ``Hit`` to the dict shape InProcessTextbookRetriever wants.

    Includes the figure (page image + caption) when the chunk is figure-bearing and the
    image file actually exists on disk, so the renderer never points at a missing image.
    The index stores the PDF ``page`` only (no ``printed_page``)."""
    d = {
        "book": getattr(h, "book", "") or "",
        "chapter": getattr(h, "chapter", None),
        "page": getattr(h, "page", None),
        "printed_page": None,            # index has PDF page only
        "score": getattr(h, "score", None),
        "text": getattr(h, "text", "") or "",
    }
    fp = getattr(h, "figure_path", None)
    if getattr(h, "has_figure", False) and fp and os.path.isfile(fp):
        d["figure_path"] = fp
        d["caption"] = getattr(h, "caption", None) or ""
    return d


def _index_search_fn(*, index_dir: str | None = None, repo: str | None = None):
    """A no-GPU lexical ``search_fn(query, k) -> list[dict]`` backed by textbook-rag's
    ``Index.text_search``, or ``None`` when the engine or LanceDB index are unavailable."""
    repo = repo or _default_textbook_repo()
    index_dir = index_dir or _default_index_dir()
    if not os.path.isdir(index_dir):
        return None
    if repo and os.path.isdir(repo) and repo not in sys.path:
        sys.path.insert(0, repo)
    try:
        from engine.index import Index  # type: ignore
        index = Index(index_dir)
    except Exception:
        return None

    def search_fn(query, k):
        terms = _SanitizingCorpus._clean(query, 8)   # FTS-safe bare clinical terms
        if not terms:
            return []
        try:
            hits = index.text_search(terms, k) or []
        except Exception:
            return []
        return [_hit_to_dict(h) for h in hits]

    return search_fn


def _textbook_lane(enable: bool):
    if not enable:
        return None
    try:  # in-process lexical lane (textbook-rag Index.text_search, no GPU)
        fn = _index_search_fn()
        if fn is not None:
            return InProcessTextbookRetriever(fn)
    except Exception:
        pass
    try:  # legacy in-process entrypoint, if a build ever exposes engine.query.search
        from engine.query import search as tb_search  # type: ignore
        return InProcessTextbookRetriever(lambda q, k: tb_search(q, k))
    except Exception:
        pass
    try:  # subprocess CLI fallback
        if shutil.which(os.environ.get("TEXTBOOK_RAG_BIN", "textbook-rag")):
            from caseprep.retrievers.textbook import TextbookRetriever
            return TextbookRetriever()
    except Exception:
        pass
    return None


# --- figure-caption retrieval (fixes lexical whole-page drift) --------------
#
# Ranking figures by the textbook PAGE body text pulls the right subspecialty but the wrong
# target (a distal-M4 page for an M1-bifurcation case). Each row of figures.lance carries
# the FIGURE'S OWN caption; ranking the claim against those captions (IDF-weighted, no GPU)
# surfaces the actual plate (e.g. Rhoton's CPA / Sylvian views). A region guard then drops
# cross-region figures (a lumbar plate on a C1-C2 board).

import collections
import math

_CRANIAL_SIG = ("crani", "cortex", "cortical", "cerebr", "cerebell", "ventricle", "aneurysm",
                "glioma", "meningioma", "tumor", "tumour", "skull base", "sylvian", "pterional",
                "temporal lobe", "frontal lobe", "cpa", "cerebellopontine", "vestibular",
                "pituitary", " clip", "subarachnoid", "petrous", "clivus", "sulcus", "gyrus",
                "hemisphere", "thalam", "callosum", "insula")
_SPINE_SIG = ("spine", "spinal", "vertebra", "pedicle", "cervical", "thoracic", "lumbar",
              "sacral", "disc", "laminectomy", "fusion", "acdf", "corpectomy", "odontoid",
              "atlas", " axis", "atlantoaxial", "myelopath", "radiculopath", "scoliosis",
              "kyphosis", "spondyl")
# Spine levels. Only thoracic/lumbar/sacral are *block-worthy* on a cervical/cranial case:
# a cervical figure's page incidentally naming c3-c7 must NOT block a good atlantoaxial plate,
# but a page naming lumbar/thoracic is unambiguously a different operation.
_LEVELS = {
    "cervical": ("cervical", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "atlas", " axis",
                 "atlanto", "odontoid", "subaxial", "craniovertebral"),
    "thoracic": ("thoracic", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10",
                 "t11", "t12", "costotransverse"),
    "lumbar": ("lumbar", "l1", "l2", "l3", "l4", "l5", "cauda equina", "spondylolisthesis"),
    "sacral": ("sacral", "sacrum", " s1", "iliac"),
}
_BLOCK_LEVELS = {"thoracic", "lumbar", "sacral"}

# Cervical sub-region, read from CAPTIONS only (page context names c-levels too loosely):
# the craniovertebral junction (occiput-C2) vs the subaxial spine (C3-C7).
_CVJ_TERMS = ("c1", "c2", "atlas", " axis", "atlanto", "odontoid", "dens", "craniovertebral",
              "occipitocervical", "suboccipital")
_SUBAXIAL_TERMS = ("c3", "c4", "c5", "c6", "c7", "subaxial")
# Peripheral-nerve / brachial-plexus surgery is a different subspecialty entirely.
_PERIPHERAL_NERVE = ("nerve transfer", "nerve graft", "brachial plexus", "fascicular",
                     "neurotization", "peripheral nerve", "ulnar nerve", "median nerve",
                     "radial nerve", "brachialis", "supraclavicular")
_SELLAR = ("pituitary", "sella", "sellar", "hypophys", "transsphenoidal", "parasellar")

# Within-cranial anterior(supratentorial)<->posterior-fossa divide. A blind image judge found a
# posterior-fossa/CPA board pulling an anterior-perforated-substance / lenticulostriate (circle of
# Willis) plate, and vice-versa risk: a posterior-fossa CN plate on an anterior-circulation (MCA)
# board. The cranial<->spine and sellar guards don't catch this intra-cranial drift. A figure is
# blocked only when it is UNAMBIGUOUSLY the other compartment (its compartment terms present, the
# case's compartment terms absent), so a circle-of-Willis plate that also shows basilar/cerebellar
# vessels is NOT blocked.
_POSTERIOR_FOSSA = ("cerebellopontine", "cpa", "retrosigmoid", "suboccipital", "far lateral",
                    "aica", "pica", "internal acoustic", "internal auditory", "vestibulocochlear",
                    "vestibular schwannoma", "acoustic neuroma", "jugular foramen", "foramen magnum",
                    "petroclival", "fourth ventricle", "brainstem", "cerebellar", "cerebellum",
                    "semicircular", "labyrinth", "glossopharyngeal", "hypoglossal", "trigeminal",
                    "petrous", "clivus", "meatal", "petrosal")
_ANTERIOR_CIRC = ("middle cerebral", "lenticulostriate", "anterior perforated substance",
                  "circle of willis", "anterior communicating", "recurrent artery of heubner",
                  "sylvian", "pterional", " mca", "acom", "anterior cerebral")

# Angiographic/fluoroscopic positioning & technique figures (projection setup, frame rate) are not
# operative anatomy — they diluted an MCA board with a "view positioning" plate.
_NONOP_ANGIO = ("view positioning", "haughton", "angiographic projection", "fluoroscopic projection",
                "radiographic projection", "frames per second", "frame rate", "projection view",
                "c-arm angulation", "tube angulation")

# Diagnostic-imaging / ICU books are radiographs and tracings, not operative anatomy — a
# figure lane for a surgical board should not draw from them.
_DIAGNOSTIC_BOOKS = ("neuroradiology core requisites", "neuroicu", "neurocritical")

# Cross-sectional diagnostic imaging (CT/MRI/CT-angiogram) is a patient scan, not operative
# atlas anatomy. The larger cropped index surfaces these; a surgical-anatomy board should not
# show them. Plain X-ray / fluoroscopy is intentionally NOT here — it is often intra-op
# construct imaging that IS wanted (e.g. a lateral film confirming a C1-C2 construct).
_DIAGNOSTIC_IMAGE = ("ct angiogram", "ct scan", "axial ct", "coronal ct", "sagittal ct",
                     "3d ct", "3-d ct", "ct images", "ct image", "mri", "magnetic resonance",
                     "t1-weighted", "t2-weighted", "t2 weighted", "computed tomography",
                     "angiogram showing", "angiogram demonstrating", "3d reconstruction",
                     "diffusion-weighted", "flair")

_VIGNETTE = re.compile(r"\b\d{1,3}[\s-]?year[\s-]?old\b|\bpresented with\b|\ba \d{1,2}[- ]year",
                       re.IGNORECASE)

# Decision-making / management-pathway flowcharts are text diagrams, not operative anatomy. A blind
# generalization test had a cerebral-venous-thrombosis management algorithm leak onto a vasospasm
# board. These are DEMOTED, not blocked: a genuinely on-topic algorithm (a strong lexical match for
# the case's own subject) can still surface when it is the best candidate, but a tangential one
# loses to real anatomy plates.
_FLOWCHART = ("algorithm", "flowchart", "flow chart", "flow-chart", "decision tree",
              "management pathway", "treatment pathway", "management algorithm",
              "treatment algorithm", "decision-making algorithm", "schematic algorithm")


def _cap_toks(s: str):
    return [t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2]


def _caption_head(text: str, max_chars: int = 320) -> str:
    """Cap a (possibly legend-bloated) figure caption to caption length: keep the panel
    detail the lexical lane needs but drop the trailing legend that ``get_text('blocks')``
    glues on. Trim to the last sentence boundary in the window, else the last word."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    cut = head.rfind(". ")
    return head[:cut + 1] if cut >= 60 else head.rsplit(" ", 1)[0]


def _row_caption(r) -> str:
    """The caption the figure lane keys on. Prefer the Gemini multimodal caption when
    present: it NAMES the specific anatomy a surgeon needs (e.g. "MCA M1 bifurcation into
    superior/inferior M2 trunks with lenticulostriate perforators") that the source's
    generic first-line caption omits, so the gold plate becomes poolable + rankable. The
    Gemini caption is pure signal (no ``get_text('blocks')`` legend bloat), so it gets a
    larger cap; the source caption keeps the tighter cap that fights legend bloat / stray
    substrings ("disc dissector" -> spine) poisoning the region guards."""
    gem = (r.get("gemini_caption") or "").strip()
    if gem:
        return _caption_head(gem, max_chars=700)
    return _caption_head((r.get("caption") or "").strip())


# Medical abbreviations / synonyms so a claim saying "MCA" / "lenticulostriate" matches an
# atlas caption that spells out "middle cerebral artery" / "perforated substance".
_SYNONYMS = {
    "mca": ("middle", "cerebral"), "m1": ("middle", "cerebral"), "m2": ("middle", "cerebral"),
    "aca": ("anterior", "cerebral"), "a1": ("anterior", "cerebral"),
    "pca": ("posterior", "cerebral"), "ica": ("internal", "carotid"),
    "acom": ("anterior", "communicating"), "acoa": ("anterior", "communicating"),
    "pcom": ("posterior", "communicating"), "pcoa": ("posterior", "communicating"),
    "lenticulostriate": ("perforating", "perforator", "perforators", "perforated"),
    "perforators": ("perforating", "perforated"), "perforator": ("perforating", "perforated"),
    "aica": ("anterior", "inferior", "cerebellar"),
    "pica": ("posterior", "inferior", "cerebellar"),
    "sca": ("superior", "cerebellar"),
}


def _expand_terms(qterms: set) -> set:
    extra: set = set()
    for t in qterms:
        extra.update(_SYNONYMS.get(t, ()))
    return qterms | extra


def _levels_in(text: str):
    low = (text or "").lower()
    return {lv for lv, terms in _LEVELS.items() if any(t in low for t in terms)}


_SPINE_BOOKS = ("benzel spine", "bridwell", "spinal surgery", "vaccaro", "spine surgery",
                "techniques to the spine")   # "Surgical Anatomy and Techniques to the Spine"
_CRANIAL_BOOKS = ("rhoton", "fukushima", "greenberg")  # Schmidek/NeuroICU/Neuroradiology: mixed
# "Brain Anatomy and Neurosurgical Approaches" is deliberately NOT book-classified cranial:
# its far-lateral/suboccipital approach plates are legitimately wanted on CVJ (C1-C2) cases,
# so it is left to the per-figure caption/region guards rather than a blanket book block.


def _figure_offtarget(caption: str, topic: str, book: str = "", context: str = "") -> bool:
    """True when a figure is from a clearly different region than the case — by the
    cranial<->spine divide (caption OR source book), or a conflicting spine level. Level is
    read from the figure's PAGE CONTEXT (not just the column-truncated caption), so a lumbar
    plate whose caption is merely "Pedicle screw placement" is still caught on a C1-C2 case."""
    cap = (caption or "").lower()
    top = (topic or "").lower()
    bk = (book or "").lower()
    if any(x in cap for x in _DIAGNOSTIC_IMAGE):
        return True                          # diagnostic scan, not operative atlas anatomy
    if any(x in cap for x in _NONOP_ANGIO):
        return True                          # angio/fluoro positioning setup, not operative anatomy
    t_spine = any(s in top for s in _SPINE_SIG)
    t_cran = any(s in top for s in _CRANIAL_SIG)
    c_spine = any(s in cap for s in _SPINE_SIG)
    c_cran = any(s in cap for s in _CRANIAL_SIG)
    b_spine = any(x in bk for x in _SPINE_BOOKS)
    b_cran = any(x in bk for x in _CRANIAL_BOOKS)
    if t_spine and not t_cran and ((c_cran and not c_spine) or b_cran):
        return True
    if t_cran and not t_spine and ((c_spine and not c_cran) or b_spine):
        return True
    # peripheral-nerve/brachial-plexus figures don't belong on a cranial or spinal board
    if any(x in cap for x in _PERIPHERAL_NERVE) and not any(x in top for x in _PERIPHERAL_NERVE):
        return True
    # a sellar/pituitary plate doesn't belong on a non-sellar cranial case (e.g. an MCA clip)
    if t_cran:
        t_sellar = any(x in top for x in _SELLAR)
        f_sellar = any(x in cap for x in _SELLAR)
        if f_sellar and not t_sellar:
            return True
        # within-cranial anterior<->posterior-fossa divide: block a figure that is unambiguously
        # the OTHER compartment from the case (its terms present, the case's terms absent).
        t_post = any(x in top for x in _POSTERIOR_FOSSA)
        t_ant = any(x in top for x in _ANTERIOR_CIRC)
        f_post = any(x in cap for x in _POSTERIOR_FOSSA)
        f_ant = any(x in cap for x in _ANTERIOR_CIRC)
        if t_ant and not t_post and f_post and not f_ant:
            return True                      # posterior-fossa plate on an anterior-circulation case
        if t_post and not t_ant and f_ant and not f_post:
            return True                      # anterior-circulation plate on a posterior-fossa case
    if t_spine:
        # block a clearly different region (thoracolumbar/sacral) the case isn't about,
        # read from caption + full page context.
        t_lv = _levels_in(top)
        f_lv = _levels_in(f"{caption} {context}".lower())
        if (f_lv & _BLOCK_LEVELS) - t_lv:
            return True
        # cervical sub-region (CAPTIONS only): a CVJ case rejects a subaxial-only plate and
        # vice versa (context names c-levels too loosely to use here).
        t_cvj = any(x in top for x in _CVJ_TERMS)
        t_sub = any(x in top for x in _SUBAXIAL_TERMS)
        f_cvj = any(x in cap for x in _CVJ_TERMS)
        f_sub = any(x in cap for x in _SUBAXIAL_TERMS)
        if t_cvj and not t_sub and f_sub and not f_cvj:
            return True
        if t_sub and not t_cvj and f_cvj and not f_sub:
            return True
    return False


def _fuse_rankings(lex, sem, top_n, *, k: int = 60):
    """Reciprocal-rank fusion of the lexical (score, row) and semantic (score, row)
    rankings, keyed by figure_path so a plate appearing in BOTH lanes is rewarded.
    Returns [(row, fused_score)] best-first, truncated to ``top_n``."""
    scores: dict = {}
    rowmap: dict = {}
    for rank, (_s, row) in enumerate(lex):
        key = row["figure_path"]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        rowmap[key] = row
    for rank, (_s, row) in enumerate(sem):
        key = row["figure_path"]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        rowmap[key] = row
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(rowmap[key], sc) for key, sc in ranked[:top_n]]


class FigureCaptionRetriever:
    """Rank figures.lance rows for a claim, region/level/domain-guarded. Lexical lane =
    IDF caption overlap; optional semantic lane = BiomedCLIP text<->image cosine (the crop
    embeddings). When an ``embed_fn`` is given the two lanes are RRF-fused (hybrid),
    otherwise it is pure lexical (unchanged). The guards run BEFORE either lane, so domain
    cleanliness never depends on ranking."""

    def __init__(self, rows, *, embed_fn=None):
        self._rows = rows
        self._embed_fn = embed_fn
        df = collections.Counter()
        for row in rows:
            for t in set(_cap_toks(row["caption"])):
                df[t] += 1
        self._df = df
        self._n = max(1, len(rows))

    def _idf(self, t: str) -> float:
        return math.log((self._n + 1) / (self._df.get(t, 0) + 1))

    def _lexical_ranked(self, qterms, candidates):
        scored = []
        for row in candidates:
            ct = collections.Counter(_cap_toks(row["caption"]))
            matched = [t for t in qterms if t in ct]
            if len(matched) < 2:            # need >=2 shared terms to avoid single-word noise
                continue
            s = sum(ct[t] * self._idf(t) for t in matched)
            if _VIGNETTE.search(row["caption"]):
                s *= 0.4                    # demote patient case-vignette/clinical-image figures
            cap_low = row["caption"].lower()
            if any(f in cap_low for f in _FLOWCHART):
                s *= 0.35                   # demote decision/management flowcharts (keep if strong)
            if s > 0:
                scored.append((s, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _semantic_ranked(self, query, candidates):
        """Cosine of the claim's BiomedCLIP text vector against each candidate plate's
        image vector. [] when no encoder / no vectors / the encoder errors (graceful)."""
        if not self._embed_fn:
            return []
        try:
            import numpy as np
            qv = np.asarray(self._embed_fn(query), dtype="float32").ravel()
        except Exception:
            return []
        qn = float(np.linalg.norm(qv)) or 1.0
        sims = []
        for row in candidates:
            v = row.get("vector")
            if v is None:
                continue
            v = np.asarray(v, dtype="float32").ravel()
            if v.size != qv.size:
                continue
            vn = float(np.linalg.norm(v)) or 1.0
            sims.append((float(qv @ v) / (qn * vn), row))
        sims.sort(key=lambda x: x[0], reverse=True)
        return sims

    def retrieve(self, query, *, topic: str = "", subdomain=None, top_n: int = 3):
        from caseprep.core.contracts import EvidenceRecord
        from neuro_caseboard.captions import assemble_caption
        qterms = _expand_terms(set(_cap_toks(query)))
        if not qterms:
            return []
        candidates = [row for row in self._rows
                      if not _figure_offtarget(row["caption"], topic, row["book"],
                                               row.get("context", ""))]
        lex = self._lexical_ranked(qterms, candidates)
        sem = self._semantic_ranked(query, candidates)
        if sem:
            ordered = _fuse_rankings(lex, sem, top_n)
        else:
            ordered = [(row, s) for s, row in lex[:top_n]]
        out = []
        for row, s in ordered:
            cap = assemble_caption(row["caption"], [])
            cite = f'{row["book"]}, p.{row["page"]}' if row["book"] else ""
            out.append(EvidenceRecord(
                id=f'fig-{row["book"]}-p{row["page"]}', source="textbook",
                title=f'{row["book"]} (p.{row["page"]})', text=cap,
                metadata={"figure_path": row["figure_path"], "caption": cap,
                          "citation": cite, "book": row["book"], "page": row["page"],
                          "score": round(float(s), 4), "retrieval_source": "textbook_figcap"}))
        return out


_FIGURE_ROWS = None


def _load_figure_rows(index_dir: str | None = None):
    """Load figure-bearing rows (book/page/figure_path/caption) from figures.lance once."""
    global _FIGURE_ROWS
    if _FIGURE_ROWS is not None:
        return _FIGURE_ROWS
    index_dir = index_dir or _default_index_dir()
    rows_out: list[dict] = []
    if os.path.isdir(index_dir):
        try:
            import lancedb
            db = lancedb.connect(index_dir)
            try:
                names = set(db.list_tables())
            except Exception:
                names = set(db.table_names())
            if "figures" in names:
                for r in db.open_table("figures").search().limit(100000).to_list():
                    fp = r.get("figure_path") or ""
                    cap = _row_caption(r)
                    book = r.get("book") or ""
                    if any(d in book.lower() for d in _DIAGNOSTIC_BOOKS):
                        continue                 # radiology/ICU books: not operative anatomy
                    if cap and fp and os.path.isfile(fp):
                        rows_out.append({"book": book, "page": r.get("page"),
                                         "figure_path": fp, "caption": cap, "context": "",
                                         "vector": r.get("vector")})
            # page context (chunk body text) so the region/level guard isn't blind to a
            # column-truncated caption (e.g. a lumbar plate captioned "Pedicle screw placement").
            if rows_out and "chunks" in names:
                ctx: dict = {}
                for r in db.open_table("chunks").search().limit(1000000).to_list():
                    t = (r.get("text") or "").strip()
                    if not t:
                        continue
                    k = (r.get("book") or "", str(r.get("page")))
                    ctx[k] = (ctx.get(k, "") + " " + t)[:6000]
                for row in rows_out:
                    row["context"] = ctx.get((row["book"], str(row["page"])), "")
        except Exception:
            rows_out = []
    _FIGURE_ROWS = rows_out
    return rows_out


def _build_figure_embed_fn(repo: str | None = None):
    """A ``claim text -> BiomedCLIP text vector`` function (CPU), or None when disabled or
    unavailable. Reuses textbook-rag's ``VisualEmbedder`` so the query embedding lives in
    the same space as the figures.lance image vectors. Default OFF: a blind image judge found
    the BiomedCLIP semantic lane *hurts* (it surfaces visually-similar but wrong-region plates
    — too coarse for fine neuroanatomy), on both page-image and cropped indexes. Set
    ``CASEBOARD_FIGURE_SEMANTIC=1`` to opt in (e.g. once a stronger vision model is wired)."""
    if os.environ.get("CASEBOARD_FIGURE_SEMANTIC", "0") != "1":
        return None
    repo = repo or _default_textbook_repo()
    if repo and os.path.isdir(repo) and repo not in sys.path:
        sys.path.insert(0, repo)
    try:
        from engine.visual_embed import VisualEmbedder   # type: ignore
        from engine.config import load_config            # type: ignore
        embedder = VisualEmbedder(load_config().visual_model, device="cpu")
        return lambda text: embedder.embed_query(text)
    except Exception:
        return None


def build_figure_retriever(*, index_dir: str | None = None):
    """A figure retriever: caption-IDF lexical lane plus an optional BiomedCLIP semantic
    lane (hybrid), region/level/domain-guarded. None if no figure rows are available."""
    rows = _load_figure_rows(index_dir)
    if not rows:
        return None
    return FigureCaptionRetriever(rows, embed_fn=_build_figure_embed_fn())


def build_retriever(*, enable_corpus: bool = True, enable_textbook=None):
    """Compose the available retrieval lanes, or return None when none are available."""
    if enable_textbook is None:
        enable_textbook = os.environ.get("CASEPREP_TEXTBOOK", "0") == "1"
    lanes = []
    if enable_corpus:
        c = _corpus_lane()
        if c is not None:
            lanes.append(c)
    t = _textbook_lane(enable_textbook)
    if t is not None:
        lanes.append(t)
    if not lanes:
        return None
    if len(lanes) == 1:
        return lanes[0]
    from caseprep.retrievers.composite import CompositeRetriever
    return CompositeRetriever(lanes)
