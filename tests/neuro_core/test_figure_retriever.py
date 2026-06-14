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
