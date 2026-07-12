#!/usr/bin/env bash
# Preprocess lvgl/lvgl.h once with MicroPython-canonical flags (no LV_*_BUILD).
# Writes generated/lvgl.pp and prints that path on stdout.
set -e

LV_BINDINGS_DIR=$(cd "$(dirname "$0")/.." && pwd)
GENERATED="$LV_BINDINGS_DIR/generated"
LVGL_H="lvgl/lvgl.h"
FAKE_LIBC="$LV_BINDINGS_DIR/fake_libc_include"

mkdir -p "$GENERATED"

CPP="${CPP:-gcc -E}"
LV_CFLAGS="${LV_CFLAGS:-}"
PP_FILE="$GENERATED/lvgl.pp"

echo "Preprocessing $LVGL_H (MP-canonical flags)" >&2
$CPP $LV_CFLAGS -E -DPYCPARSER \
    -I "$FAKE_LIBC" \
    "$LV_BINDINGS_DIR/$LVGL_H" >"$PP_FILE"

echo "$PP_FILE"
