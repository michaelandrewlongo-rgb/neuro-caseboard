import asyncio
import os

import pytest

from neuro_caseboard.literature.pubmed_client import PubMedClient

pytestmark = pytest.mark.skipif(
    not (os.environ.get("NCBI_API_KEY") or os.environ.get("NCBI_API_KEY_2")),
    reason="no NCBI key in env; live PubMed smoke test skipped",
)


def test_live_search_returns_pmids():
    key = os.environ.get("NCBI_API_KEY") or os.environ.get("NCBI_API_KEY_2")
    client = PubMedClient(api_key=key)
    pmids, total = asyncio.run(
        client.search("mechanical thrombectomy large vessel occlusion", max_results=5))
    assert pmids and total > 0
