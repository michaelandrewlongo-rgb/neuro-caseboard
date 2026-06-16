#!/usr/bin/env bash
# Reproduce the REQUIRED CI pipeline locally in a throwaway virtualenv, so a red CI job can
# be debugged on your machine with one command. Mirrors .github/workflows/ci.yml.
#
#   ci/local-ci.sh                 # full mirror: sanity -> tests -> package smoke
#   USE_LOCAL_CASEPREP=1 ci/local-ci.sh   # install caseprep from ../caseprep (-e) — faster,
#                                          # for iterating; CI uses the pinned git ref.
#
# The venv is created WITHOUT --system-site-packages, so heavy libs you have installed
# globally (torch, sentence-transformers, open-clip) cannot leak in and mask a real gap.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
VENV="${VENV:-$REPO/.local-ci-venv}"
export PYTHONHASHSEED=0
export PIP_DISABLE_PIP_VERSION_CHECK=1

echo "==> [0/3] fresh venv at $VENV"
rm -rf "$VENV"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> [1/3] sanity (syntax + hygiene)"
python -m compileall -q neuro_caseboard neuro_core app tests eval
python -c "import tomllib, pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print('pyproject OK')"

echo "==> [2/3] install + full offline test suite"
if [ "${USE_LOCAL_CASEPREP:-0}" = "1" ] && [ -d "$REPO/../caseprep" ]; then
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -e "$REPO/../caseprep"
  python -m pip install -e ".[dev]"
else
  ./ci/install.sh ".[dev]"
fi
python -m pytest -p no:cacheprovider --durations=10
echo "==> [2b/3] quality-regression gate (eval split, offline/deterministic)"
python eval/quality_gate.py

echo "==> [3/3] package: build + clean wheel install + import + entry point"
python -m pip install --upgrade build twine >/dev/null
rm -rf dist build
python -m build
python -m twine check dist/*
PKGVENV="$REPO/.local-ci-pkgvenv"
rm -rf "$PKGVENV"
python3 -m venv "$PKGVENV"
# shellcheck disable=SC1091
source "$PKGVENV/bin/activate"
if [ "${USE_LOCAL_CASEPREP:-0}" = "1" ] && [ -d "$REPO/../caseprep" ]; then
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -e "$REPO/../caseprep"
  python -m pip install dist/*.whl
else
  ./ci/install.sh dist/*.whl
fi
python -c "import neuro_caseboard.cli, neuro_caseboard.pipeline, neuro_core.query, neuro_core.index, neuro_caseboard.retrieve; print('ALL SURFACES IMPORTED')"
caseboard --help >/dev/null && echo "entry point OK"

echo "==> local CI mirror PASSED"
