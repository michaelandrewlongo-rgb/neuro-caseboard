#!/usr/bin/env bash
# Install the project's one external sibling dependency (caseprep, pinned) and then this
# package with whatever pip target/extras you pass. Used by CI and reproducible locally.
#
#   ci/install.sh ".[dev]"          # editable-ish source install with the dev extra
#   ci/install.sh dist/*.whl        # the built wheel (declared deps resolve from PyPI)
#
# Override the caseprep pin with the CASEPREP_REF env var (CI sets it once per workflow).
set -euo pipefail

# Keep this default in sync with .github/workflows/ci.yml's CASEPREP_REF.
CASEPREP_REF="${CASEPREP_REF:-8b1d8fd0488c16ff68721c6dc29041862517b392}"
CASEPREP_URL="git+https://github.com/michaelandrewlongo-rgb/caseprep.git@${CASEPREP_REF}"

if [ "$#" -lt 1 ]; then
  echo "usage: ci/install.sh <pip-install-target> [more targets...]" >&2
  exit 2
fi

echo ">> python: $(python -V)  ($(command -v python))"
python -m pip install --upgrade pip >/dev/null

echo ">> installing caseprep @ ${CASEPREP_REF}"
python -m pip install "caseprep @ ${CASEPREP_URL}"

echo ">> installing project target(s): $*"
python -m pip install "$@"
