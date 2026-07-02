#!/usr/bin/env bash
# Generate MicroPython bindings and all generated/lvgl_micropython.* artifacts.
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
LVGL_MP_C="$GENERATED/lvgl_micropython.c"

NAMING_ARGS=()
if [[ "${LV_NAMING_STYLE:-}" == pythonic ]]; then
    NAMING_ARGS=(--naming-style pythonic)
fi

PP_FILE=$("$LV_BINDINGS_DIR/scripts/preprocess_lvgl.sh")

echo "Generating $LVGL_MP_C"
"$PYTHON" "$LV_BINDINGS_DIR/binding/gen_binding.py" \
    --target micropython \
    -M lvgl -MP lv \
    "${NAMING_ARGS[@]}" \
    --ir "$GENERATED/lvgl.json" \
    -E "$PP_FILE" \
    "$LVGL_H" >"$LVGL_MP_C"

echo "Generating $GENERATED/lvgl.pyi"
(
    cd "$LV_BINDINGS_DIR"
    "$PYTHON" -m binding.emit_pyi \
        --generated-dir "$GENERATED" \
        "${NAMING_ARGS[@]}"
)

echo "Done: $LVGL_MP_C"
