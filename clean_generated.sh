#!/usr/bin/env bash
# Remove generated bindings and generator caches. Safe to run anytime; regenerate before building.
set -e

LV_BINDINGS_DIR=$(cd "$(dirname "$0")" && pwd)

rm -rf "$LV_BINDINGS_DIR/generated"/*
rm -f "$LV_BINDINGS_DIR/lextab.py" "$LV_BINDINGS_DIR/yacctab.py"

echo "Cleaned lv_bindings/generated/ and pycparser table caches."
echo "Regenerate before building:"
echo "  $LV_BINDINGS_DIR/regenerate_lvmp.sh"
echo "  $LV_BINDINGS_DIR/regenerate_lvcp.sh   # CircuitPython"
