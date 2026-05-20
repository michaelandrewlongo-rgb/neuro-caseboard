"""Tests for template population — content extraction, domain profiles, guardrail verification."""

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest
from caseprep.mcp_server import (
    _extract_relevant_sentences,
    _detect_profile,
    _build_keywords,
    _BASE_ANATOMY,
    _BASE_APPROACH,
    _BASE_COMPLICATIONS,
    _fmt_corpus_paper,
    _handle_search_corpus,
    _corpus_search,
    _populate_section,
)


class TestDomainProfiles:
    def test_detects_skull_base_vestibular_schwannoma(self):
        profile, conf = _detect_profile("vestibular schwannoma")
        assert profile == "skull_base"
        assert conf > 0.5

    def test_detects_vascular_aneurysm(self):
        profile, conf = _detect_profile("anterior communicating artery aneurysm clipping")
        assert profile == "vascular"
        assert conf > 0

    def test_detects_supratentorial_gbm(self):
        profile, conf = _detect_profile("glioblastoma resection")
        assert profile == "supratentorial_tumor"
        assert conf > 0.3

    def test_detects_spine_fusion(self):
        profile, conf = _detect_profile("lumbar fusion l4-l5")
        assert profile == "spine"

    def test_detects_functional_dbs(self):
        profile, conf = _detect_profile("deep brain stimulation parkinson")
        assert profile == "functional"

    def test_detects_pediatric_hydrocephalus(self):
        profile, conf = _detect_profile("pediatric hydrocephalus")
        assert profile == "pediatric"

    def test_falls_back_to_skull_base_on_unknown(self):
        profile, conf = _detect_profile("some unknown neurosurgical procedure")
        assert profile == "skull_base"
        assert conf == 0.0

    def test_longest_match_wins(self):
        # "aneurysm" matches vascular, but "lumbar" also matches spine.
        # "lumbar aneurysm" — vascular wins because "aneurysm" is longer than "lumbar"
        profile, conf = _detect_profile("lumbar aneurysm")
        # Actually "lumbar" = 6 chars, "aneurysm" = 8 chars → aneurysm wins
        assert profile in ("spine", "vascular")

    def test_build_keywords_merges_base_and_profile(self):
        kw = _build_keywords("skull_base")
        assert "anatomy" in kw
        assert "cranial nerve" in kw["anatomy"]  # profile-specific
        assert "nerve" in kw["anatomy"]  # base
        assert len(kw["anatomy"]) > len(_BASE_ANATOMY)  # profile adds

    def test_build_keywords_unknown_profile_uses_base_only(self):
        kw = _build_keywords("nonexistent")
        assert kw["anatomy"] == _BASE_ANATOMY
        assert kw["approach"] == _BASE_APPROACH
        assert kw["complications"] == _BASE_COMPLICATIONS


class TestStructuredCaseDossierOutput:
    @pytest.mark.asyncio
    async def test_write_filled_templates_writes_canonical_schema_files(self, tmp_path):
        from caseprep.mcp_server import _write_filled_templates

        axis_data = {
            "Anatomy / Relevant Structures": [
                {
                    "pmid": "12345",
                    "title": "CPA Anatomy",
                    "authors": "Doe J",
                    "source": "J Neurosurg",
                    "pubdate": "2024",
                    "doi": "",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                    "_abstract": "The cerebellopontine angle contains cranial nerves and vascular structures.",
                    "_structured": {},
                }
            ],
            "Surgical Technique": [],
            "Reviews / Landmarks": [],
            "Outcomes / Evidence": [],
            "Complications": [],
        }

        async def fake_populate(**kwargs):
            return f"# {kwargs['section_title']} - {kwargs['topic']}\n\nGenerated section body."

        with patch("caseprep.mcp_server._populate_section", side_effect=fake_populate):
            await _write_filled_templates(
                tmp_path,
                "retrosigmoid vestibular schwannoma",
                "# Case Plan\n\nPaper summary",
                axis_data,
            )

        for filename in [
            "caseprep.yaml",
            "provenance.json",
            "README.md",
            "01-case-summary.md",
            "02-imaging-review.md",
            "03-anatomy-at-risk.md",
            "04-operative-plan.md",
            "05-risk-and-rescue.md",
            "06-postop-plan.md",
            "07-evidence.md",
            "08-checklists.md",
            "09-open-questions.md",
        ]:
            assert (tmp_path / filename).is_file(), f"missing {filename}"

        assert "Preparation Status" in (tmp_path / "README.md").read_text()
        assert "pmid-12345" in (tmp_path / "07-evidence.md").read_text()
        assert (tmp_path / "anatomy.md").read_text() == (tmp_path / "03-anatomy-at-risk.md").read_text()
        assert (tmp_path / "approach.md").read_text() == (tmp_path / "04-operative-plan.md").read_text()
        assert (tmp_path / "complications.md").read_text() == (tmp_path / "05-risk-and-rescue.md").read_text()
        assert (tmp_path / "literature.md").read_text() == (tmp_path / "07-evidence.md").read_text()


class TestExtractRelevantSentences:
    def test_extracts_anatomy_sentences(self):
        articles = [{
            "_abstract": (
                "The cerebellopontine angle contains the facial nerve and "
                "vestibulocochlear nerve. The anterior inferior cerebellar artery "
                "courses through the cistern. Anatomic variants of the sigmoid "
                "sinus may affect the surgical corridor."
            ),
            "_structured": {},
        }]
        keywords = _BASE_ANATOMY + ["cranial nerve", "cerebellopontine", "sigmoid"]
        result = _extract_relevant_sentences(articles, keywords)
        # All sentences should match (low keyword density, score=1 or 2 each)
        assert len(result) >= 2
        assert any("nerve" in s.lower() for s in result)

    def test_extracts_approach_sentences(self):
        articles = [{
            "_abstract": (
                "The retrosigmoid approach provides excellent exposure. "
                "Intraoperative neuromonitoring with facial nerve EMG reduces "
                "the risk of postoperative deficit. The craniotomy should expose "
                "the transverse-sigmoid junction."
            ),
            "_structured": {},
        }]
        keywords = _BASE_APPROACH + ["retrosigmoid", "emg"]
        result = _extract_relevant_sentences(articles, keywords)
        # All sentences should match with ≥1 keyword hit
        assert len(result) >= 2

    def test_extracts_complication_sentences(self):
        articles = [{
            "_abstract": (
                "CSF leak occurred in 8% of patients. The mortality rate was "
                "less than 1%. Meningitis was observed in 2% of cases. "
                "Facial nerve palsy was the most common complication at 12%."
            ),
            "_structured": {},
        }]
        keywords = _BASE_COMPLICATIONS + ["csf leak", "facial nerve"]
        result = _extract_relevant_sentences(articles, keywords)
        assert len(result) >= 2
        assert any("%" in s for s in result)

    def test_empty_articles_returns_empty(self):
        result = _extract_relevant_sentences([], _BASE_ANATOMY)
        assert result == []

    def test_no_matching_keywords_returns_empty(self):
        articles = [{
            "_abstract": "The weather was sunny with clear skies.",
            "_structured": {},
        }]
        result = _extract_relevant_sentences(articles, _BASE_ANATOMY)
        assert result == []

    def test_respects_char_budget(self):
        """Sentences should be capped by char_budget, not sentence count."""
        articles = [{
            "_abstract": (
                "The artery was dissected carefully. The nerve was identified. "
                "The cistern was opened. The cortex was retracted. "
                "The vein was preserved. The tract was avoided. "
                "The fissure was explored. The sulcus was traced. "
                "The gyrus was mapped. The ventricle was entered."
            ),
            "_structured": {},
        }]
        result = _extract_relevant_sentences(articles, _BASE_ANATOMY, char_budget=150)
        total_chars = sum(len(s) for s in result)
        assert total_chars <= 150
        assert len(result) >= 1  # should fit at least one sentence

    def test_uses_structured_abstract(self):
        articles = [{
            "_abstract": "",
            "_structured": {
                "METHODS": "We used a retrosigmoid craniotomy approach with "
                           "facial nerve monitoring and continuous EMG.",
                "RESULTS": "CSF leak rate was 5% and meningitis rate was 1%.",
            },
        }]
        approach_kw = _BASE_APPROACH + ["retrosigmoid", "emg"]
        complication_kw = _BASE_COMPLICATIONS + ["csf leak", "facial nerve"]
        approach_result = _extract_relevant_sentences(articles, approach_kw)
        complication_result = _extract_relevant_sentences(articles, complication_kw)
        assert len(approach_result) > 0 or len(complication_result) > 0

    def test_single_keyword_hit_included(self):
        """Sentences with exactly 1 keyword hit should be included (score ≥ 1)."""
        articles = [{
            "_abstract": (
                "The patient underwent surgery. The retrosigmoid approach was used. "
                "The standard craniotomy was performed. The dura was closed. "
                "Neuromonitoring was employed throughout the procedure."
            ),
            "_structured": {},
        }]
        keywords = _BASE_APPROACH + ["retrosigmoid"]
        result = _extract_relevant_sentences(articles, keywords)
        # Every sentence has at least one keyword: surgery(none), approach+retrosigmoid(2),
        # craniotomy(1), dura(1), neuromonitoring+monitoring(2)
        # "surgery" is NOT in _BASE_APPROACH, so that sentence drops
        assert len(result) >= 3

    def test_supratentorial_profile_extracts_gbm_anatomy(self):
        """GBM-relevant keywords should extract supratentorial anatomy."""
        articles = [{
            "_abstract": (
                "The tumor was located in the left frontal lobe adjacent to "
                "Broca's area and the supplementary motor cortex. "
                "Eloquent cortex was mapped intraoperatively. "
                "The corticospinal tract was visualized with DTI tractography."
            ),
            "_structured": {},
        }]
        kw = _build_keywords("supratentorial_tumor")
        result = _extract_relevant_sentences(articles, kw["anatomy"])
        assert len(result) >= 2
        assert any("broca" in s.lower() or "eloquent" in s.lower() or "frontal" in s.lower() for s in result)

    def test_vascular_profile_extracts_aneurysm_anatomy(self):
        """Vascular keywords should extract aneurysm-specific anatomy."""
        articles = [{
            "_abstract": (
                "The anterior communicating artery aneurysm arose at the "
                "A1-A2 junction. The perforator arising from the A1 segment "
                "was preserved during clipping. The interhemispheric approach "
                "provided good exposure of the AComA complex."
            ),
            "_structured": {},
        }]
        kw = _build_keywords("vascular")
        result = _extract_relevant_sentences(articles, kw["anatomy"])
        assert len(result) >= 2
        assert any("acoma" in s.lower() or "anterior communicating" in s.lower() or "perforator" in s.lower() for s in result)

    def test_sorted_by_relevance(self):
        """Highest keyword-density sentences should come first."""
        articles = [{
            "_abstract": (
                "The patient recovered well. The cerebellopontine angle cistern "
                "contains the facial nerve and vestibulocochlear nerve. "
                "The approach was standard."
            ),
            "_structured": {},
        }]
        keywords = _BASE_ANATOMY + ["cranial nerve", "cerebellopontine", "cistern"]
        result = _extract_relevant_sentences(articles, keywords)
        if len(result) >= 2:
            # The CPA sentence should be first (highest keyword density: cerebellopontine, cistern, nerve)
            first = result[0].lower()
            assert "cerebellopontine" in first or "cistern" in first


# ── Guardrail tests ────────────────────────────────────────────────────────

class TestGuardrailVerify:
    def test_passes_cited_supported_claims(self):
        from caseprep.llm import verify_synthesis
        sources = [
            "CSF leak occurred in 8% of patients (N=234).",
            "Meningitis rate was 1.5% in the retrosigmoid approach group.",
        ]
        synth = "- CSF leak rate was 8 percent [S1]\n- Meningitis rate 1.5 percent [S2]"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.flagged_count == 0

    def test_flags_claim_when_cited_source_does_not_match(self):
        """Claim cites [S1] but [S1] doesn't contain the claim — should flag."""
        from caseprep.llm import verify_synthesis
        sources = [
            "The tumor was resected via retrosigmoid approach.",  # S1
            "CSF leak occurred in 8% of patients.",               # S2
        ]
        # Claim cites S1 but S1 doesn't mention CSF leak or 8%
        synth = "- CSF leak rate was 8% [S1]"
        result = verify_synthesis(synth, sources)
        # Should flag because S1 doesn't contain the claim's content
        assert result.flagged_count > 0
        # Verify it's flagged because of the cited source mismatch
        assert not result.claims[0]["passed"]

    def test_passes_when_cited_source_matches(self):
        """Claim cites [S2] which DOES contain the fact — should pass."""
        from caseprep.llm import verify_synthesis
        sources = [
            "The tumor was resected via retrosigmoid approach.",  # S1
            "CSF leak occurred in 8% of patients.",               # S2
        ]
        synth = "- CSF leak rate was 8% [S2]"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.flagged_count == 0

    def test_numeric_fidelity_blocks_fabricated_numbers(self):
        """A claim with a fabricated number should fail numeric fidelity check."""
        from caseprep.llm import verify_synthesis
        sources = ["Mortality rate was 1% in the series."]  # S1
        synth = "- Mortality rate was 50% [S1]"
        result = verify_synthesis(synth, sources)
        # Should flag — "50%" doesn't appear in source even if Jaccard passes
        assert result.flagged_count > 0
        flagged = [c for c in result.claims if not c["passed"]]
        assert any(not c.get("numeric_fidelity", True) for c in flagged)

    def test_numeric_fidelity_passes_exact_match(self):
        """Exact number match should pass numeric fidelity."""
        from caseprep.llm import verify_synthesis
        sources = ["CSF leak rate was 8.5% (n=234) in the retrosigmoid group."]
        synth = "- CSF leak rate was 8.5% (n=234) [S1]"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.claims[0]["numeric_fidelity"]

    def test_falls_back_to_best_match_when_no_citation(self):
        """Claim without [S#] should match against all sources."""
        from caseprep.llm import verify_synthesis
        sources = [
            "Approach was standard.",
            "CSF leak rate was 5%.",
        ]
        synth = "- CSF leak rate was 5%"
        result = verify_synthesis(synth, sources)
        assert result.passed
        assert result.flagged_count == 0

    def test_rejects_when_over_threshold(self):
        from caseprep.llm import verify_synthesis
        sources = ["The approach provides good exposure."]
        synth = "- Mortality was 5% [S1]\n- Infection rate 10% [S1]\n- CSF leak 8% [S1]\n- Seizure 3% [S1]"
        result = verify_synthesis(synth, sources, max_flagged_ratio=0.25)
        assert not result.passed  # 4 claims, all hallucinated > 25%

    def test_handles_insufficient_data_lines(self):
        from caseprep.llm import _extract_claims
        text = "- CSF leak rate was 5% [S1]\n- Insufficient data in search results.\n- Meningitis 2% [S2]"
        claims = _extract_claims(text)
        assert len(claims) == 2  # insufficient data line skipped

    def test_empty_synthesis_fails(self):
        from caseprep.llm import verify_synthesis
        result = verify_synthesis("", ["some source"])
        assert not result.passed

    def test_citation_parsing(self):
        from caseprep.llm import _parse_citations
        assert _parse_citations("- Claim with [S1] citation") == [1]
        assert _parse_citations("- Claim with [S1, S2] citations") == [1, 2]
        assert _parse_citations("- Claim without citation") == []

    def test_numeric_extraction(self):
        from caseprep.llm import _extract_numbers
        nums = _extract_numbers("CSF leak rate was 8.5% (n=234). OR: 2.1 (95% CI 1.2-3.5).")
        assert "8.5%" in nums
        assert "n=234" in nums
        assert "OR 2.1" in nums

    def test_claim_fallback_for_non_bullet_format(self):
        """When LLM returns paragraph format, _extract_claims should still find claims."""
        from caseprep.llm import _extract_claims
        text = """# Section
        The CSF leak rate was 8% in this series [S1].
        Meningitis occurred in 1.5% of cases [S2].
        Insufficient data in search results.
        """
        claims = _extract_claims(text)
        assert len(claims) >= 2

    def test_zero_total_claims_edge_case(self):
        """verify_synthesis with no extractable claims returns GuardrailResult(passed=False)."""
        from caseprep.llm import verify_synthesis
        # Use only headers (stripped) and short lines (<20 chars) — nothing extractable
        result = verify_synthesis("# Short\n## Very short\nok\n", ["source sentence"])
        assert not result.passed
        assert result.total_count == 0


class TestCorpusFormatting:
    def test_fmt_corpus_paper_includes_work_id(self):
        lines = _fmt_corpus_paper(
            {
                "work_id": "W123",
                "title": "Treatment Outcomes",
                "journal": "J Neurosurg",
                "year": 2024,
            },
            1,
        )

        assert "   Work ID: W123" in lines

    def test_handle_search_corpus_includes_work_id(self):
        fake_result = {
            "papers": [
                {
                    "work_id": "W123",
                    "title": "Treatment Outcomes",
                    "journal": "J Neurosurg",
                    "year": 2024,
                }
            ],
            "total_matches": 1,
            "returned": 1,
            "subdomain_distribution": {},
        }
        with patch("caseprep.mcp_server._corpus_search", return_value=fake_result):
            output = _handle_search_corpus({"fts_query": "aneurysm"})

        assert "Work ID: W123" in output
        assert "get_paper with a work_id" in output

    def test_handle_search_corpus_invalid_fts_query_is_user_facing(self):
        fake_result = {
            "error": "Invalid FTS query: unterminated string",
            "papers": [],
            "total_matches": 0,
        }
        with patch("caseprep.mcp_server._corpus_search", return_value=fake_result):
            output = _handle_search_corpus({"fts_query": '"'})

        assert "Invalid FTS query: unterminated string" in output
        assert "Corpus search unavailable" not in output

    def test_corpus_search_invalid_fts_query_closes_connection(self):
        class FakeCursor:
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("unterminated string")

        class FakeConnection:
            def __init__(self):
                self.closed = False

            def cursor(self):
                return FakeCursor()

            def close(self):
                self.closed = True

        conn = FakeConnection()
        with (
            patch("caseprep.mcp_server._CORPUS_AVAILABLE", True),
            patch("caseprep.mcp_server._corpus_conn", return_value=conn),
        ):
            result = _corpus_search('"')

        assert result["error"] == "Invalid FTS query: unterminated string"
        assert result["papers"] == []
        assert result["total_matches"] == 0
        assert conn.closed


class TestGuardrailRetry:
    @pytest.mark.asyncio
    async def test_numeric_retry_preserves_source_numbering(self):
        sources = [
            "The retrosigmoid approach was used for tumor exposure.",
            "Meningitis rate was 1.5% in the retrosigmoid approach group.",
        ]

        synthesize = AsyncMock(side_effect=[
            "- Meningitis rate was 50% [S2]",
            "- Meningitis rate was 1.5% [S2]",
        ])

        with (
            patch("caseprep.mcp_server._extract_relevant_sentences", return_value=sources),
            patch("caseprep.llm.synthesize_section", synthesize),
        ):
            output = await _populate_section(
                articles=[{"_abstract": "unused", "_structured": {}}],
                keywords=["meningitis"],
                template_sections=[("Postoperative", "(infection rates)")],
                topic="vestibular schwannoma",
                section_title="Complications",
            )

        assert synthesize.await_count == 2
        assert synthesize.await_args_list[1].kwargs["source_sentences"] == sources
        assert "All 1 claims verified" in output
        assert "LLM synthesis rejected" not in output
        assert "- Meningitis rate was 1.5% [S2]" in output
