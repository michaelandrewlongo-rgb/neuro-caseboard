"""Tests for LLM synthesis prompt construction."""

from caseprep.llm import _build_synthesis_user_prompt


def test_synthesis_prompt_allows_checklists_and_tables():
    prompt = _build_synthesis_user_prompt(
        template_sections=[
            ("Operative Plan", "- Positioning:\n- Critical steps:"),
        ],
        source_sentences=[
            "The retrosigmoid approach provides access to the cerebellopontine angle.",
        ],
        topic="retrosigmoid vestibular schwannoma",
    )

    assert "checklists, short tables, or compact prose" in prompt
    assert "No bullet lists" not in prompt
    assert "[S1] The retrosigmoid approach" in prompt
    assert "Mark unsupported fields as `needs input`" in prompt


def test_synthesis_prompt_preserves_number_integrity_rules():
    prompt = _build_synthesis_user_prompt(
        template_sections=[("Complications", "- Risk:\n- Rescue:")],
        source_sentences=["CSF leak occurred in 8% of cases."],
        topic="vestibular schwannoma",
    )

    assert "A number" in prompt
    assert "VERBATIM" in prompt
    assert "do NOT invent one" in prompt
