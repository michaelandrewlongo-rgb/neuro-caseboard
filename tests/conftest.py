import pytest


@pytest.fixture(autouse=True)
def _literature_lane_off_by_default(monkeypatch):
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
