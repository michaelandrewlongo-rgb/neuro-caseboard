"""Build search URLs for neurosurgical reference sources."""

import urllib.parse

SOURCES: dict[str, str] = {
    "PubMed": "https://pubmed.ncbi.nlm.nih.gov/?term={query}",
    "Surgical Neurology International": "https://surgicalneurologyint.com/?s={query}",
}


def build_search_links(topic: str) -> dict[str, str]:
    """Return a dict mapping source name → search URL for a topic.

    Topic is URL-encoded so spaces/special characters become safe query params.
    """
    query = urllib.parse.quote_plus(topic.strip())
    return {name: url.format(query=query) for name, url in SOURCES.items()}
