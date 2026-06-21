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


def test_cli_renders_woven_literature_refs_without_narrative(capsys, monkeypatch):
    from types import SimpleNamespace
    import neuro_caseboard.cli as cli
    woven = SimpleNamespace(
        answer="Woven answer [1] with recent trial [L1].",
        citations=[SimpleNamespace(n=1, book="Greenberg", chapter="Ch", page=5)],
        figures=[],
        literature=SimpleNamespace(narrative="", citations=[
            SimpleNamespace(n=1, title="DISTAL trial", journal="NEJM", year=2024,
                            doi="10/x", url="u")]))
    monkeypatch.setattr(cli, "_answer_question", lambda q, force=False: woven)
    rc = cli._run_ask(SimpleNamespace(question="distal occlusion?", force=False))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Woven answer [1] with recent trial [L1]." in out
    assert "Contemporary Literature:" in out
    assert "[L1] DISTAL trial" in out
