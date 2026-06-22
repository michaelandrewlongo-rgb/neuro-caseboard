"""Bridge an index built at one assets location to one served/read at another.

Figure/plate paths are stored in the LanceDB index as absolute *build-time* host paths
(e.g. /home/.../neuro-textbook-rag/assets/figures/<book>/p0026.png). When the assets tree is
mounted somewhere else at runtime — the container mounts it at /data/figures with
ASSETS_DIR=/data/figures — that literal path does not exist, so both the engine read
(neuro_core.query.Engine._read_image) and the API serve (api.server._safe_image_path) fail and
figures silently vanish from ask/dossier. These two helpers re-root a stored path onto the runtime
assets dir. Pure stdlib so any layer can import it without pulling in the heavy engine deps.
"""
from pathlib import Path


def reroot_candidates(stored_path, roots):
    """Yield re-rooted variants of *stored_path*: for each runtime root whose directory name
    appears in the stored path, rebase the tail after that name onto the root. e.g. a stored
    .../figures/<book>/x.png with root /data/figures yields /data/figures/<book>/x.png. The caller
    is responsible for any traversal/whitelist check (api.server resolve()s before trusting these)."""
    parts = Path(stored_path).parts
    for root in roots:
        root = Path(root)
        if root.name in parts:
            i = len(parts) - 1 - parts[::-1].index(root.name)  # last occurrence of the root dir name
            yield root.joinpath(*parts[i + 1:])


def resolve_asset_path(stored_path, *roots):
    """Return the first existing file: the literal *stored_path*, else a re-rooted candidate under
    one of *roots. Returns the literal path unchanged if nothing resolves (caller handles absence).
    For trusted index paths only — no whitelist; do not pass user-supplied input here."""
    p = Path(stored_path)
    if p.is_file():
        return p
    for cand in reroot_candidates(stored_path, roots):
        if cand.is_file():
            return cand
    return p
