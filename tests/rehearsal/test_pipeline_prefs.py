"""prefs threaded through the offline build: default no-op; add injects; reinforced suppress removes."""
from neuro_caseboard.pipeline import build_dossier, build_manifest
from neuro_caseboard.preferences import Preference, _key_terms


def test_default_noop():
    a, _ = build_manifest("C5-6 corpectomy", use_llm=False)
    b, _ = build_manifest("C5-6 corpectomy", use_llm=False, prefs=None)
    assert [c.question for c in a.cards] == [c.question for c in b.cards]


def test_add_injects_into_board():
    pref = Preference(profile="spine", action="add",
                      pattern=_key_terms("monitoring troubleshooting zenith"),
                      text="Confirm intraoperative monitoring troubleshooting plan zenith", why="always")
    d = build_dossier("C5-6 corpectomy", enrich=False, use_llm=False, prefs=[pref])
    blob = " ".join(" ".join([c.text, *c.sub_items]) for s in d.sections for c in s.claims)
    assert "zenith" in blob


def test_reinforced_suppress_removes_claim():
    topic = "C5-6 corpectomy"
    base, profile = build_manifest(topic, use_llm=False)
    target = base.cards[0]
    pref = Preference(profile=profile, action="suppress",
                      pattern=_key_terms(f"{target.question} {target.why_it_matters}"), weight=2)
    d0 = build_dossier(topic, enrich=False, use_llm=False)
    d1 = build_dossier(topic, enrich=False, use_llm=False, prefs=[pref])
    raws0 = [c.raw for s in d0.sections for c in s.claims]
    raws1 = [c.raw for s in d1.sections for c in s.claims]
    assert target.question in raws0 and target.question not in raws1
