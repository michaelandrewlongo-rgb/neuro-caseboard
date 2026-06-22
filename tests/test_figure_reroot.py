"""Figure paths are stored in the index as absolute *build-time* host paths
(e.g. /home/michael/neuro-textbook-rag/assets/figures/<book>/p0026.png). The Docker image mounts
that same tree at a different location (/data/figures, ASSETS_DIR=/data/figures), so the literal
stored path does not exist in the container and every figure was served as image_available:false /
/api/figure 404. _safe_image_path must re-root the stored path's tail onto the runtime ASSETS_DIR
so the mounted file resolves — without weakening the traversal guard or serving files outside the
whitelisted roots.
"""
from pathlib import Path

import pytest

pytest.importorskip("fastapi")


def test_reroots_stale_build_time_host_path(tmp_path, monkeypatch):
    # Runtime assets dir (the container's /data/figures stand-in) holds the real file.
    runtime_figs = tmp_path / "data" / "figures"
    (runtime_figs / "Benzel Spine").mkdir(parents=True)
    real = runtime_figs / "Benzel Spine" / "p0026.png"
    real.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setenv("ASSETS_DIR", str(runtime_figs))

    import api.server as server

    # The index stored a build-time host path that does NOT exist in this (container-like) env.
    # Use an absent build prefix so the test is hermetic on the box that *does* hold the real index.
    stored = str(tmp_path / "build" / "assets" / "figures" / "Benzel Spine" / "p0026.png")
    assert not Path(stored).is_file()  # precondition: literal path absent

    got = server._safe_image_path(stored)
    assert got is not None
    assert got.samefile(real)


def test_literal_path_still_served_unchanged(tmp_path, monkeypatch):
    # Regression: when the literal stored path DOES exist under ASSETS_DIR (native run), unchanged.
    runtime_figs = tmp_path / "data" / "figures"
    (runtime_figs / "Book").mkdir(parents=True)
    real = runtime_figs / "Book" / "p1.png"
    real.write_bytes(b"\x89PNG")
    monkeypatch.setenv("ASSETS_DIR", str(runtime_figs))

    import api.server as server

    assert server._safe_image_path(str(real)).samefile(real)


def test_rejects_traversal_and_unmounted_paths(tmp_path, monkeypatch):
    # Security: re-rooting must not become an arbitrary file read.
    runtime_figs = tmp_path / "data" / "figures"
    runtime_figs.mkdir(parents=True)
    monkeypatch.setenv("ASSETS_DIR", str(runtime_figs))

    import api.server as server

    # A real file that exists but lives outside every whitelisted root.
    assert server._safe_image_path("/etc/hostname") is None
    # A figures-anchored path whose target was never mounted -> no file -> rejected.
    assert server._safe_image_path("/home/x/assets/figures/Book/missing.png") is None
    # Traversal dressed up under a figures anchor must not escape the root.
    assert server._safe_image_path(
        "/home/x/assets/figures/../../../../etc/hostname") is None
