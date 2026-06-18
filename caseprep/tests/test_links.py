"""Tests for caseprep.links — URL generation."""

import pytest
from caseprep.links import build_search_links, SOURCES


class TestBuildSearchLinks:
    def test_returns_all_sources(self):
        links = build_search_links("vestibular schwannoma")
        assert set(links.keys()) == set(SOURCES.keys())

    def test_spaces_are_encoded(self):
        links = build_search_links("brain tumor")
        for url in links.values():
            assert " " not in url
            assert "brain+tumor" in url or "brain%20tumor" in url

    def test_special_characters_are_encoded(self):
        links = build_search_links("C7-T1 fracture/dislocation")
        pubmed = links["PubMed"]
        assert "C7-T1" in pubmed
        assert " " not in pubmed

    def test_topic_is_stripped(self):
        links = build_search_links("  glioma  ")
        pubmed = links["PubMed"]
        assert "+" not in pubmed.split("term=")[1][:2]  # no leading +

    def test_pubmed_url_is_correct(self):
        links = build_search_links("meningioma")
        assert links["PubMed"] == "https://pubmed.ncbi.nlm.nih.gov/?term=meningioma"

    def test_sni_url_is_correct(self):
        links = build_search_links("large core thrombectomy")
        expected = "https://surgicalneurologyint.com/?s=large+core+thrombectomy"
        assert links["Surgical Neurology International"] == expected


class TestSourcesConstant:
    def test_exactly_two_api_sources(self):
        assert len(SOURCES) == 2
        assert "PubMed" in SOURCES
        assert "Surgical Neurology International" in SOURCES

    def test_all_urls_are_https(self):
        for name, url in SOURCES.items():
            assert url.startswith("https://"), f"{name} should use HTTPS: {url}"
