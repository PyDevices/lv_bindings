#!/usr/bin/env bash
# Exercise the complete local release gate without committing, tagging,
# pushing, dispatching another repository, or publishing a package.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
LV_BINDINGS_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
if [[ -x "$LV_BINDINGS_DIR/.venv/bin/python" ]]; then
    PYTHON="$LV_BINDINGS_DIR/.venv/bin/python"
else
    PYTHON=python3
fi

cd "$LV_BINDINGS_DIR"

echo "==> Generator unit tests"
PYTHONPATH=. "$PYTHON" -m pytest -q -s tests

echo "==> Generate and compare every artifact"
./regenerate_all.sh --check --hash

echo "==> Binding contract checks"
./scripts/verify_bindings.sh

echo "==> Expected release version"
VERSION=$(./scripts/next_release_version.sh)
case "$VERSION" in
    9.5.*) ;;
    *) echo "Error: expected a 9.5.N version, got $VERSION" >&2; exit 1 ;;
esac
echo "Release dry run passed; expected version: $VERSION"
echo "No commits, tags, pushes, workflow dispatches, or publications were made."
