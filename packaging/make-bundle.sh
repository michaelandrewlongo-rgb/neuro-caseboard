#!/usr/bin/env bash
# make-bundle.sh — stage a complete, self-contained transfer bundle of neuro-caseboard
# so it can be copied to an external drive and rebuilt on a Mac (or any machine).
#
# WHY a bundle and not "just copy the folder":
#   neuro-caseboard is a 5-layer system. Only the code lives in the repo. The rest —
#   caseprep (external sibling dep), the LanceDB textbook index, the 15G figure assets,
#   and the board-review card bank — live elsewhere on disk and must travel too. The
#   Python venv must NOT travel (its compiled wheels are Linux-x86_64; the Mac is arm64),
#   so it is deliberately excluded and rebuilt on the far side by setup-mac.sh.
#
# USAGE (run on this WSL/Linux machine):
#   packaging/make-bundle.sh /mnt/e/caseboard-bundle      # stage straight onto the USB mount
#   DEST=/mnt/e/caseboard-bundle packaging/make-bundle.sh # same, via env
#   DRY_RUN=1 packaging/make-bundle.sh ./caseboard-bundle # print the plan + sizes, write nothing big
#
# OVERRIDE source locations if yours differ from the defaults:
#   TEXTBOOK_HOME=~/neuro-textbook-rag  (holds index/ and assets/)
#   CARDS_DIR=~/projects/abns-board-review-lancedb
#   CASEPREP_DIR=~/projects/caseprep
set -euo pipefail

# ---- resolve paths -----------------------------------------------------------------------
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SELF/.." && pwd)"

DEST="${1:-${DEST:-./caseboard-bundle}}"
DRY_RUN="${DRY_RUN:-0}"

TEXTBOOK_HOME="${TEXTBOOK_HOME:-$HOME/neuro-textbook-rag}"   # contains index/ + assets/
CARDS_DIR="${CARDS_DIR:-$HOME/projects/abns-board-review-lancedb}"
CASEPREP_DIR="${CASEPREP_DIR:-$HOME/projects/caseprep}"
# Keep this in lockstep with ci/install.sh and .github/workflows/ci.yml.
CASEPREP_REF="${CASEPREP_REF:-8b1d8fd0488c16ff68721c6dc29041862517b392}"

INDEX_DIR="$TEXTBOOK_HOME/index"
ASSETS_DIR="$TEXTBOOK_HOME/assets"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m[err] %s\033[0m\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = "1" ]; then echo "  (dry-run) $*"; else eval "$*"; fi; }

# ---- preflight: every source layer must exist --------------------------------------------
say "Preflight — checking the five source layers"
[ -d "$REPO/.git" ]    || die "repo not found at $REPO"
[ -d "$INDEX_DIR" ]    || die "textbook index not found at $INDEX_DIR (set TEXTBOOK_HOME)"
[ -d "$ASSETS_DIR" ]   || die "figure assets not found at $ASSETS_DIR (set TEXTBOOK_HOME)"
[ -d "$CARDS_DIR" ]    || warn "card bank not found at $CARDS_DIR — Cards mode will be unavailable on the Mac"
[ -d "$CASEPREP_DIR" ] || warn "caseprep not found at $CASEPREP_DIR — Mac will install it from GitHub (needs network)"

repo_sha="$(git -C "$REPO" rev-parse --short HEAD)"
dirty=""; git -C "$REPO" diff --quiet --ignore-submodules HEAD 2>/dev/null || dirty=" +WIP"

printf '  %-26s %8s  %s\n' "repo (code, full .git)" "$(du -sh "$REPO" 2>/dev/null | cut -f1)" "$REPO  [$repo_sha$dirty]"
printf '  %-26s %8s  %s\n' "textbook index"          "$(du -sh "$INDEX_DIR" 2>/dev/null | cut -f1)" "$INDEX_DIR"
printf '  %-26s %8s  %s\n' "figure assets"           "$(du -sh "$ASSETS_DIR" 2>/dev/null | cut -f1)" "$ASSETS_DIR"
[ -d "$CARDS_DIR" ] && printf '  %-26s %8s  %s\n' "board-review cards" "$(du -sh "$CARDS_DIR" 2>/dev/null | cut -f1)" "$CARDS_DIR"

# ---- free-space sanity at the destination ------------------------------------------------
need_kb=$(( $(du -sk "$INDEX_DIR" "$ASSETS_DIR" 2>/dev/null | awk '{s+=$1} END{print s}') ))
[ -d "$CARDS_DIR" ] && need_kb=$(( need_kb + $(du -sk "$CARDS_DIR" | cut -f1) ))
mkdir -p "$DEST"
avail_kb=$(df -Pk "$DEST" | awk 'NR==2{print $4}')
say "Destination: $DEST"
printf '  need ~%s, available %s on target volume\n' \
  "$(numfmt --to=iec $((need_kb*1024)) 2>/dev/null || echo "${need_kb}K")" \
  "$(numfmt --to=iec $((avail_kb*1024)) 2>/dev/null || echo "${avail_kb}K")"
if [ "$avail_kb" -lt "$((need_kb + need_kb/20))" ]; then
  warn "target volume may not have enough free space (need ~5% headroom on top of the payload)"
fi

mkdir -p "$DEST/code" "$DEST/data"

# ---- 1. code: whole repo (history + WIP), minus throwaway/compiled cruft -----------------
# A tar of the repo (its .git is ~1M) faithfully captures committed history AND your
# uncommitted working-tree changes + untracked files (.streamlit/, signal_theme.py, ...),
# which a `git bundle` would silently drop. The venv and caches are excluded — they rebuild.
say "[1/5] code -> code/neuro-caseboard-repo.tar  (full repo incl. .git and WIP)"
run "tar -C '$(dirname "$REPO")' \
  --exclude='neuro-caseboard/.venv' \
  --exclude='neuro-caseboard/.local-ci-venv' \
  --exclude='neuro-caseboard/.local-ci-pkgvenv' \
  --exclude='neuro-caseboard/.ci-venv' \
  --exclude='*/__pycache__' \
  --exclude='neuro-caseboard/.pytest_cache' \
  --exclude='neuro-caseboard/*.egg-info' \
  --exclude='neuro-caseboard/dist' \
  --exclude='neuro-caseboard/build' \
  -cf '$DEST/code/neuro-caseboard-repo.tar' '$(basename "$REPO")'"

# ---- 2. caseprep: tree-only archive of the pinned sha (offline fallback) ------------------
# setup-mac.sh prefers installing caseprep from GitHub at this exact sha; if the Mac is
# offline, it falls back to this archive. `git archive` ships only tracked files at the
# sha — none of caseprep's 27G image_bank data, which neuro-caseboard never imports.
if [ -d "$CASEPREP_DIR/.git" ]; then
  say "[2/5] caseprep -> code/caseprep-src.tar.gz  (git archive @ ${CASEPREP_REF:0:12}, offline fallback)"
  run "git -C '$CASEPREP_DIR' archive --format=tar.gz --prefix=caseprep-src/ '$CASEPREP_REF' -o '$DEST/code/caseprep-src.tar.gz'"
else
  warn "[2/5] skipping caseprep archive — Mac will install it from GitHub @ ${CASEPREP_REF:0:12}"
fi

# ---- 3,4,5. data layers: plain tar (assets are already-compressed images -> no gzip) -----
say "[3/5] textbook index  -> data/textbook-index.tar   (extracts to ~/neuro-textbook-rag/index)"
run "tar -C '$TEXTBOOK_HOME' -cf '$DEST/data/textbook-index.tar' index"

say "[4/5] figure assets   -> data/textbook-assets.tar   (~15G, ~20k files; one stream beats per-file USB copy)"
run "tar -C '$TEXTBOOK_HOME' -cf '$DEST/data/textbook-assets.tar' assets"

if [ -d "$CARDS_DIR" ]; then
  say "[5/5] board-review cards -> data/abns-cards-lancedb.tar (extracts to ~/projects/$(basename "$CARDS_DIR"))"
  run "tar -C '$(dirname "$CARDS_DIR")' -cf '$DEST/data/abns-cards-lancedb.tar' '$(basename "$CARDS_DIR")'"
fi

# ---- fetch the self-contained uv runtime for Apple Silicon -------------------------------
# This is what makes the Mac install need ZERO pre-setup: uv carries its own Python and
# installs all deps. We grab the macOS arm64 binary now (we have network here); if it fails,
# the Mac side falls back to a system-Python path.
say "Fetching the macOS (Apple Silicon) uv runtime into the bundle"
UV_URL="https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz"
if [ "$DRY_RUN" = "1" ]; then
  echo "  (dry-run) download + extract $UV_URL -> $DEST/bin/uv"
else
  mkdir -p "$DEST/bin"
  if command -v curl >/dev/null 2>&1; then DL=(curl -fsSL "$UV_URL" -o "$DEST/bin/uv.tgz");
  else DL=(wget -qO "$DEST/bin/uv.tgz" "$UV_URL"); fi
  if "${DL[@]}"; then
    tar -C "$DEST/bin" -xzf "$DEST/bin/uv.tgz"
    mv "$DEST/bin/uv-aarch64-apple-darwin/uv"  "$DEST/bin/uv"
    mv "$DEST/bin/uv-aarch64-apple-darwin/uvx" "$DEST/bin/uvx" 2>/dev/null || true
    rm -rf "$DEST/bin/uv-aarch64-apple-darwin" "$DEST/bin/uv.tgz"
    chmod +x "$DEST/bin/uv" "$DEST/bin/uvx" 2>/dev/null || true
    printf '  uv staged (%s, macOS arm64 binary)\n' "$(du -h "$DEST/bin/uv" | cut -f1)"
  else
    warn "could not download uv — Mac install will fall back to system Python (brew install python@3.12)"
  fi
fi

# ---- bootstrap files + provenance --------------------------------------------------------
say "Copying the double-click installer, scripts, and quick-start into the bundle"
run "cp '$SELF/setup-mac.sh' '$SELF/Install Caseboard.command' '$SELF/.env.example' '$SELF/README-TRANSFER.md' '$SELF/QUICKSTART.txt' '$DEST/'"
run "chmod +x '$DEST/setup-mac.sh' '$DEST/Install Caseboard.command'"

if [ "$DRY_RUN" != "1" ]; then
  {
    echo "neuro-caseboard transfer bundle"
    echo "built:        $(date -u '+%Y-%m-%dT%H:%M:%SZ') on $(hostname)"
    echo "repo sha:     $repo_sha$dirty"
    echo "caseprep ref: $CASEPREP_REF"
    echo "cards bank:   $([ -d "$CARDS_DIR" ] && echo included || echo 'NOT included')"
  } > "$DEST/bundle-info.txt"

  # SHA256 manifest so a corrupt USB copy is caught before you rebuild on the Mac.
  # (Skip with SKIP_CHECKSUM=1 — hashing 16G takes a few minutes.)
  if [ "${SKIP_CHECKSUM:-0}" != "1" ]; then
    say "Writing SHA256SUMS (integrity check for the USB copy; SKIP_CHECKSUM=1 to skip)"
    ( cd "$DEST" && find code data -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
  fi
fi

say "Bundle staged at: $DEST"
[ "$DRY_RUN" = "1" ] && { echo "  (dry-run: no large files written)"; exit 0; }
du -sh "$DEST" 2>/dev/null | awk '{print "  total bundle size: "$1}'
cat <<EOF

Next (all the Mac user does):
  1. Eject the drive, plug it into the MacBook Air.
  2. Open the drive's "$(basename "$DEST")" folder and double-click:  Install Caseboard.command
     (if macOS blocks it: right-click -> Open -> Open)
  3. When it says INSTALLED, double-click the "Caseboard" shortcut on the Desktop.
  See QUICKSTART.txt in the bundle for the same steps on paper.
EOF
