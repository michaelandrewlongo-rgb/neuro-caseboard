import pytest


@pytest.fixture(autouse=True)
def _literature_lane_off_by_default(monkeypatch, tmp_path):
    """Keep the live PubMed network out of unit tests.

    The contemporary-literature lane is always-on in production, so any test that
    exercises a Q&A entry point (e.g. the CLI ``ask`` path) would otherwise fire a
    real NCBI E-utilities request through ``answer_question``'s Lane B. Default the
    flag OFF for the whole suite; tests that specifically exercise the lane either
    inject their dependencies (retriever/cache/synth fakes) or pass an explicit
    ``LiteratureConfig``, both of which bypass this env var.
    """
    monkeypatch.setenv("LITERATURE_RETRIEVAL", "false")
    # Keep the suite hermetic: never auto-load a developer's local .env into the
    # controlled test environment (config._load_dotenv_once honors this opt-out).
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    # The default claim verifier is now a real NLI cross-encoder (downloads/loads a model on
    # first use). Force the deterministic lexical verifier suite-wide; NLI tests inject stubs.
    monkeypatch.setenv("CASEBOARD_NLI_MODEL", "lexical")
    # Never let a test enqueue into (or read) the developer's real brief queue.
    monkeypatch.setenv("BRIEF_QUEUE_DB", str(tmp_path / "brief_queue.db"))
