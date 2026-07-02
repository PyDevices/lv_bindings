#!/usr/bin/env bash
# Generate CircuitPython bindings and all generated/lvgl_circuitpython.* artifacts.
# Naming: LV_NAMING_STYLE=pythonic for PEP 8-style exports (default: legacy).
set -e

LV_BINDINGS_DIR=$(cd "$(dirname "$0")" && pwd)
if [[ -x "$LV_BINDINGS_DIR/.venv/bin/python3" ]]; then
    PYTHON="$LV_BINDINGS_DIR/.venv/bin/python3"
else
    PYTHON=python3
fi
GENERATED="$LV_BINDINGS_DIR/generated"
LVGL_H="lvgl/lvgl.h"
LVGL_CP_C="$GENERATED/lvgl_circuitpython.c"
LVGL_CP_H="$GENERATED/lvgl_circuitpython.h"

NAMING_ARGS=()
if [[ "${LV_NAMING_STYLE:-}" == pythonic ]]; then
    NAMING_ARGS=(--naming-style pythonic)
fi

PP_FILE=$("$LV_BINDINGS_DIR/scripts/preprocess_lvgl.sh")

echo "Writing $GENERATED/lvgl.json"
"$PYTHON" "$LV_BINDINGS_DIR/binding/gen_binding.py" \
    --target micropython \
    --mode ir \
    -M lvgl -MP lv \
    --ir "$GENERATED/lvgl.json" \
    "${NAMING_ARGS[@]}" \
    -E "$PP_FILE" \
    "$LVGL_H" >/dev/null

echo "Generating $LVGL_CP_C"
"$PYTHON" "$LV_BINDINGS_DIR/binding/gen_binding.py" \
    --target circuitpython \
    -M lvgl -MP lv \
    "${NAMING_ARGS[@]}" \
    --ir "$GENERATED/lvgl.json" \
    -E "$PP_FILE" \
    "$LVGL_H" >"$LVGL_CP_C"

"$PYTHON" - "$LVGL_CP_C" "$LVGL_CP_H" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
start = src.find("#ifndef LVCP_MODULE_GLOBALS_H")
end_marker = "#endif /* LVCP_MODULE_GLOBALS_H */"
end = src.find(end_marker)
if start < 0 or end < 0:
    raise SystemExit("LVCP_MODULE_GLOBALS block not found in lvgl_circuitpython.c")
end += len(end_marker)
Path(sys.argv[2]).write_text(src[start:end] + "\n")
PY

echo "Generating $GENERATED/lvgl.pyi"
(
    cd "$LV_BINDINGS_DIR"
    "$PYTHON" -m binding.emit_pyi \
        --generated-dir "$GENERATED" \
        "${NAMING_ARGS[@]}"
)

echo "Done: $LVGL_CP_C"
