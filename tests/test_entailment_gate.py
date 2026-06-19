from neuro_caseboard.entailment import LexicalVerifier, should_cite


def test_lexical_entails_when_overlap_high():
    v = LexicalVerifier()
    premise = "The recurrent artery of Heubner supplies the caudate head and must be preserved."
    assert v.entails(premise, "Preserve the recurrent artery of Heubner.") is True


def test_lexical_rejects_when_disjoint():
    v = LexicalVerifier()
    premise = "Lumbar pedicle screw trajectories follow the convergent sagittal angle."
    assert v.entails(premise, "Preserve the recurrent artery of Heubner.") is False


def test_should_cite_abstains_keep_on_thin_premise():
    assert should_cite("Reference corpus record 1",
                       "Preserve the recurrent artery of Heubner.", LexicalVerifier()) is True


def test_should_cite_withholds_on_substantial_disjoint_premise():
    premise = "Lumbar pedicle screw trajectories follow the convergent sagittal angle through the pars."
    assert should_cite(premise, "Preserve the recurrent artery of Heubner.", LexicalVerifier()) is False
