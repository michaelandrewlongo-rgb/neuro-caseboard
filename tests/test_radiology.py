"""Tests for caseprep radiology — Open-i search, relevance filtering, image download."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from caseprep.mcp_server import _download_images, _openi_search, _query_terms


# ── _query_terms ──────────────────────────────────────────────────────────────

class TestQueryTerms:
    def test_basic_split(self):
        terms = _query_terms("vestibular schwannoma MRI")
        assert "vestibular" in terms
        assert "schwannoma" in terms
        assert "mri" in terms

    def test_stop_words_removed(self):
        terms = _query_terms("for the treatment of glioma")
        assert "for" not in terms
        assert "the" not in terms
        assert "of" not in terms
        assert "treatment" in terms
        assert "glioma" in terms

    def test_short_tokens_dropped(self):
        terms = _query_terms("a CT of CPA angle at L2")
        assert "a" not in terms
        assert "ct" in terms  # 2 chars — accepted
        assert "cpa" in terms
        assert "angle" in terms
        assert "l2" in terms   # 2 chars — accepted

    def test_punctuation_stripped(self):
        terms = _query_terms("vestibular schwannoma (MRI), CPA-angle")
        assert "vestibular" in terms
        assert "schwannoma" in terms
        assert "mri" in terms
        assert "cpa" in terms
        assert "angle" in terms

    def test_deduplication(self):
        terms = _query_terms("mri mri MRI schwannoma schwannoma")
        assert terms.count("mri") == 1
        assert terms.count("schwannoma") == 1

    def test_empty_returns_empty(self):
        assert _query_terms("") == []
        assert _query_terms("  ") == []

    def test_only_stop_words(self):
        terms = _query_terms("for the and of")
        assert terms == []

    def test_order_preserved(self):
        terms = _query_terms("alpha beta gamma")
        assert terms == ["alpha", "beta", "gamma"]


# ── _openi_search with relevance filtering ───────────────────────────────────

_MOCK_OPENI_RESPONSE = {
    "total": 5,
    "list": [
        {
            "uid": "1", "pmid": "111", "title": "Vestibular Schwannoma MRI Findings",
            "journal_title": "J Neurosurg", "authors": "Doe J",
            "imgLarge": "/img/large1.png", "imgThumb": "/img/thumb1.png",
            "image": {"caption": "Axial T1-weighted MRI showing a left CPA schwannoma"},
            "journal_date": {"year": "2020", "month": "01", "day": "15"},
        },
        {
            "uid": "2", "pmid": "222", "title": "Hemangioblastoma of the Posterior Fossa",
            "journal_title": "Acta Neurochir", "authors": "Smith K",
            "imgLarge": "/img/large2.png", "imgThumb": "/img/thumb2.png",
            "image": {"caption": "Hemangioblastoma with cystic component"},
            "journal_date": {"year": "2019", "month": "06", "day": "01"},
        },
        {
            "uid": "3", "pmid": "333", "title": "Schwannoma Resection Outcomes",
            "journal_title": "Neurosurgery", "authors": "Lee M",
            "imgLarge": "/img/large3.png", "imgThumb": "/img/thumb3.png",
            "image": {"caption": "Intraoperative schwannoma image"},
            "journal_date": {"year": "2021", "month": "03", "day": "10"},
        },
        {
            "uid": "4", "pmid": "444", "title": "CPA Meningioma vs Schwannoma",
            "journal_title": "Neuroradiology", "authors": "Park S",
            "imgLarge": "/img/large4.png", "imgThumb": "/img/thumb4.png",
            "image": {"caption": "Differential diagnosis of CPA masses"},
            "journal_date": {"year": "2022", "month": "08", "day": "22"},
        },
        {
            "uid": "5", "pmid": "555", "title": "Vestibular Neuroma Imaging",
            "journal_title": "AJNR", "authors": "Chen R",
            "imgLarge": "/img/large5.png", "imgThumb": "/img/thumb5.png",
            "image": {"caption": "T2 weighted axial MRI"},
            "journal_date": {"year": "2023", "month": "01", "day": "05"},
        },
    ],
}


class TestOpenISearch:
    @pytest.mark.asyncio
    async def test_basic_search_no_filter(self):
        """Without query_terms, all results pass through."""
        with patch("caseprep.mcp_server._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(), json=lambda: _MOCK_OPENI_RESPONSE,
            ))
            results, total = await _openi_search("vestibular schwannoma", max_results=5)
            assert total == 5
            assert len(results) == 5

    @pytest.mark.asyncio
    async def test_relevance_filter_excludes_hemangioblastoma(self):
        """Hemangioblastoma result should be excluded when searching schwannoma."""
        with patch("caseprep.mcp_server._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(), json=lambda: _MOCK_OPENI_RESPONSE,
            ))
            terms = _query_terms("vestibular schwannoma")
            results, total = await _openi_search(
                "vestibular schwannoma", max_results=5, query_terms=terms,
            )
            titles = [r["title"] for r in results]
            assert "Hemangioblastoma of the Posterior Fossa" not in titles
            assert any("Schwannoma" in t or "schwannoma" in r["caption"]
                       for t in [r["title"] for r in results]
                       for r in results
                       if "schwannoma" in r["caption"] or "Schwannoma" in t)

    @pytest.mark.asyncio
    async def test_caption_based_match(self):
        """Image 5 has no query term in title, but 'mri' in caption should let it through."""
        with patch("caseprep.mcp_server._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(), json=lambda: _MOCK_OPENI_RESPONSE,
            ))
            terms = _query_terms("mri")
            results, total = await _openi_search("mri", max_results=5, query_terms=terms)
            # Result 5 has "MRI" in caption -> should be included
            titles = [r["title"] for r in results]
            assert "Vestibular Schwannoma MRI Findings" in titles
            # Result 2 has no "mri" in title or caption -> excluded
            assert "Hemangioblastoma of the Posterior Fossa" not in titles

    @pytest.mark.asyncio
    async def test_max_results_capped(self):
        """Even with many matches, we cap at max_results."""
        with patch("caseprep.mcp_server._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(), json=lambda: _MOCK_OPENI_RESPONSE,
            ))
            results, _ = await _openi_search("vestibular schwannoma", max_results=2)
            assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_modality_code_passed(self):
        """Modality is mapped to the correct Open-i it= code."""
        with patch("caseprep.mcp_server._client") as mock_client:
            mock_get = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(), json=lambda: _MOCK_OPENI_RESPONSE,
            ))
            mock_client.return_value.get = mock_get
            await _openi_search("schwannoma", max_results=3, modality="mri")
            call_args = mock_get.call_args
            assert call_args[1]["params"]["it"] == "m"

    @pytest.mark.asyncio
    async def test_default_modality_is_x(self):
        """Default modality 'any' maps to 'x' (general radiology)."""
        with patch("caseprep.mcp_server._client") as mock_client:
            mock_get = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(), json=lambda: _MOCK_OPENI_RESPONSE,
            ))
            mock_client.return_value.get = mock_get
            await _openi_search("schwannoma", max_results=3)
            call_args = mock_get.call_args
            assert call_args[1]["params"]["it"] == "x"

    @pytest.mark.asyncio
    async def test_fetches_more_than_requested(self):
        """When filtering is active, fetch_n > max_results."""
        with patch("caseprep.mcp_server._client") as mock_client:
            mock_get = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(), json=lambda: _MOCK_OPENI_RESPONSE,
            ))
            mock_client.return_value.get = mock_get
            terms = _query_terms("vestibular schwannoma")
            await _openi_search("vestibular schwannoma", max_results=3, query_terms=terms)
            call_args = mock_get.call_args
            fetch_n = int(call_args[1]["params"]["n"])
            assert fetch_n > 3  # should fetch more than max_results when filtering


# ── _download_images ─────────────────────────────────────────────────────────

class TestDownloadImages:
    @pytest.fixture
    def sample_results(self):
        return [
            {
                "uid": "img001", "pmid": "111111",
                "img_large": "https://openi.nlm.nih.gov/imgs/large/001.png",
                "img_grid": "", "img_thumb": "",
                "title": "Test Image 1", "caption": "Test caption",
                "journal": "J Test", "authors": "Author A", "pubdate": "2024",
            },
            {
                "uid": "img002", "pmid": "222222",
                "img_large": "", "img_grid": "https://openi.nlm.nih.gov/imgs/grid/002.jpg",
                "img_thumb": "",
                "title": "Test Image 2", "caption": "Test caption 2",
                "journal": "J Test", "authors": "Author B", "pubdate": "2023",
            },
        ]

    @pytest.mark.asyncio
    async def test_downloads_and_saves_files(self, sample_results):
        """Downloaded images are saved to the output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal PNG
            jpg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100    # minimal JPEG

            mock_resp1 = MagicMock(
                content=png_bytes,
                headers={"content-type": "image/png"},
            )
            mock_resp2 = MagicMock(
                content=jpg_bytes,
                headers={"content-type": "image/jpeg"},
            )

            with patch("caseprep.mcp_server._client") as mock_client:
                mock_client.return_value.get = AsyncMock(
                    side_effect=[mock_resp1, mock_resp2],
                )
                results = await _download_images(sample_results, out)
                assert out.is_dir()
                files = sorted(out.iterdir())
                assert len(files) == 2
                assert files[0].suffix == ".png"
                assert files[1].suffix == ".jpg"
                assert "local_path" in results[0]
                assert "local_path" in results[1]

    @pytest.mark.asyncio
    async def test_no_image_url_sets_error(self, sample_results):
        """When no image URL exists, local_path gets an error string."""
        sample_results[0]["img_large"] = ""
        sample_results[0]["img_grid"] = ""
        sample_results[0]["img_thumb"] = ""
        with patch("caseprep.mcp_server._client") as mock_client:
            mock_client.return_value.get = AsyncMock(return_value=MagicMock(
                content=b"", headers={"content-type": "image/jpeg"},
            ))
            with tempfile.TemporaryDirectory() as tmpdir:
                results = await _download_images(sample_results, Path(tmpdir))
            assert results[0]["local_path"].startswith("Error")

    @pytest.mark.asyncio
    async def test_http_error_captured(self, sample_results):
        """HTTP errors are captured as error strings, not raised."""
        with patch("caseprep.mcp_server._client") as mock_client:
            bad_resp = MagicMock()
            bad_resp.raise_for_status = MagicMock(
                side_effect=Exception("HTTP 500"))
            mock_client.return_value.get = AsyncMock(return_value=bad_resp)
            with tempfile.TemporaryDirectory() as tmpdir:
                results = await _download_images(sample_results[:1], Path(tmpdir))
            assert results[0]["local_path"].startswith("Error")

    @pytest.mark.asyncio
    async def test_max_images_capped(self, sample_results):
        """Only max_images results are downloaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            with patch("caseprep.mcp_server._client") as mock_client:
                mock_client.return_value.get = AsyncMock(return_value=MagicMock(
                    content=png_bytes,
                    headers={"content-type": "image/png"},
                ))
                await _download_images(sample_results, out, max_images=1)
                files = list(out.iterdir())
                assert len(files) == 1

    @pytest.mark.asyncio
    async def test_extension_from_url_fallback(self, sample_results):
        """When content-type is missing, fall back to URL extension."""
        sample_results[0]["img_large"] = "https://example.com/img.png"
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            with patch("caseprep.mcp_server._client") as mock_client:
                mock_client.return_value.get = AsyncMock(return_value=MagicMock(
                    content=png_bytes,
                    headers={},  # no content-type
                ))
                results = await _download_images(sample_results[:1], out)
                local = Path(results[0]["local_path"])
                assert local.suffix == ".png"
