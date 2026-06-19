import pytest

from neuro_core.scripts.probe_book import main


def test_script_ok_on_tiny_pdf(tiny_pdf, capsys):
    rc = main([str(tiny_pdf)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out and "Sample Book" in out


def test_script_requires_arg():
    with pytest.raises(SystemExit):
        main([])
