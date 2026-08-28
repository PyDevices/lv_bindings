#!/usr/bin/env python3
"""Validate the generated target-neutral API model and its content hash."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .api_model import TARGETS, api_hash_for_dict


def validate_api_data(data):
    errors = []
    if data.get("schema_version") != 1:
        errors.append("unsupported API schema version")
    if not isinstance(data.get("api_hash"), str):
        errors.append("missing api_hash")
    elif data["api_hash"] != api_hash_for_dict(data):
        errors.append("api_hash does not match canonical content")
    if data.get("module_prefix") != "lv":
        errors.append("unexpected module prefix")
    for section in ("functions", "objects", "structs", "enums", "typedefs", "variables"):
        if not isinstance(data.get(section), list):
            errors.append("section %s must be a list" % section)
    for function in data.get("functions", ()):
        available = function.get("available_on", ())
        if not set(available) <= set(TARGETS):
            errors.append("function %s has an unknown target" % function.get("c_name"))
        if function.get("visibility") == "public" and not available:
            errors.append("public function %s has no targets" % function.get("c_name"))
    return errors


def main(argv=None):
    path = Path((argv or sys.argv)[1])
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    errors = validate_api_data(data)
    if errors:
        for error in errors:
            print("FAIL: " + error)
        return 1
    print("OK: %s (%s)" % (path, data["api_hash"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
