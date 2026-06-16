#!/usr/bin/env bash
# setup-mac.sh — rebuild neuro-caseboard on a Mac with ZERO pre-setup.
#
# You normally never run this directly — you double-click "Install Caseboard.command",
# which calls this. It is driven by a self-contained `uv` binary shipped in the bundle
# (bin/uv), so the Mac needs no Homebrew, no system Python, and no git: uv brings its own
# Python and installs everything. Re-runnable; pass FORCE=1 to overwrite an existing install.
set -euo pipefail

BUNDLE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_REPO="${TARGET_REPO:-$HOME/projects/neuro-caseboard}"
TEXTBOOK_HOME="${TEXTBOOK_HOME:-$HOME/neuro-textbook-rag}"
PROJECTS="${PROJECTS:-$HOME/projects}"
PY_VERSION="${PY_VERSION:-3.12}"
# 16GB Air -> full set incl. the visual/figure lane (BiomedCLIP via open-clip-torch).
EXTRAS="${EXTRAS:-web,llm,vertex,models,dev}"
CASEPREP_REF="${CASEPREP_REF:-8b1d8fd0488c16ff68721c6dc29041862517b392}"
CASEPREP_URL="git+https://github.com/michaelandrewlongo-rgb/caseprep.git@${CASEPREP_REF}"
FORCE="${FORCE:-0}"
VENV="$TARGET_REPO/.venv"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m[!] %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 1. preflight ------------------------------------------------------------------------
say "[1/6] Checking the bundle"
[ "$(uname -s)" = "Darwin" ] || warn "this targets macOS; you are on $(uname -s) (continuing anyway)"
for f in code/neuro-caseboard-repo.tar data/textbook-index.tar data/textbook-assets.tar; do
  [ -f "$BUNDLE/$f" ] || die "bundle is incomplete: $f is missing. Re-copy the whole folder from the drive."
done
if [ -f "$BUNDLE/SHA256SUMS" ] && [ "${SKIP_CHECKSUM:-0}" != "1" ]; then
  say "Verifying the copy isn't corrupt (this is quick)…"
  ( cd "$BUNDLE" && shasum -a 256 -c SHA256SUMS ) >/dev/null \
    && say "Copy is intact." || die "The copy is damaged. Re-copy the whole folder from the drive and try again."
fi

# ---- pick an installer: bundled uv (preferred) or a system python fallback ----------------
UV=""
if [ -x "$BUNDLE/bin/uv" ]; then UV="$BUNDLE/bin/uv"
elif command -v uv >/dev/null 2>&1; then UV="$(command -v uv)"; fi

# ---- 2. restore the repo -----------------------------------------------------------------
say "[2/6] Installing the program files -> $TARGET_REPO"
if [ -e "$TARGET_REPO" ] && [ "$FORCE" != "1" ]; then
  warn "$TARGET_REPO already exists — leaving it as-is (FORCE=1 to reinstall from scratch)"
else
  [ "$FORCE" = "1" ] && rm -rf "$TARGET_REPO"
  mkdir -p "$(dirname "$TARGET_REPO")"
  tar -C "$(dirname "$TARGET_REPO")" -xf "$BUNDLE/code/neuro-caseboard-repo.tar"
fi

# ---- 3. extract the data to its default home paths (so no config edits are needed) -------
say "[3/6] Unpacking the textbook data (this is the big part — a few minutes)"
extract() { # <tarball> <dest-parent> <subdir> <label>
  [ -f "$1" ] || { warn "$4: $1 not in bundle — skipping"; return; }
  if [ -d "$2/$3" ] && [ "$FORCE" != "1" ]; then warn "$4 already present — skipping"; return; fi
  mkdir -p "$2"; tar -C "$2" -xf "$1"; printf '   %s ready\n' "$4"
}
extract "$BUNDLE/data/textbook-index.tar"     "$TEXTBOOK_HOME" "index"  "textbook index"
extract "$BUNDLE/data/textbook-assets.tar"    "$TEXTBOOK_HOME" "assets" "figure assets"
extract "$BUNDLE/data/abns-cards-lancedb.tar" "$PROJECTS"      "abns-board-review-lancedb" "board-review cards"

# ---- 4. environment + dependencies -------------------------------------------------------
say "[4/6] Setting up Python and downloading libraries (needs Wi-Fi; the longest step)"
install_caseprep() {
  if [ -f "$BUNDLE/code/caseprep-src.tar.gz" ]; then
    local tmp; tmp="$(mktemp -d)"; tar -C "$tmp" -xzf "$BUNDLE/code/caseprep-src.tar.gz"
    echo "$tmp/caseprep-src"          # local path -> no git needed
  else
    echo "$CASEPREP_URL"
  fi
}
CASEPREP_TARGET="$(install_caseprep)"

if [ -n "$UV" ]; then
  say "   using bundled uv (brings its own Python ${PY_VERSION})"
  [ -d "$VENV" ] && [ "$FORCE" = "1" ] && rm -rf "$VENV"
  [ -d "$VENV" ] || "$UV" venv --python "$PY_VERSION" "$VENV"
  "$UV" pip install --python "$VENV/bin/python" "$CASEPREP_TARGET"
  "$UV" pip install --python "$VENV/bin/python" -e "$TARGET_REPO[$EXTRAS]"
else
  warn "uv not found in bundle — falling back to system Python (needs Python >=3.10)"
  PY=""; for c in python3.12 python3.11 python3.10 python3; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
  [ -n "$PY" ] || die "No Python found. Easiest fix: install Homebrew Python (brew install python@3.12) and re-run."
  [ -d "$VENV" ] && [ "$FORCE" = "1" ] && rm -rf "$VENV"
  [ -d "$VENV" ] || "$PY" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
  "$VENV/bin/python" -m pip install "$CASEPREP_TARGET"
  "$VENV/bin/python" -m pip install -e "$TARGET_REPO[$EXTRAS]"
fi

# ---- 5. .env + a double-click launcher on the Desktop ------------------------------------
say "[5/6] Creating your settings file and a Desktop shortcut"
[ -f "$TARGET_REPO/.env" ] || cp "$BUNDLE/.env.example" "$TARGET_REPO/.env"

LAUNCHER="$HOME/Desktop/Caseboard.command"
cat > "$LAUNCHER" <<EOF
#!/bin/bash
# Double-click to start Neuro-Caseboard. It opens in your web browser.
# Keep this window open while you use it; close the window to stop.
cd "$TARGET_REPO" || exit 1
echo "Starting Caseboard… your browser will open in a few seconds."
echo "(First start is slow — it loads the AI models. Leave this window open.)"
exec "$VENV/bin/python" -m streamlit run app/streamlit_app.py --server.headless=false
EOF
chmod +x "$LAUNCHER" 2>/dev/null || true

# ---- 6. verify ---------------------------------------------------------------------------
say "[6/6] Checking the install"
"$VENV/bin/python" - <<'PY'
import importlib
for m in ("neuro_caseboard.cli","neuro_caseboard.pipeline","neuro_core.query","neuro_core.index","neuro_caseboard.retrieve"):
    importlib.import_module(m)
print("   program files OK")
PY
"$VENV/bin/caseboard" --help >/dev/null && echo "   commands OK"
idx="$TEXTBOOK_HOME/index"
[ -d "$idx" ] && echo "   data OK ($(find "$idx" -type f | wc -l | tr -d ' ') index files, $(find "$TEXTBOOK_HOME/assets" -type f 2>/dev/null | wc -l | tr -d ' ') figures)"

cat <<EOF

============================================================================
  ✅  Neuro-Caseboard is installed.
============================================================================
  • A "Caseboard" shortcut is on your Desktop — double-click it to start.
  • You can unplug the USB drive now; everything was copied to your Mac.

  Optional, only when you want the smartest answers (it works without these):
     open  $TARGET_REPO/.env   and paste in any keys you have
     (ANTHROPIC_API_KEY for the LLM; GOOGLE_CLOUD_PROJECT for Vertex).

  Heads-up: the FIRST question downloads the AI models (~3.5GB) and is slow.
  After that it's much quicker. It runs on the Mac's processor — correct, just
  not as fast as a desktop GPU.
============================================================================
EOF
