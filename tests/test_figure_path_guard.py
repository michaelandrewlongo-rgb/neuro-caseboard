"""Structural guard against the *figure-path remap* bug class (PR #54).

Stored figure paths are absolute build-time HOST paths; any runtime that mounts the assets tree
elsewhere (Docker: ``ASSETS_DIR=/data/figures``) makes the literal path nonexistent, so a raw
``open()`` / ``is_file()`` on a stored figure path silently drops the plate. The fix funnels every
figure-path read through ``neuro_core.asset_paths.resolve_asset_path``. The bug resurfaced in
*seven* scattered gates because the mistake — a raw fs primitive on a stored path — is easy to
re-add in a new module and invisible on a native dev box (``ASSETS_DIR`` defaults to the build
path, so the literal path happens to exist there).

``test_no_unguarded_figure_path_reads`` freezes the set of raw existence/binary-read primitives in
the runtime packages. A NEW one fails the test: either route the path through ``resolve_asset_path``,
or — if it is provably NOT a stored asset path (an index dir, a credential file, the SPA bundle) —
add the exact line to ``ALLOWLIST``.
"""
import re
from pathlib import Path

import pytest

# Existence checks + binary/image reads — the surfaces where a stored figure path silently fails
# under a remapped ASSETS_DIR. Text open() of configs/json is a different surface, out of scope.
ANTIPATTERN = re.compile(
    r'os\.path\.is(?:file|dir)\(|os\.path\.exists\(|\.is_file\(\)|Image\.open\(|open\([^)]*["\']rb["\']'
)
PKG_ROOTS = ["neuro_core", "neuro_caseboard", "api"]
EXCLUDE_DIRS = {"scripts", "figures_gen"}      # offline build lanes: run on the host, paths are literal
EXCLUDE_FILES = {"neuro_core/asset_paths.py"}  # the resolver itself

# Every entry is provably safe: it either resolves via resolve_asset_path, or touches a non-figure
# path (index dir / ADC credential / SPA static bundle). Adding a figure read here instead of
# resolving it re-opens the bug — don't.
ALLOWLIST = {
    "neuro_core/figure_retriever.py: if os.path.isdir(index_dir):",
    "neuro_core/figure_retriever.py: if cap and fp and resolve_asset_path(fp, assets_dir).is_file():",
    'neuro_core/query.py: with open(path, "rb") as f:',  # path resolved at the call site (Engine._collect_figures)
    'neuro_core/visual_embed.py: imgs = [self.preprocess(Image.open(p).convert("RGB")) for p in paths]',  # build/visual lane
    'neuro_caseboard/exec_navy.py: with open(resolved, "rb") as f:',  # resolved inside img_data_uri
    'neuro_caseboard/retrieve.py: if getattr(h, "has_figure", False) and fp and resolve_asset_path(fp, load_config().assets_dir).is_file():',
    "neuro_caseboard/retrieve.py: if not os.path.isdir(index_dir):",
    "neuro_caseboard/retrieve.py: enable_textbook = os.path.isdir(_default_index_dir())",
    "neuro_caseboard/briefing_pdf.py: if resolved and resolved.is_file():",
    "neuro_caseboard/render_pdf.py: if resolved and resolved.is_file():",
    "api/server.py: if explicit and Path(explicit).is_file():",          # ADC credential
    "api/server.py: return default.is_file()",                           # ADC credential
    "api/server.py: if not cand.is_file():",                             # _safe_image_path, post-reroot
    "api/server.py: if not index.is_file():",                            # SPA index.html
    "api/server.py: if candidate.is_file() and (candidate == dist_root or dist_root in candidate.parents):",  # SPA bundle
}


def _scan(repo_root):
    hits = set()
    for r in PKG_ROOTS:
        for p in (repo_root / r).rglob("*.py"):
            rel = p.relative_to(repo_root).as_posix()
            if rel in EXCLUDE_FILES or set(p.parts) & EXCLUDE_DIRS:
                continue
            for line in p.read_text().splitlines():
                if ANTIPATTERN.search(line):
                    hits.add(f"{rel}: {line.strip()}")
    return hits


def test_no_unguarded_figure_path_reads():
    repo_root = Path(__file__).resolve().parent.parent
    new = _scan(repo_root) - ALLOWLIST
    assert not new, (
        "New raw filesystem read(s) on a path in a runtime module:\n  "
        + "\n  ".join(sorted(new))
        + "\n\nStored figure/asset paths are absolute build-time host paths and DO NOT exist when "
        "the assets tree is mounted elsewhere (Docker: ASSETS_DIR). Route the path through "
        "neuro_core.asset_paths.resolve_asset_path before reading it. If this is provably NOT a "
        "stored asset path (an index dir, credential file, or the SPA bundle), add the exact line "
        "to ALLOWLIST in tests/test_figure_path_guard.py."
    )


def test_img_data_uri_reroots_remapped_assets(tmp_path, monkeypatch):
    """Behavioral proof for the gate-6/7 fix: img_data_uri (the PDF builders' shared image-embed
    helper) must resolve a stale build-time host path onto the runtime ASSETS_DIR — otherwise a
    Docker-style remap makes open() raise and the swallowing try/except drops the plate silently."""
    runtime = tmp_path / "data" / "figures"
    (runtime / "Book").mkdir(parents=True)
    (runtime / "Book" / "p1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setenv("ASSETS_DIR", str(runtime))

    from neuro_caseboard.exec_navy import img_data_uri

    # The index stored a build-time host path that does NOT exist in this (container-like) env.
    stored = str(tmp_path / "build" / "assets" / "figures" / "Book" / "p1.png")
    assert not Path(stored).is_file()  # precondition: literal path absent

    uri = img_data_uri(stored)
    assert uri.startswith("data:image/png;base64,")

    # And it must still raise (not silently succeed) when the file is genuinely missing everywhere,
    # so the caller's try/except can honestly drop a corrupt plate.
    with pytest.raises(OSError):
        img_data_uri(str(tmp_path / "build" / "assets" / "figures" / "Book" / "gone.png"))
