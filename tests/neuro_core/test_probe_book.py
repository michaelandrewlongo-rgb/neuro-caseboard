from neuro_core.ingest import probe_book, _probe_verdict


def test_verdict_flags_scanned():
    ok, reason = _probe_verdict(0.10, 200, 0.6)
    assert ok is False and "scanned" in reason


def test_verdict_flags_empty():
    ok, reason = _probe_verdict(0.0, 0, 0.6)
    assert ok is False and "no pages" in reason


def test_verdict_passes_text_layer():
    ok, _ = _probe_verdict(0.99, 200, 0.6)
    assert ok is True


def test_probe_book_on_tiny_pdf(tiny_pdf):
    rep = probe_book(tiny_pdf)
    assert rep["book"] == "Sample Book"
    assert rep["pages"] == 4
    assert rep["coverage"] == 1.0
    assert rep["chapters"] == 2
    assert rep["ok"] is True
