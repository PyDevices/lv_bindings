#!/usr/bin/env bash
# Generate LVGL binding artifacts. This command never commits, tags, pushes, or
# dispatches a release; release mutation lives in scripts/publish_release_tag.sh
# and the explicitly dispatched release workflow.

set -euo pipefail

LV_BINDINGS_DIR=$(cd "$(dirname "$0")" && pwd)
if [[ -x "$LV_BINDINGS_DIR/.venv/bin/python3" ]]; then
    PYTHON="$LV_BINDINGS_DIR/.venv/bin/python3"
else
    PYTHON=python3
fi

TARGET=all
CHECK=0
HASH=0
PYI_ONLY=0
NAMING_STYLE=legacy

usage() {
    cat <<'EOF'
Usage: ./regenerate_all.sh [OPTIONS]

Generate binding artifacts without changing git history or release state.

  --target TARGET  Generate all, micropython, circuitpython, or cpython
  --pyi-only       Regenerate only generated/lvgl.pyi; preserve every C/IR file
  --check          Generate in a temporary directory and compare (read-only)
  --hash           Print the generated artifact manifest
  --pythonic       Use the alternate pythonic naming profile

Release tags are created separately with scripts/publish_release_tag.sh.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target) TARGET=$2; shift 2 ;;
        --pyi-only) PYI_ONLY=1; shift ;;
        --check) CHECK=1; shift ;;
        --hash) HASH=1; shift ;;
        --pythonic) NAMING_STYLE=pythonic; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
done

case "$TARGET" in
    all|micropython|circuitpython|cpython) ;;
    *) echo "Error: invalid target: $TARGET" >&2; exit 1 ;;
esac

if [[ "$PYI_ONLY" -eq 1 && "$TARGET" != all ]]; then
    echo "Error: --pyi-only cannot be combined with --target" >&2
    exit 1
fi

ARGS=(--target "$TARGET" --naming-style "$NAMING_STYLE")
[[ "$PYI_ONLY" -eq 1 ]] && ARGS+=(--pyi-only)
[[ "$CHECK" -eq 1 ]] && ARGS+=(--check)
[[ "$HASH" -eq 1 ]] && ARGS+=(--hash)

cd "$LV_BINDINGS_DIR"
PYTHONPATH="$LV_BINDINGS_DIR" "$PYTHON" -m binding.generate "${ARGS[@]}"
