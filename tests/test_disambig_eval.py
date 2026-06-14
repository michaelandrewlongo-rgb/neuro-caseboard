# tests/test_disambig_eval.py
from eval.textbook.disambig_eval import conflation, wrong_variant, over_ask
from neuro_core.query import QueryResult, Clarification


def test_conflation_true_when_forbidden_term_present():
    r = QueryResult(answer="The bifrontal bicoronal incision is made ...")
    assert conflation(r, forbidden=["bifrontal", "bicoronal", "kjellberg"]) is True


def test_conflation_false_when_clean():
    r = QueryResult(answer="**Assuming unilateral FTP hemicraniectomy ...** 12x15 cm flap [1].")
    assert conflation(r, forbidden=["bifrontal", "bicoronal", "kjellberg"]) is False


def test_wrong_variant_true_when_chosen_label_absent():
    r = QueryResult(answer="A bifrontal decompression is performed ...")
    assert wrong_variant(r, expected_label="unilateral FTP hemicraniectomy") is True


def test_over_ask_true_only_for_clarification_on_unambiguous_case():
    assert over_ask(Clarification(question="q", variants=[]), expect_ambiguous=False) is True
    assert over_ask(QueryResult(answer="x"), expect_ambiguous=False) is False
    assert over_ask(Clarification(question="q", variants=[]), expect_ambiguous=True) is False
