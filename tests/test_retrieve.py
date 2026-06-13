"""The FTS5 query sanitizer that keeps caseprep's CorpusRetriever from choking on
question punctuation/operators."""

from neuro_caseboard.retrieve import _SanitizingCorpus


def test_strips_fts_operators_and_punctuation():
    raw = "Confirm vertebral artery course (margin >= 5 mm, drill -> medial)?"
    cleaned = _SanitizingCorpus._clean(raw, 6)
    for bad in ("?", "(", ")", ">=", "->", ","):
        assert bad not in cleaned
    assert "vertebral" in cleaned and "artery" in cleaned


def test_drops_stopwords_and_caps_terms():
    cleaned = _SanitizingCorpus._clean(
        "Confirm the vertebral artery course and the corpectomy trough width", 4)
    terms = cleaned.split()
    assert len(terms) <= 4
    assert "the" not in terms and "and" not in terms


def test_empty_query_returns_empty():
    assert _SanitizingCorpus._clean("?? // (,)", 6) == ""


# --- textbook lexical lane (engine.index.Index.text_search) -----------------

from neuro_caseboard.retrieve import (
    _hit_to_dict, _index_search_fn, InProcessTextbookRetriever,
)


class _FakeHit:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_hit_to_dict_basic_shape():
    h = _FakeHit(book="Greenberg", chapter="Tumors", page=792,
                 text="acoustic neuroma...", score=1.2)
    d = _hit_to_dict(h)
    assert d["book"] == "Greenberg" and d["page"] == 792
    assert d["printed_page"] is None            # index stores PDF page only
    assert d["text"].startswith("acoustic")
    assert "figure_path" not in d               # this hit carries no figure


def test_hit_to_dict_includes_existing_figure(tmp_path):
    img = tmp_path / "p0026.png"
    img.write_bytes(b"\x89PNG\r\n")
    h = _FakeHit(book="Benzel Spine", page=26, text="page text", has_figure=True,
                 figure_path=str(img), caption="Figure 1-2. historic laminectomy")
    d = _hit_to_dict(h)
    assert d["figure_path"] == str(img)
    assert d["caption"].startswith("Figure 1-2")


def test_hit_to_dict_drops_missing_figure_file():
    h = _FakeHit(book="Benzel Spine", page=26, text="x", has_figure=True,
                 figure_path="/no/such/p0026.png", caption="Figure 1-2")
    assert "figure_path" not in _hit_to_dict(h)   # renderer never points at a missing image


def test_index_search_fn_none_when_index_absent():
    assert _index_search_fn(index_dir="/no/such/index", repo="/no/such/repo") is None


def test_inprocess_retriever_maps_hits_to_cited_records():
    def fake_search(query, k):
        return [{"book": "Greenberg", "chapter": "Tumors", "page": 792,
                 "printed_page": None, "score": 1.0, "text": "facial nerve over tumor"}]
    recs = InProcessTextbookRetriever(fake_search).retrieve(
        "vestibular schwannoma facial nerve", top_n=3)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.source == "textbook"
    assert rec.metadata["citation"] == "Greenberg, p.792"
    assert rec.metadata["retrieval_source"] == "textbook_rag_inproc"


def test_inprocess_retriever_skips_hits_without_book_or_page():
    def fake_search(query, k):
        return [{"book": "", "page": 5, "text": "x"},             # no book -> skip
                {"book": "Schmidek", "page": None, "text": "y"},  # no page -> skip
                {"book": "Rhoton", "page": 10, "text": "z"}]      # kept
    recs = InProcessTextbookRetriever(fake_search).retrieve("q", top_n=5)
    assert [r.metadata["book"] for r in recs] == ["Rhoton"]


# --- figure collection into card_evidence (pipeline) ------------------------

def test_collect_figures_dedups_pages_and_links_cards():
    from neuro_caseboard.pipeline import _collect_figures
    from caseprep.core.contracts import EvidenceRecord
    from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest

    figA = EvidenceRecord(id="a", source="textbook", title="Benzel (p.26)", text="pageA",
                          metadata={"figure_path": "/x/p26.png", "caption": "Fig A"})
    figB = EvidenceRecord(id="b", source="textbook", title="Benzel (p.27)", text="pageB",
                          metadata={"figure_path": "/x/p27.png", "caption": "Fig B"})

    class _R:  # returns both figures for every card; _collect must dedup by page
        def retrieve(self, query, *, topic="", top_n=4):
            return [figA, figB]

    cards = [QuestionCard(target_file="03-anatomy-at-risk.md", section_key="neural_structures",
                          question=f"q{i}", why_it_matters="w", compiler_slot="Neural", answerability="x")
             for i in range(3)]
    mani = QuestionManifest(procedure_family="spine", cards=cards)

    ce, pt = _collect_figures(mani, "C5-6 ACDF", figret=_R(), max_total=8, per_card=1)
    # each page image used at most once; first two cards get one distinct figure each
    assert ce["q0"][0].metadata["figure_path"] == "/x/p26.png"
    assert ce["q1"][0].metadata["figure_path"] == "/x/p27.png"
    assert "q2" not in ce                      # both pages already used
    assert pt == {"/x/p26.png": "pageA", "/x/p27.png": "pageB"}  # page text for caption recovery


# --- figure-caption retrieval (fixes lexical whole-page drift) ---------------

def test_figure_region_guard_rejects_cross_region_and_level():
    from neuro_caseboard.retrieve import _figure_offtarget
    # cranial case must reject a spine plate
    assert _figure_offtarget("Lumbar pedicle screw entry point",
                             "pterional craniotomy for MCA aneurysm")
    # spine case must reject a cranial plate
    assert _figure_offtarget("Sylvian fissure and middle cerebral artery branches",
                             "C1-C2 posterior fusion for atlantoaxial instability")
    # cervical case rejects a lumbar figure (level conflict)
    assert _figure_offtarget("Lumbar pedicle angles and dimensions",
                             "Posterior C1 lateral mass and C2 pedicle screw, atlantoaxial")
    # on-target figures are kept
    assert not _figure_offtarget(
        "Left cerebellopontine angle: AICA between the facial and vestibulocochlear nerves",
        "retrosigmoid craniotomy for vestibular schwannoma")
    assert not _figure_offtarget("C1 lateral mass and C2 pedicle screw trajectory",
                                 "C1-C2 atlantoaxial fixation")


def test_figure_region_guard_uses_source_book():
    from neuro_caseboard.retrieve import _figure_offtarget
    # spine-book figure with a generic (no region term) caption on a cranial case -> blocked
    assert _figure_offtarget("An attempt to correct shoulder asymmetry",
                             "retrosigmoid craniotomy for vestibular schwannoma",
                             book="Textbook of Spinal Surgery Bridwell")
    # cranial-book figure on a spine case -> blocked
    assert _figure_offtarget("Stepwise dissection of the cavernous sinus",
                             "C1-C2 posterior atlantoaxial fixation", book="Rhoton Cranial Anatomy")
    # same-region book stays
    assert not _figure_offtarget("C1 lateral mass screw entry point",
                                 "C1-C2 atlantoaxial fixation", book="Benzel Spine")


def test_figure_level_guard_uses_page_context_for_truncated_caption():
    from neuro_caseboard.retrieve import _figure_offtarget
    # caption only says "Pedicle screw placement" but the page is lumbar -> blocked on a C1-C2 case
    assert _figure_offtarget(
        "Pedicle screw placement, entrance point", "Posterior C1 lateral mass and C2 pedicle screw, atlantoaxial",
        book="Benzel Spine", context="Lumbar pedicle screw placement at L4 and L5 with the entrance point")
    # a thoracic plate is off-target for a cervical/CVJ case
    assert _figure_offtarget("Pedicle screws at T8 and T9 for deformity",
                             "C1-C2 Goel-Harms atlantoaxial fixation", book="Bridwell")
    # the atlantoaxial construct stays even though its page mentions c3-c7 in passing
    assert not _figure_offtarget(
        "Atlantoaxial bony anatomy after C1 lateral mass and C2 pedicle screw",
        "C1-C2 Goel-Harms atlantoaxial", book="Schmidek and Sweet",
        context="cervical spine C2 C3 C4 lateral mass screw technique")
    # ACDF (cervical) must still reject a lumbar plate seen only in the page context
    assert _figure_offtarget("Interbody graft placement",
                             "C5-6 ACDF for cervical myelopathy with interbody graft",
                             context="lumbar interbody fusion at L4-L5")


def test_figure_guard_blocks_peripheral_nerve_and_cervical_subregion():
    from neuro_caseboard.retrieve import _figure_offtarget
    # peripheral-nerve / brachial-plexus surgery figure on a C1-C2 case
    assert _figure_offtarget("Double fascicular nerve transfer; the nerve to brachialis",
                             "Posterior C1-C2 Goel-Harms atlantoaxial fixation")
    # subaxial (C4-C5) plate on a CVJ (C1-C2) case
    assert _figure_offtarget("Lateral mass fixation at C4 and C5 and pedicle screw",
                             "Posterior C1 lateral mass and C2 pedicle Goel-Harms atlantoaxial")
    # CVJ plate on a subaxial (ACDF) case
    assert _figure_offtarget("Atlantoaxial C1-C2 transarticular screw and odontoid",
                             "C5-6 ACDF subaxial cervical myelopathy")
    # same sub-region stays
    assert not _figure_offtarget("Atlantoaxial C1 lateral mass and C2 pedicle screw",
                                 "C1-C2 Goel-Harms atlantoaxial")


def test_figure_caption_retriever_ranks_by_caption_and_region_filters():
    from neuro_caseboard.retrieve import FigureCaptionRetriever
    rows = [
        {"book": "Rhoton", "page": 538, "figure_path": "/x/p538.png",
         "caption": "Left cerebellopontine angle: the AICA passes between the facial and vestibulocochlear nerves"},
        {"book": "Benzel", "page": 516, "figure_path": "/x/p516.png",
         "caption": "Lumbar pedicle angles and dimensions, transverse pedicle angle"},
        {"book": "Rhoton", "page": 227, "figure_path": "/x/p227.png",
         "caption": "Sylvian and insular veins, lateral view of the sylvian fissure"},
    ]
    r = FigureCaptionRetriever(rows)
    # the CPA caption ranks first for a CPA query
    recs = r.retrieve("cerebellopontine angle facial vestibulocochlear AICA",
                      topic="retrosigmoid vestibular schwannoma", top_n=2)
    assert recs and recs[0].metadata["page"] == 538
    assert recs[0].metadata["retrieval_source"] == "textbook_figcap"
    # an ambiguous "pedicle screw" query in a cranial case must NOT surface the lumbar plate
    recs2 = r.retrieve("pedicle screw", topic="retrosigmoid craniotomy CPA", top_n=3)
    assert all(x.metadata["page"] != 516 for x in recs2)
