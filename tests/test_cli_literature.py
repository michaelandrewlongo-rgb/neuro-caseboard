from types import SimpleNamespace

import neuro_caseboard.cli as cli


def test_run_ask_prints_literature(monkeypatch, capsys):
    lit = SimpleNamespace(
        narrative="Recent RCTs expand EVT [L1].",
        citations=[SimpleNamespace(n=1, pmid="111", title="EVT RCT", journal="Stroke",
                                   year=2024, doi="10/x",
                                   url="https://pubmed.ncbi.nlm.nih.gov/111/")])
    result = SimpleNamespace(answer="Textbook answer [1].",
                             citations=[SimpleNamespace(n=1, book="Bk", chapter="", page=5)],
                             figures=[], literature=lit)
    monkeypatch.setattr(cli, "_answer_question", lambda q, force=False: result, raising=False)
    rc = cli._run_ask(SimpleNamespace(question="q", force=False))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Textbook answer" in out
    assert "Contemporary Literature" in out
    assert "[L1]" in out and "EVT RCT" in out
