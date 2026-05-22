"""Tests for the private structured PubMed MCP helper."""

from __future__ import annotations

import pytest

from caseprep import mcp_server


@pytest.mark.asyncio
async def test_structured_pubmed_helper_returns_required_keys_and_markdown(monkeypatch):
    async def fake_search(query, max_results, filter_type):
        assert query == "aneurysm clipping"
        assert max_results == 3
        assert filter_type is None
        return ["111"], 12

    async def fake_summaries(pmids):
        assert pmids == ["111"]
        return [
            {
                "pmid": "111",
                "title": "Aneurysm clipping outcomes",
                "authors": "Doe J",
                "source": "J Neurosurg",
                "pubdate": "2025",
                "pub_types": ["Clinical Trial"],
                "doi": "10.1000/aneurysm",
                "url": "https://pubmed.ncbi.nlm.nih.gov/111/",
            }
        ]

    async def fail_abstracts(pmids):  # pragma: no cover - should not be called
        raise AssertionError("abstract fetcher should not be called")

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)
    monkeypatch.setattr(mcp_server, "_pubmed_summaries", fake_summaries)
    monkeypatch.setattr(mcp_server, "_pubmed_abstracts", fail_abstracts)

    result = await mcp_server._handle_pubmed_structured(
        {"query": "aneurysm clipping", "max_results": 3}
    )

    assert set(result) == {
        "query",
        "rendered_query",
        "query_plan",
        "retrieval_strategy",
        "total",
        "articles",
        "markdown",
    }
    assert result["query"] == "aneurysm clipping"
    assert result["rendered_query"] == "aneurysm clipping"
    assert result["query_plan"] is None
    assert result["retrieval_strategy"] == "legacy"
    assert result["total"] == 12
    assert len(result["articles"]) == 1
    assert result["articles"][0]["_relevance_score"] >= 0.0
    assert result["articles"][0]["_evidence_grade"].label.startswith("Level")
    assert "## PubMed — aneurysm clipping" in result["markdown"]
    assert "Aneurysm clipping outcomes" in result["markdown"]


@pytest.mark.asyncio
async def test_structured_pubmed_helper_fetches_and_uses_abstracts(monkeypatch):
    seen = {"abstract_pmids": None, "scored_abstract": None}

    async def fake_search(query, max_results, filter_type):
        return ["222"], 1

    async def fake_summaries(pmids):
        return [
            {
                "pmid": "222",
                "title": "Spine surgery randomized trial",
                "authors": "Roe J",
                "source": "Spine",
                "pubdate": "2024",
                "pub_types": ["Randomized Controlled Trial"],
                "doi": "",
                "url": "https://pubmed.ncbi.nlm.nih.gov/222/",
            }
        ]

    async def fake_abstracts(pmids):
        seen["abstract_pmids"] = pmids
        return {"222": "Brain and spine surgery abstract used for ranking."}

    def fake_score(title, abstract):
        seen["scored_abstract"] = abstract
        return 99.0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)
    monkeypatch.setattr(mcp_server, "_pubmed_summaries", fake_summaries)
    monkeypatch.setattr(mcp_server, "_pubmed_abstracts", fake_abstracts)
    monkeypatch.setattr(mcp_server, "neurosurg_relevance_score", fake_score)

    result = await mcp_server._handle_pubmed_structured(
        {"query": "spine surgery", "include_abstracts": True}
    )

    assert seen["abstract_pmids"] == ["222"]
    assert seen["scored_abstract"] == "Brain and spine surgery abstract used for ranking."
    assert result["articles"][0]["_relevance_score"] == 99.0
    assert "Abstract: Brain and spine surgery abstract used for ranking." in result["markdown"]


@pytest.mark.asyncio
async def test_structured_pubmed_helper_no_results_returns_empty_structured_result(monkeypatch):
    async def fake_search(query, max_results, filter_type):
        assert filter_type == "therapy"
        return [], 0

    async def fail_summaries(pmids):  # pragma: no cover - should not be called
        raise AssertionError("summary fetcher should not be called")

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)
    monkeypatch.setattr(mcp_server, "_pubmed_summaries", fail_summaries)

    result = await mcp_server._handle_pubmed_structured(
        {"query": "not-a-real-query", "filter_type": "therapy"}
    )

    assert result["query"] == "not-a-real-query"
    assert "clinical trial[pt]" in result["rendered_query"]
    assert result["total"] == 0
    assert result["articles"] == []
    assert result["markdown"] == "No PubMed results for: not-a-real-query (filter: therapy)"


@pytest.mark.asyncio
async def test_structured_pubmed_helper_preserves_query_plan_and_strategy(monkeypatch):
    query_plan = {"axes": [{"name": "therapy", "terms": ["trial"]}]}

    async def fake_search(query, max_results, filter_type):
        return [], 0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)

    result = await mcp_server._handle_pubmed_structured(
        {
            "query": "vestibular schwannoma",
            "query_plan": query_plan,
            "retrieval_strategy": "hybrid",
        }
    )

    assert result["query_plan"] is query_plan
    assert result["retrieval_strategy"] == "hybrid"


@pytest.mark.asyncio
async def test_structured_pubmed_legacy_with_query_plan_searches_original_query(monkeypatch):
    query_plan = {
        "queries": [
            {
                "id": "plan-primary",
                "retriever": "pubmed",
                "axis": "therapy",
                "query": "plan query should not be used",
            }
        ]
    }
    seen = {"query": None}

    async def fake_search(query, max_results, filter_type):
        seen["query"] = query
        return [], 0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)

    result = await mcp_server._handle_pubmed_structured(
        {
            "query": "original legacy query",
            "query_plan": query_plan,
            "retrieval_strategy": "legacy",
        }
    )

    assert seen["query"] == "original legacy query"
    assert result["rendered_query"] == "original legacy query"
    assert result["query_plan"] is query_plan


@pytest.mark.asyncio
async def test_structured_pubmed_hybrid_uses_first_pubmed_plan_query(monkeypatch):
    query_plan = {
        "queries": [
            {
                "id": "therapy-primary",
                "retriever": "pubmed",
                "axis": "therapy",
                "query": "vestibular schwannoma radiosurgery outcomes",
            },
            {
                "id": "complications-secondary",
                "retriever": "pubmed",
                "axis": "complications",
                "query": "vestibular schwannoma facial nerve complications",
            },
        ]
    }
    seen = {"query": None}

    async def fake_search(query, max_results, filter_type):
        seen["query"] = query
        return [], 0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)

    result = await mcp_server._handle_pubmed_structured(
        {
            "query": "vestibular schwannoma",
            "query_plan": query_plan,
            "retrieval_strategy": "hybrid",
        }
    )

    assert seen["query"] == "vestibular schwannoma radiosurgery outcomes"
    assert result["rendered_query"] == "vestibular schwannoma radiosurgery outcomes"
    assert result["query_plan"] is query_plan
    assert result["query_plan_metadata"]["available_pubmed_queries"] == 2
    assert result["query_plan_metadata"]["selected_query_id"] == "therapy-primary"
    assert result["query_plan_metadata"]["selected_query_axis"] == "therapy"
    assert result["query_plan_metadata"]["selection_scope"] == "first_pubmed_query"


@pytest.mark.asyncio
async def test_structured_pubmed_max_axes_metadata_tracks_actual_searches(monkeypatch):
    query_plan = {
        "queries": [
            {
                "id": "therapy-primary",
                "retriever": "pubmed",
                "axis": "therapy",
                "query": "vestibular schwannoma radiosurgery outcomes",
            },
            {
                "id": "complications-secondary",
                "retriever": "pubmed",
                "axis": "complications",
                "query": "vestibular schwannoma facial nerve complications",
            },
        ]
    }
    sent_queries = []

    async def fake_search(query, max_results, filter_type):
        sent_queries.append(query)
        assert max_results == 1
        if query == "vestibular schwannoma radiosurgery outcomes":
            return ["555"], 1
        raise AssertionError("second planned query should not be searched")

    async def fake_summaries(pmids):
        assert pmids == ["555"]
        return [
            {
                "pmid": "555",
                "title": "Radiosurgery outcomes",
                "authors": "Doe J",
                "source": "Neurosurgery",
                "pubdate": "2026",
                "pub_types": [],
                "doi": "",
                "url": "https://pubmed.ncbi.nlm.nih.gov/555/",
            }
        ]

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)
    monkeypatch.setattr(mcp_server, "_pubmed_summaries", fake_summaries)

    result = await mcp_server._handle_pubmed_structured(
        {
            "query": "vestibular schwannoma",
            "query_plan": query_plan,
            "retrieval_strategy": "hybrid",
            "max_axes": 2,
            "max_results": 1,
        }
    )

    assert sent_queries == ["vestibular schwannoma radiosurgery outcomes"]
    assert result["rendered_query"] == "vestibular schwannoma radiosurgery outcomes"
    metadata = result["query_plan_metadata"]
    assert metadata["available_pubmed_queries"] == 2
    assert metadata["selected_pubmed_queries"] == 2
    assert metadata["selected_query_ids"] == [
        "therapy-primary",
        "complications-secondary",
    ]
    assert metadata["searched_pubmed_queries"] == 1
    assert metadata["searched_query_ids"] == ["therapy-primary"]
    assert metadata["searched_query_axes"] == ["therapy"]


@pytest.mark.asyncio
async def test_structured_pubmed_malformed_query_plan_falls_back_to_original(monkeypatch):
    sent_queries = []

    async def fake_search(query, max_results, filter_type):
        sent_queries.append(query)
        return [], 0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)

    result = await mcp_server._handle_pubmed_structured(
        {
            "query": "original fallback query",
            "query_plan": ["not", "a", "dict"],
            "retrieval_strategy": "hybrid",
        }
    )

    assert sent_queries == ["original fallback query"]
    assert result["rendered_query"] == "original fallback query"
    assert "query_plan_metadata" not in result
    assert result["warnings"]
    assert "Malformed query_plan" in result["warnings"][0]


@pytest.mark.asyncio
async def test_structured_pubmed_first_pubmed_query_spec_falls_back_to_original(monkeypatch):
    query_plan = {
        "queries": [
            {
                "id": "query-spec-primary",
                "retriever": "pubmed",
                "axis": "therapy",
                "query_spec": {"terms": ["vestibular schwannoma", "radiosurgery"]},
            },
            {
                "id": "rendered-secondary",
                "retriever": "pubmed",
                "axis": "complications",
                "query": "secondary query should not be searched",
            },
        ]
    }
    seen = {"query": None}

    async def fake_search(query, max_results, filter_type):
        seen["query"] = query
        return [], 0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)

    result = await mcp_server._handle_pubmed_structured(
        {
            "query": "original fallback query",
            "query_plan": query_plan,
            "retrieval_strategy": "hybrid",
        }
    )

    assert seen["query"] == "original fallback query"
    assert result["rendered_query"] == "original fallback query"
    assert result["query_plan_metadata"]["available_pubmed_queries"] == 2
    assert result["query_plan_metadata"]["searched_pubmed_queries"] == 0
    assert "selected_query_id" not in result["query_plan_metadata"]
    assert result["warnings"]
    assert "Selected PubMed query_plan entry" in result["warnings"][0]


@pytest.mark.asyncio
async def test_structured_pubmed_skips_non_pubmed_plan_queries(monkeypatch):
    query_plan = {
        "queries": [
            {
                "id": "local-primary",
                "retriever": "local_corpus",
                "axis": "therapy",
                "query": "local-only query",
            },
            {
                "id": "pubmed-secondary",
                "retriever": "pubmed",
                "axis": "complications",
                "query": "pubmed selected query",
            },
        ]
    }
    seen = {"query": None}

    async def fake_search(query, max_results, filter_type):
        seen["query"] = query
        return [], 0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)

    result = await mcp_server._handle_pubmed_structured(
        {
            "query": "original query",
            "query_plan": query_plan,
            "retrieval_strategy": "hybrid",
        }
    )

    assert seen["query"] == "pubmed selected query"
    assert result["query_plan_metadata"]["available_pubmed_queries"] == 1
    assert result["query_plan_metadata"]["selected_query_id"] == "pubmed-secondary"


@pytest.mark.asyncio
async def test_structured_pubmed_nonlegacy_without_pubmed_plan_query_degrades_to_original(monkeypatch):
    query_plan = {
        "queries": [
            {
                "id": "local-primary",
                "retriever": "local_corpus",
                "axis": "therapy",
                "query": "local-only query",
            }
        ]
    }
    seen = {"query": None}

    async def fake_search(query, max_results, filter_type):
        seen["query"] = query
        return [], 0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)

    result = await mcp_server._handle_pubmed_structured(
        {
            "query": "original fallback query",
            "query_plan": query_plan,
            "retrieval_strategy": "hybrid",
        }
    )

    assert seen["query"] == "original fallback query"
    assert result["rendered_query"] == "original fallback query"
    assert result["query_plan_metadata"]["available_pubmed_queries"] == 0
    assert result["warnings"]
    assert "No PubMed query found in query_plan" in result["warnings"][0]


@pytest.mark.asyncio
async def test_handle_pubmed_routes_through_structured_helper(monkeypatch):
    seen = {"args": None}

    async def fake_structured(args):
        seen["args"] = args
        return {
            "query": args["query"],
            "rendered_query": args["query"],
            "query_plan": None,
            "retrieval_strategy": "legacy",
            "total": 1,
            "articles": [],
            "markdown": "## PubMed — bypass\n(1 shown of 1 total)\n",
        }

    monkeypatch.setattr(mcp_server, "_handle_pubmed_structured", fake_structured)

    args = {"query": "bypass", "max_results": 1}
    markdown = await mcp_server._handle_pubmed(args)

    assert seen["args"] is args
    assert markdown == "## PubMed — bypass\n(1 shown of 1 total)\n"


@pytest.mark.asyncio
async def test_handle_pubmed_default_markdown_has_no_query_plan(monkeypatch):
    query_plan = {"strategy": "legacy", "queries": ["aneurysm"]}

    async def fake_search(query, max_results, filter_type):
        return ["333"], 1

    async def fake_summaries(pmids):
        return [
            {
                "pmid": "333",
                "title": "Aneurysm paper",
                "authors": "Doe J",
                "source": "Neurosurgery",
                "pubdate": "2026",
                "pub_types": [],
                "doi": "",
                "url": "https://pubmed.ncbi.nlm.nih.gov/333/",
            }
        ]

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)
    monkeypatch.setattr(mcp_server, "_pubmed_summaries", fake_summaries)

    markdown = await mcp_server._handle_pubmed(
        {"query": "aneurysm", "query_plan": query_plan}
    )

    assert "## PubMed — aneurysm" in markdown
    assert "## Query plan" not in markdown


@pytest.mark.asyncio
async def test_handle_pubmed_return_query_plan_appends_compact_section(monkeypatch):
    query_plan = {
        "strategy": "legacy",
        "rendered_query": "aneurysm",
        "queries": ["aneurysm", "aneurysm outcomes"],
    }

    async def fake_search(query, max_results, filter_type):
        return ["444"], 1

    async def fake_summaries(pmids):
        return [
            {
                "pmid": "444",
                "title": "Aneurysm outcomes",
                "authors": "Roe J",
                "source": "J Neurosurg",
                "pubdate": "2026",
                "pub_types": [],
                "doi": "",
                "url": "https://pubmed.ncbi.nlm.nih.gov/444/",
            }
        ]

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)
    monkeypatch.setattr(mcp_server, "_pubmed_summaries", fake_summaries)

    markdown = await mcp_server._handle_pubmed(
        {
            "query": "aneurysm",
            "query_plan": query_plan,
            "return_query_plan": True,
        }
    )

    assert "## PubMed — aneurysm" in markdown
    assert "## Query plan" in markdown
    assert "retrieval_strategy: legacy" in markdown
    assert "rendered_query: aneurysm" in markdown
    assert "queries: aneurysm; aneurysm outcomes" in markdown


@pytest.mark.asyncio
async def test_structured_pubmed_invalid_strategy_degrades_to_legacy_with_warning(monkeypatch):
    async def fake_search(query, max_results, filter_type):
        return [], 0

    monkeypatch.setattr(mcp_server, "_pubmed_search", fake_search)

    result = await mcp_server._handle_pubmed_structured(
        {"query": "aneurysm", "retrieval_strategy": "expanded"}
    )

    assert result["retrieval_strategy"] == "legacy"
    assert result["warnings"]
    assert "Invalid retrieval_strategy" in result["warnings"][0]
