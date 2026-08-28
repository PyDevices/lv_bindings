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
    function_exports = {}
    for function in data.get("functions", ()):
        available = function.get("available_on", ())
        if not set(available) <= set(TARGETS):
            errors.append("function %s has an unknown target" % function.get("c_name"))
        if function.get("visibility") == "public" and not available:
            errors.append("public function %s has no targets" % function.get("c_name"))
        if function.get("visibility") == "public":
            key = (
                function.get("role"),
                function.get("receiver"),
                function.get("python_name"),
            )
            if key in function_exports:
                errors.append(
                    "duplicate function export %s (%s and %s)"
                    % (
                        function.get("python_name"),
                        function_exports[key],
                        function.get("c_name"),
                    )
                )
            else:
                function_exports[key] = function.get("c_name")
    names = {}
    for function in data.get("functions", ()):
        if function.get("visibility") != "public" or function.get("role") != "module":
            continue
        name = function.get("python_name")
        if name in names:
            errors.append(
                "duplicate module export %s (function and %s)" % (name, names[name])
            )
        else:
            names[name] = "function"
    type_names = {
        item.get("python_name")
        for section in ("structs", "enums")
        for item in data.get(section, ())
        if item.get("visibility") == "public"
    }
    for section in ("objects", "structs", "enums", "typedefs", "variables", "constants"):
        for item in data.get(section, ()):
            if item.get("visibility") != "public":
                continue
            name = item.get("python_name") or item.get("name")
            if (
                section == "typedefs"
                and name in type_names
                and item.get("type", {}).get("kind") in {"struct", "union", "enum"}
            ):
                continue
            if name in names:
                errors.append(
                    "duplicate module export %s (%s and %s)"
                    % (name, names[name], section)
                )
            else:
                names[name] = section
            members = item.get("members")
            if isinstance(members, list):
                member_names = [member.get("name") for member in members]
                if len(member_names) != len(set(member_names)):
                    errors.append("duplicate enum members: %s" % name)
            methods = item.get("methods") if section == "objects" else None
            if isinstance(methods, list) and len(methods) != len(set(methods)):
                errors.append("duplicate object methods: %s" % name)
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
