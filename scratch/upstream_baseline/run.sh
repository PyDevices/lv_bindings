#!/usr/bin/env bash
# Reproduce the pinned upstream generator in a temporary workspace.
#
# This is an oracle for the rebuild, not a production regeneration path. It
# deliberately does not copy the upstream generator or its generated output
# into this repository.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
UPSTREAM_URL="https://github.com/lvgl/lv_binding_micropython.git"
UPSTREAM_REF="60dfbd41f99c2757d1fe3bffab246c818afebcc4"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
BASELINE="$ROOT/docs/baseline/lvgl-bindings-api-baseline.json.gz"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cat <<'EOF'
Usage: scratch/upstream_baseline/run.sh

The optional LVGL_BINDINGS_UPSTREAM_REPO environment variable can point to an
existing checkout of lv_binding_micropython. Otherwise the pinned upstream
commit is cloned into a temporary directory. Generated intermediates remain
temporary; the committed compact baseline is verified read-only.
EOF
    exit 0
fi

if [[ ! -x "$PYTHON" ]]; then
    PYTHON=python3
fi
if [[ ! -f "$ROOT/generated/lvgl.pp" ]]; then
    echo "missing $ROOT/generated/lvgl.pp" >&2
    exit 1
fi

WORK=$(mktemp -d /tmp/lvgl-bindings-upstream-baseline.XXXXXX)
cleanup() {
    rm -rf "$WORK"
}
trap cleanup EXIT

if [[ -n "${LVGL_BINDINGS_UPSTREAM_REPO:-}" ]]; then
    UPSTREAM=${LVGL_BINDINGS_UPSTREAM_REPO}
else
    UPSTREAM="$WORK/upstream"
    git clone --quiet --filter=blob:none --no-checkout "$UPSTREAM_URL" "$UPSTREAM"
    git -C "$UPSTREAM" checkout --quiet "$UPSTREAM_REF"
fi

if [[ "$(git -C "$UPSTREAM" rev-parse HEAD)" != "$UPSTREAM_REF" ]]; then
    echo "upstream checkout is not $UPSTREAM_REF" >&2
    exit 1
fi

UPSTREAM_JSON="$WORK/upstream.json"
UPSTREAM_C="$WORK/upstream.c"
"$PYTHON" "$UPSTREAM/gen/gen_mpy.py" \
    -M lvgl -MP lv -MD "$UPSTREAM_JSON" \
    -E "$ROOT/generated/lvgl.pp" "$ROOT/lvgl/lvgl.h" >"$UPSTREAM_C"

"$PYTHON" "$ROOT/tools/verify_upstream_baseline.py" \
    --upstream-metadata "$UPSTREAM_JSON" \
    --upstream-c "$UPSTREAM_C" \
    --baseline "$BASELINE"
