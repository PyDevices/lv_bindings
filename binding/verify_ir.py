#!/usr/bin/env python3
"""Regression check: lvgl.json shape vs generated/baseline (verify_bindings.sh)."""
from __future__ import print_function

import json
import sys
from pathlib import Path


def _counts(meta):
    enums = meta.get("enums", {})
    return {
        "functions": len(meta.get("functions", {})),
        "objects": len(meta.get("objects", {})),
        "enums": len(enums),
        "enums_with_members": sum(1 for value in enums.values() if value.get("members")),
        "structs": len(meta.get("structs", [])),
        "blobs": len(meta.get("blobs", [])),
        "int_constants": len(meta.get("int_constants", [])),
    }


def compare_ir(ir_path, baseline_path, *, slack=3):
    ir = json.loads(Path(ir_path).read_text())
    baseline = json.loads(Path(baseline_path).read_text())
    ir_counts = _counts(ir)
    base_counts = _counts(baseline)
    errors = []
    for key, got in ir_counts.items():
        expect = base_counts[key]
        if abs(got - expect) > slack:
            errors.append("%s: got %d, expected ~%d (±%d)" % (key, got, expect, slack))
    return errors, ir_counts, base_counts


def main(argv=None):
    argv = argv or sys.argv
    generated = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "generated"
    ir_path = generated / "lvgl.json"
    baseline_path = generated / "baseline" / "lvgl.json"
    if not baseline_path.is_file():
        baseline_path = generated / "baseline" / "bindings.json"
    if not baseline_path.is_file():
        baseline_path = generated / "baseline" / "lv_bindings.json"
    if not baseline_path.is_file():
        baseline_path = generated / "baseline" / "lvmp.c.json"
    if len(argv) > 2:
        baseline_path = Path(argv[2])

    if not ir_path.is_file():
        print("FAIL: missing %s" % ir_path)
        return 1
    if not baseline_path.is_file():
        print("FAIL: missing baseline %s" % baseline_path)
        return 1

    errors, ir_counts, base_counts = compare_ir(ir_path, baseline_path)
    if errors:
        print("FAIL IR parity vs baseline:")
        for err in errors:
            print("  - %s" % err)
        return 1

    print(
        "OK: lvgl.json matches baseline shape "
        "(%d functions, %d objects, %d enums, %d structs)"
        % (
            ir_counts["functions"],
            ir_counts["objects"],
            ir_counts["enums"],
            ir_counts["structs"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
