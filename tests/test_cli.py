from neuro_caseboard import cli


class _Cite:
    def __init__(self, n, book, chapter, page):
        self.n, self.book, self.chapter, self.page = n, book, chapter, page


class _Fig:
    def __init__(self, source_n, book, page, image_path):
        self.source_n, self.book, self.page, self.image_path = source_n, book, page, image_path


class _Result:
    answer = "The facial nerve runs anterior to the tumor."
    citations = [_Cite(1, "Greenberg", "Tumors", 792)]
    figures = [_Fig(1, "Rhoton", 538, "/x/p538.png")]


def test_cli_ask_prints_answer_sources_and_figures(capsys, monkeypatch):
    monkeypatch.setattr("neuro_core.query.query", lambda q, force=False: _Result())
    rc = cli.main(["ask", "facial nerve schwannoma"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "facial nerve runs anterior" in out
    assert "[1] Greenberg, Tumors, p.792" in out
    assert "[1] Rhoton, p.538 -> /x/p538.png" in out


def test_cli_ask_gpu_not_ready_exits_1(capsys, monkeypatch):
    from neuro_core.gpu_guard import GpuNotReadyError

    def _boom(q, force=False):
        raise GpuNotReadyError("no cuda")

    monkeypatch.setattr("neuro_core.query.query", _boom)
    rc = cli.main(["ask", "q"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "GPU not ready" in err


def test_cli_build_dispatches_to_generate(capsys, monkeypatch):
    class _Summary:
        supported, to_verify, quarantined = 2, 1, 0

    class _Dossier:
        sections = [object(), object()]
        summary = _Summary()

    calls = {}

    def _fake_generate(topic, *, output_dir, pdf, enrich, use_llm):
        calls.update(topic=topic, output_dir=output_dir, pdf=pdf, enrich=enrich, use_llm=use_llm)
        return _Dossier(), {"markdown": "out/case-board.md"}

    monkeypatch.setattr(cli, "generate", _fake_generate)
    rc = cli.main(["build", "C5-6 ACDF", "-o", "out", "--no-llm"])
    out = capsys.readouterr().out
    assert rc == 0
    assert calls["topic"] == "C5-6 ACDF" and calls["use_llm"] is False and calls["enrich"] is True
    assert "Wrote out/case-board.md" in out
