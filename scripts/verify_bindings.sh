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
LVCP_C="$GENERATED/lvgl_circuitpython.c"

echo "==> Verify deterministic generated artifacts"
(
    cd "$LV_BINDINGS_DIR"
    PYTHONPATH="$LV_BINDINGS_DIR" "$PYTHON" -m binding.generate --check
)
echo

echo "==> Validate target-neutral API model (api.json)"
PYTHONPATH="$LV_BINDINGS_DIR" "$PYTHON" -m binding.verify_api "$GENERATED/api.json"
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

echo "==> Validate generated/lvgl.pyi against canonical API manifest"
PYTHONPATH="$LV_BINDINGS_DIR" "$PYTHON" -m binding.verify_pyi \
    "$GENERATED/api.json" "$GENERATED/lvgl.pyi"
echo

echo "==> Static-check generated/lvgl.pyi"
PYTHONPATH="$LV_BINDINGS_DIR" "$PYTHON" -m mypy "$GENERATED/lvgl.pyi"
echo

echo "==> Validate generated/lvgl_circuitpython.c"
"$PYTHON" - "$LVCP_C" "$GENERATED/api.json" <<'PY'
import json
import sys
from pathlib import Path

lvcp_path = Path(sys.argv[1])
api_path = Path(sys.argv[2])

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

api = json.loads(api_path.read_text())
public_functions = sum(
    item.get("visibility") == "public"
    and "circuitpython" in item.get("available_on", ())
    for item in api["functions"]
)
public_structs = sum(
    item.get("visibility") == "public"
    and "circuitpython" in item.get("available_on", ())
    for item in api["structs"]
)

if errors:
    print("FAIL:")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)

print(f"OK: lvgl_circuitpython.c ({line_count} lines)")
print(f"    canonical API: {public_functions} public functions, "
      f"{public_structs} public structs")
PY

echo
echo "All binding regression checks passed."
