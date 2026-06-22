"""resolve_asset_path / reroot_candidates bridge an index built at one assets location to one
read at another (the container mounts figures at /data/figures while the index stores absolute
/home/.../assets/figures/... paths). The engine read (query.Engine._read_image) depends on this:
without it, open() on the stale host path fails and figures are silently dropped from ask answers.
"""
from neuro_core.asset_paths import reroot_candidates, resolve_asset_path


def test_resolve_prefers_literal_when_present(tmp_path):
    real = tmp_path / "figures" / "Book" / "p1.png"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"\x89PNG")
    # Literal exists -> returned unchanged, runtime root irrelevant (native-run behavior).
    assert resolve_asset_path(str(real), tmp_path / "elsewhere") == real


def test_resolve_reroots_stale_path_onto_runtime_dir(tmp_path):
    runtime = tmp_path / "data" / "figures"
    (runtime / "Benzel Spine").mkdir(parents=True)
    real = runtime / "Benzel Spine" / "p0026.png"
    real.write_bytes(b"\x89PNG\r\n")
    stale = "/build/host/neuro-textbook-rag/assets/figures/Benzel Spine/p0026.png"
    got = resolve_asset_path(stale, runtime)
    assert got.samefile(real)


def test_resolve_returns_literal_when_nothing_exists(tmp_path):
    runtime = tmp_path / "data" / "figures"
    runtime.mkdir(parents=True)
    stale = "/nope/assets/figures/Book/missing.png"
    # No file anywhere -> literal path back unchanged; the caller's open() then fails cleanly.
    assert str(resolve_asset_path(stale, runtime)) == stale


def test_reroot_candidates_matches_each_root_by_name(tmp_path):
    figs = tmp_path / "figures"
    cards = tmp_path / "cards"
    cands = list(reroot_candidates("/x/assets/figures/Book/p1.png", [figs, cards]))
    # Only the 'figures' root matches the anchor in the path.
    assert cands == [figs / "Book" / "p1.png"]
