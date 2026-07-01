#!/usr/bin/env bash
# Remove debug preprocessor artifacts and pycparser caches.
# Generated *.c files are committed; use --all to delete them too.
set -e

LV_BINDINGS_DIR=$(cd "$(dirname "$0")" && pwd)
GENERATED="$LV_BINDINGS_DIR/generated"

rm -f "$GENERATED"/*.pp "$GENERATED"/*.json
rm -f "$LV_BINDINGS_DIR/lextab.py" "$LV_BINDINGS_DIR/yacctab.py"

if [[ "${1:-}" == "--all" ]]; then
    rm -f "$GENERATED"/lvmp.c "$GENERATED"/lvcp.c "$GENERATED"/lvpy.c "$GENERATED"/lvcp_module_globals.h
    echo "Removed committed generated/*.c (regenerate before building)."
else
    echo "Cleaned debug artifacts in generated/ and pycparser table caches."
fi

echo "Regenerate before building:"
echo "  $LV_BINDINGS_DIR/regenerate_lvmp.sh"
echo "  $LV_BINDINGS_DIR/regenerate_lvcp.sh"
echo "  $LV_BINDINGS_DIR/regenerate_lvpy.sh"
