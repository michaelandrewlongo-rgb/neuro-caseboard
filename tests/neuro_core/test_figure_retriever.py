from neuro_core.figure_retriever import FigureRetriever

ROWS = [
    {"book": "Rhoton", "page": 162, "figure_path": "/x/p162.png", "context": "",
     "caption": "MCA middle cerebral artery bifurcation aneurysm with M1 and M2 trunks"},
    {"book": "Benzel", "page": 516, "figure_path": "/x/p516.png", "context": "",
     "caption": "Lumbar pedicle screw entry point and trajectory"},
    {"book": "Rhoton", "page": 538, "figure_path": "/x/p538.png", "context": "",
     "caption": "AICA passes between the facial and vestibulocochlear nerves in the CPA"},
]

def test_topic_off_skips_guards_topic_on_applies_them():
    r = FigureRetriever(ROWS)
    q = "MCA bifurcation middle cerebral artery"
    no_topic = [h.figure_path for h in r.retrieve(q, topic="", top_n=3)]
    assert no_topic and no_topic[0] == "/x/p162.png"
    spine = [h.figure_path for h in r.retrieve(
        "C1 C2 pedicle screw", topic="atlantoaxial C1 C2 fixation odontoid", top_n=3)]
    assert "/x/p162.png" not in spine and "/x/p538.png" not in spine

def test_anterior_posterior_guard_only_with_topic():
    r = FigureRetriever(ROWS)
    cpa = [h.figure_path for h in r.retrieve(
        "AICA facial vestibulocochlear", topic="retrosigmoid cerebellopontine angle schwannoma",
        top_n=3)]
    assert "/x/p538.png" in cpa and "/x/p162.png" not in cpa


# --- ranking tests (adapted from neuro_caseboard/retrieve.py FigureCaptionRetriever) ----------


def test_figure_caption_retriever_ranks_by_caption_and_region_filters():
    rows = [
        {"book": "Rhoton", "page": 538, "figure_path": "/x/p538.png",
         "caption": "Left cerebellopontine angle: the AICA passes between the facial and vestibulocochlear nerves"},
        {"book": "Benzel", "page": 516, "figure_path": "/x/p516.png",
         "caption": "Lumbar pedicle angles and dimensions, transverse pedicle angle"},
        {"book": "Rhoton", "page": 227, "figure_path": "/x/p227.png",
         "caption": "Sylvian and insular veins, lateral view of the sylvian fissure"},
    ]
    r = FigureRetriever(rows)
    # the CPA caption ranks first for a CPA query
    recs = r.retrieve("cerebellopontine angle facial vestibulocochlear AICA",
                      topic="retrosigmoid vestibular schwannoma", top_n=2)
    assert recs and recs[0].page == 538
    # an ambiguous "pedicle screw" query in a cranial case must NOT surface the lumbar plate
    recs2 = r.retrieve("pedicle screw", topic="retrosigmoid craniotomy CPA", top_n=3)
    assert all(x.page != 516 for x in recs2)


def test_flowchart_demoted_but_not_blocked():
    query = "vasospasm of the middle cerebral artery"
    topic = "endovascular treatment of cerebral vasospasm"
    anatomy = {"book": "Atlas", "page": 1, "figure_path": "/x/p1.png", "context": "",
               "caption": "Balloon angioplasty of the middle cerebral artery for vasospasm"}
    flow = {"book": "Decision", "page": 2, "figure_path": "/x/p2.png", "context": "",
            # same anatomy terms as the plate above, plus the flowchart tell-tale
            "caption": "Decision-making algorithm for vasospasm of the middle cerebral artery"}
    # a filler so the shared anatomy terms aren't in every row (otherwise IDF collapses to 0)
    filler = {"book": "Spine", "page": 9, "figure_path": "/x/p9.png", "context": "",
              "caption": "Lumbar pedicle screw entry point and trajectory"}
    ranked = FigureRetriever([anatomy, flow, filler]).retrieve(query, topic=topic, top_n=3)
    pages = [r.page for r in ranked]
    # the real anatomy plate outranks the equally-matching flowchart (demotion), ...
    assert pages[0] == 1
    # ... but the flowchart is NOT hard-blocked — it still appears when relevant.
    assert 2 in pages
    # a flowchart that is the ONLY relevant candidate still returns (soft demotion, not a block)
    assert 2 in [r.page
                 for r in FigureRetriever([flow, filler]).retrieve(query, topic=topic, top_n=3)]


def test_hybrid_semantic_adds_lexically_missed_in_region_plate():
    import numpy as np
    rows = [
        {"book": "Rhoton", "page": 1, "figure_path": "/x/p1.png", "context": "",
         "caption": "Middle cerebral artery bifurcation at the limen insulae",
         "vector": [1.0, 0.0, 0.0]},
        {"book": "Rhoton", "page": 2, "figure_path": "/x/p2.png", "context": "",
         "caption": "Sylvian fissure candelabra exposure",   # no lexical overlap w/ query
         "vector": [0.0, 1.0, 0.0]},
    ]
    query = "middle cerebral artery bifurcation M1 M2"
    topic = "pterional MCA bifurcation aneurysm clipping"
    # fake BiomedCLIP text encoder: the claim lands on row 2's axis (semantic match)
    embed = lambda t: np.array([0.0, 1.0, 0.0], dtype="float32")
    lex_pages = {r.page
                 for r in FigureRetriever(rows).retrieve(query, topic=topic, top_n=2)}
    hyb_pages = {r.page
                 for r in FigureRetriever(rows, embed_fn=embed).retrieve(
                     query, topic=topic, top_n=2)}
    assert 2 not in lex_pages          # lexical lane misses the zero-overlap caption
    assert 2 in hyb_pages              # semantic lane surfaces it


def test_hybrid_offtarget_guard_overrides_semantic():
    import numpy as np
    rows = [
        {"book": "Benzel", "page": 10, "figure_path": "/x/p10.png",
         "caption": "Lumbar pedicle screw trajectory and dimensions",
         "context": "lumbar L4 L5 pedicle screw", "vector": [1.0, 0.0, 0.0]},
        {"book": "Rhoton", "page": 11, "figure_path": "/x/p11.png", "context": "",
         "caption": "Middle cerebral artery bifurcation M1 M2 perforators",
         "vector": [0.0, 1.0, 0.0]},
    ]
    query = "middle cerebral artery bifurcation"
    topic = "pterional MCA bifurcation aneurysm clipping"
    # fake encoder maxes cosine on the LUMBAR plate — the region guard must still drop it
    embed = lambda t: np.array([1.0, 0.0, 0.0], dtype="float32")
    pages = {r.page
             for r in FigureRetriever(rows, embed_fn=embed).retrieve(
                 query, topic=topic, top_n=2)}
    assert 10 not in pages             # lumbar plate dropped despite max cosine
    assert 11 in pages
