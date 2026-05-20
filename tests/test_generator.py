"""Tests for caseprep.generator — output folder generation."""

import tempfile
from pathlib import Path

import pytest
from caseprep.generator import generate_caseprep, _slugify


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestSlugify:
    def test_lowercase(self):
        assert _slugify("Vestibular Schwannoma") == "vestibular-schwannoma"

    def test_strips_whitespace(self):
        assert _slugify("  glioma  ") == "glioma"

    def test_multiple_spaces(self):
        assert _slugify("acoustic  neuroma") == "acoustic--neuroma"


class TestGenerateCaseprep:
    EXPECTED_FILES = [
        "README.md",
        "anatomy.md",
        "approach.md",
        "literature.md",
        "complications.md",
        "resource-links.html",
    ]

    def test_creates_output_directory(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("glioma", out)
        assert out.is_dir()

    def test_creates_all_expected_files(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("glioma", out)
        for filename in self.EXPECTED_FILES:
            assert (out / filename).is_file(), f"missing {filename}"

    def test_topic_appears_in_readme(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("vestibular schwannoma", out)
        readme = (out / "README.md").read_text()
        assert "vestibular schwannoma" in readme

    def test_topic_appears_in_anatomy(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("acoustic neuroma", out)
        anatomy = (out / "anatomy.md").read_text()
        assert "acoustic neuroma" in anatomy

    def test_literature_contains_pubmed_link(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("meningioma", out)
        lit = (out / "literature.md").read_text()
        assert "[PubMed](https://pubmed.ncbi.nlm.nih.gov/?term=meningioma)" in lit

    def test_literature_contains_sni_link(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("glioma", out)
        lit = (out / "literature.md").read_text()
        assert "[Surgical Neurology International]" in lit
        assert "surgicalneurologyint.com" in lit

    def test_resource_html_contains_pubmed(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("glioma", out)
        html = (out / "resource-links.html").read_text()
        assert "pubmed.ncbi.nlm.nih.gov" in html

    def test_resource_html_contains_sni(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("glioma", out)
        html = (out / "resource-links.html").read_text()
        assert "surgicalneurologyint.com" in html

    def test_resource_html_is_valid_html(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("glioma", out)
        html = (out / "resource-links.html").read_text()
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_resource_html_only_two_sources(self, tmp_dir):
        """Only API-backed sources should appear."""
        out = tmp_dir / "test-case"
        generate_caseprep("glioma", out)
        html = (out / "resource-links.html").read_text()
        assert html.count("<li>") == 2
        assert "radiopaedia" not in html.lower()
        assert "neurosurgeryresident" not in html.lower()

    def test_returns_resource_path(self, tmp_dir):
        out = tmp_dir / "test-case"
        result = generate_caseprep("glioma", out)
        assert isinstance(result, Path)
        assert result.name == "resource-links.html"

    def test_relative_output_dir_uses_cwd(self, tmp_dir, monkeypatch):
        monkeypatch.chdir(tmp_dir)
        result = generate_caseprep("glioma", Path("rel-case"))
        assert (tmp_dir / "rel-case").is_dir()
        assert result.parent == tmp_dir / "rel-case"

    def test_existing_directory_is_not_destroyed(self, tmp_dir):
        out = tmp_dir / "test-case"
        out.mkdir()
        (out / "notes.txt").write_text("keep me")
        generate_caseprep("glioma", out)
        assert (out / "notes.txt").read_text() == "keep me"
        assert (out / "README.md").is_file()

    def test_creates_caseprep_schema_files(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("vestibular schwannoma", out)
        expected = [
            "caseprep.yaml",
            "provenance.json",
            "01-case-summary.md",
            "02-imaging-review.md",
            "03-anatomy-at-risk.md",
            "04-operative-plan.md",
            "05-risk-and-rescue.md",
            "06-postop-plan.md",
            "07-evidence.md",
            "08-checklists.md",
            "09-open-questions.md",
        ]
        for filename in expected:
            assert (out / filename).is_file(), f"missing {filename}"

    def test_readme_uses_case_dossier_status(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("vestibular schwannoma", out)
        readme = (out / "README.md").read_text()
        assert "## Preparation Status" in readme
        assert "`needs clinician verification`" in readme
        assert "01-case-summary.md" in readme

    def test_legacy_files_are_schema_aliases(self, tmp_dir):
        out = tmp_dir / "test-case"
        generate_caseprep("vestibular schwannoma", out)
        assert (out / "anatomy.md").read_text() == (out / "03-anatomy-at-risk.md").read_text()
        assert (out / "approach.md").read_text() == (out / "04-operative-plan.md").read_text()
        assert (out / "complications.md").read_text() == (out / "05-risk-and-rescue.md").read_text()
        assert (out / "literature.md").read_text() == (out / "07-evidence.md").read_text()
