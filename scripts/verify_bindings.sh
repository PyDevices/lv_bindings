#!/usr/bin/env bash
# Regression checks for unified LVGL binding generation.
set -e

LV_BINDINGS_DIR=$(cd "$(dirname "$0")/.." && pwd)
export LV_BINDINGS_DIR
if [[ -x "$LV_BINDINGS_DIR/.venv/bin/python3" ]]; then
    PYTHON="$LV_BINDINGS_DIR/.venv/bin/python3"
else
    PYTHON=python3
fi
GENERATED="$LV_BINDINGS_DIR/generated"
BASELINE="$GENERATED/baseline"
LVCP_C="$GENERATED/lvgl_circuitpython.c"
LVPY_C="$GENERATED/lvgl_python.c"
LVMP_C="$GENERATED/lvgl_micropython.c"
LVIR_JSON="$GENERATED/lvgl.json"

echo "==> Regenerate all binding targets"
"$LV_BINDINGS_DIR/regenerate_lvmp.sh"
"$LV_BINDINGS_DIR/regenerate_lvcp.sh"
"$LV_BINDINGS_DIR/regenerate_lvpy.sh"
echo

if [ -f "$BASELINE/lvmp.c" ] || [ -f "$BASELINE/lvgl_micropython.c" ]; then
    echo "==> MP byte regression vs baseline (C body, excluding header metadata)"
    if [ -f "$BASELINE/lvgl_micropython.c" ]; then
        BASELINE_MP="$BASELINE/lvgl_micropython.c"
    else
        BASELINE_MP="$BASELINE/lvmp.c"
    fi
    diff -q <(tail -n +14 "$BASELINE_MP") <(tail -n +14 "$LVMP_C")
    if [ -f "$BASELINE/lvgl.pp" ]; then
        diff -q "$BASELINE/lvgl.pp" "$GENERATED/lvgl.pp"
    elif [ -f "$BASELINE/bindings.pp" ]; then
        diff -q "$BASELINE/bindings.pp" "$GENERATED/lvgl.pp"
    elif [ -f "$BASELINE/lvmp.c.pp" ]; then
        diff -q "$BASELINE/lvmp.c.pp" "$GENERATED/lvgl.pp"
    fi
    echo "OK: lvgl_micropython.c body matches baseline"
    echo
fi

echo "==> Validate shared IR (lvgl.json)"
"$PYTHON" "$LV_BINDINGS_DIR/binding/verify_ir.py" "$GENERATED"
echo

echo "==> Validate public namespace parity (MP reference)"
"$PYTHON" "$LV_BINDINGS_DIR/binding/verify_namespace.py" "$GENERATED"
echo

if [ ! -f "$GENERATED/lvgl.pyi" ]; then
    echo "FAIL: missing generated/lvgl.pyi" >&2
    exit 1
fi
echo "OK: generated/lvgl.pyi present"
echo

echo "==> Validate generated/lvgl_circuitpython.c"
"$PYTHON" - "$LVCP_C" "$LVIR_JSON" <<'PY'
import json
import sys
from pathlib import Path

lvcp_path = Path(sys.argv[1])
meta_path = Path(sys.argv[2])

text = lvcp_path.read_text()
lines = text.splitlines()
line_count = len(lines)

errors = []

if line_count < 45000 or line_count > 52000:
    errors.append(f"lvgl_circuitpython.c line count {line_count} outside expected 45000–52000")

if "Target: circuitpython" not in text:
    errors.append("missing Target: circuitpython banner")

if "MP_REGISTER_MODULE(" in text:
    errors.append("lvgl_circuitpython.c must not call MP_REGISTER_MODULE (spike module registers lvgl)")

if "lvgl_module" not in text and "LVCP_MODULE_GLOBALS" not in text:
    errors.append("missing lvgl_module export or LVCP_MODULE_GLOBALS merge macro")

if "lvgl_module_entries" not in text:
    errors.append("missing lvgl_module_entries[] table")

if "CircuitPython phase-2 enum type objects" not in text:
    errors.append("missing phase-2 enum emission")

if "Struct " not in text or "mp_lv_" not in text:
    errors.append("missing struct/object emission markers")

meta = json.loads(meta_path.read_text())

def check_count(label, got, expect, slack=5):
    if abs(got - expect) > slack:
        errors.append(f"{label}: got {got}, expected ~{expect} (±{slack})")

check_count("structs", len(meta.get("structs", [])), 123)
check_count("functions", len(meta.get("functions", {})), 304)
check_count("objects", len(meta.get("objects", {})), 40)
check_count("int_constants", len(meta.get("int_constants", [])), 28, slack=2)
check_count("blobs", len(meta.get("blobs", [])), 70, slack=2)

if errors:
    print("FAIL:")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)

print(f"OK: lvgl_circuitpython.c ({line_count} lines)")
print(f"    metadata: {len(meta.get('structs', []))} structs, "
      f"{len(meta.get('functions', {}))} functions, "
      f"{len(meta.get('objects', {}))} objects, "
      f"{len(meta.get('int_constants', []))} int_constants, "
      f"{len(meta.get('blobs', []))} blobs")
PY

echo
echo "==> Validate CPython runtime export policy vs IR"
"$PYTHON" - "$LVPY_C" "$LVIR_JSON" <<'PY'
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ["LV_BINDINGS_DIR"])
from binding.runtime_exports import RUNTIME_SKIP_MODULE_FUNCS

lvpy_path = Path(sys.argv[1])
ir_meta = json.loads(Path(sys.argv[2]).read_text())

if "Target: cpython" not in lvpy_path.read_text():
    print("FAIL: missing Target: cpython banner in lvgl_python.c")
    sys.exit(1)

ir_funcs = len(ir_meta.get("functions", {}))
skip = len(RUNTIME_SKIP_MODULE_FUNCS.get("cpython", ()))
print(
    "OK: lvgl_python.c present; IR has %d module functions (%d omitted at CPython runtime)"
    % (ir_funcs, skip)
)
PY

echo
echo "All binding regression checks passed."
