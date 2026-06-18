#!/usr/bin/env bash
# Install this package with whatever pip target/extras you pass. Used by CI and reproducible
# locally. caseprep is vendored in-tree (./vendor/caseprep) and ships inside this package, so there
# is no separate sibling/pinned install step anymore.
#
#   ci/install.sh ".[dev]"          # editable-ish source install with the dev extra
#   ci/install.sh dist/*.whl        # the built wheel (declared deps resolve from PyPI)
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: ci/install.sh <pip-install-target> [more targets...]" >&2
  exit 2
fi

echo ">> python: $(python -V)  ($(command -v python))"
python -m pip install --upgrade pip >/dev/null

echo ">> installing project target(s): $*"
python -m pip install "$@"
