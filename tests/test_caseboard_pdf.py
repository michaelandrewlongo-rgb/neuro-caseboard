"""Guard the build (Dossier) Executive-Navy HTML builder — proves the exec_navy extraction
left the build pathway's output intact (this builder had no offline test before)."""
from neuro_caseboard.caseboard_pdf import build_caseboard_html
from neuro_caseboard.model import Dossier, EvidenceSummary, Section, Claim, Provenance


def _dossier():
    return Dossier(
        title="C5–6 ACDF",
        summary=EvidenceSummary(supported=2, to_verify=1, quarantined=0),
        sections=[Section(
            heading="Anatomy at risk", intro="Structures near the approach.",
            claims=[Claim(text="The **vertebral artery** runs in the foramen transversarium.",
                          why="Avoid far-lateral dissection.", status="supported")])])


def test_build_caseboard_html_carries_exec_navy_tokens_and_content():
    doc = build_caseboard_html(_dossier(), subtitle="cervical case")
    assert "NEURO·CASEBOARD" in doc                 # masthead brand
    assert "DM+Sans" in doc and "Space+Mono" in doc      # Neo Brutalism fonts
    assert "#6b93ff" in doc                              # Signal (dark) blue accent
    assert "C5–6 ACDF" in doc                       # title
    assert "<b>vertebral artery</b>" in doc              # inline bold via shared helper
    assert "Corpus-supported" in doc                     # status-marker label


def test_build_caseboard_html_has_per_page_verify_banner():
    # WS-5: a standing confidentiality/verify banner, position:fixed so it repeats on every page.
    doc = build_caseboard_html(_dossier())
    assert "verify-banner" in doc
    assert "the surgeon verifies every recommendation" in doc
    assert "position:fixed" in doc


def test_build_caseboard_html_renders_section_literature_axis():
    # WS-5/WS-3: a section's contemporary-literature block renders with [L#], separate from claims.
    from types import SimpleNamespace
    lit = SimpleNamespace(
        narrative="Recent RCTs support decompression [L1].",
        citations=[SimpleNamespace(n=1, title="ACDF RCT", journal="Spine", year=2024,
                                   doi="10.1/abc", url="")])
    d = Dossier(title="Case Dossier — C5-6 ACDF",
                summary=EvidenceSummary(to_verify=1),
                sections=[Section(heading="Clinical Reasoning",
                                  claims=[Claim(text="Indicated", why="progressive")],
                                  literature=lit)])
    doc = build_caseboard_html(d)
    assert "Contemporary Literature" in doc
    assert "[L1]" in doc and "ACDF RCT" in doc
    assert "https://doi.org/10.1/abc" in doc


def test_build_caseboard_html_signal_is_dark_print_is_light():
    dark = build_caseboard_html(_dossier(), subtitle="X", theme="signal")
    light = build_caseboard_html(_dossier(), subtitle="X", theme="print")
    assert "--bg:#000000" in dark and "--accent:#6b93ff" in dark
    assert "--bg:#ffffff" in light and "--accent:#2a52cc" in light


def test_build_caseboard_html_defaults_to_signal():
    assert "--bg:#000000" in build_caseboard_html(_dossier(), subtitle="X")


def _degraded_dossier():
    d = _dossier()
    d.provenance = Provenance(source="deterministic", degraded=True, reason="llm_error")
    return d


def test_fallback_banner_css_is_tokenized_and_legible_on_both_grounds():
    # The degraded-dossier banner is appended AFTER base_css(theme); it must read on the dark
    # default (--bg:#000000) ground, so it carries CSS tokens — never the old hardcoded amber.
    doc = build_caseboard_html(_degraded_dossier())
    assert 'class="fallback-banner"' in doc          # banner actually rendered (dossier degraded)
    assert "#a9781b" not in doc                       # old hardcoded amber rail — gone
    assert "#7a5a14" not in doc                       # old hardcoded dark-mustard text — gone
    # Tokenized: amber identity in the rail/label via --verify, frame + body via panel/line/ink.
    assert "border-left:4px solid var(--verify)" in doc
    assert "background:var(--panel)" in doc
    assert "color:var(--ink)" in doc

    # And the same on the print ground — still tokens, still no hardcoded hexes.
    light = build_caseboard_html(_degraded_dossier(), theme="print")
    assert "#a9781b" not in light and "#7a5a14" not in light
    assert "var(--verify)" in light


def test_fallback_banner_css_absent_on_clean_dossier():
    # The banner CSS is injected only when degraded, so the class never leaks into normal output.
    assert "fallback-banner" not in build_caseboard_html(_dossier())
