"""Validate a generated pyi against the canonical API manifest."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from .api_model import API_SCHEMA_VERSION, TARGETS
from .emit_pyi_canonical import _identifier
from .verify_api import validate_api_data

_ALL_TARGETS = frozenset(TARGETS)
_HELPER_NAMES = frozenset({"Blob", "C_Pointer", "LvReferenceError", "Struct", "_Nesting"})


def _available(item: Mapping[str, Any], target: str) -> bool:
    available = set(item.get("available_on", ()))
    return _ALL_TARGETS <= available if target == "all" else target in available


def _public(item: Mapping[str, Any], target: str) -> bool:
    return item.get("visibility") == "public" and _available(item, target)


def _top_level_nodes(tree: ast.Module) -> dict[str, ast.AST]:
    nodes: dict[str, ast.AST] = {}
    for node in tree.body:
        names = []
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, ast.Assign):
            names.extend(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        for name in names:
            nodes[name] = node
    return nodes


def _class_nodes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def _member_nodes(class_node: ast.ClassDef) -> dict[str, ast.AST]:
    nodes: dict[str, ast.AST] = {}
    for node in class_node.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            nodes[node.name] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nodes[node.target.id] = node
    return nodes


def _expected_top_level(data: Mapping[str, Any], target: str) -> set[str]:
    expected = set(_HELPER_NAMES)
    for section in ("objects", "structs"):
        expected.update(
            _identifier(item["python_name"])
            for item in data.get(section, ())
            if _public(item, target)
        )
    expected.update(
        _identifier(item["module_name"])
        for item in data.get("enums", ())
        if _public(item, target) and item.get("module_name")
    )
    expected.update(
        _identifier(item["python_name"])
        for item in data.get("functions", ())
        if _public(item, target) and item.get("role") == "module"
    )
    expected.update(
        _identifier(item["python_name"])
        for item in data.get("variables", ())
        if _public(item, target) and item.get("c_name") != "_nesting"
    )
    if any(item.get("c_name") == "_nesting" for item in data.get("variables", ())):
        expected.add("_nesting")
    expected.update(
        _identifier(item["python_name"])
        for item in data.get("constants", ())
        if _public(item, target)
    )
    return expected


def _expected_enum_members(enum: Mapping[str, Any]) -> set[str]:
    return {_identifier(member["name"]) for member in enum.get("members", ())}


def _expected_class_members(
    data: Mapping[str, Any], class_name: str, target: str
) -> set[str]:
    expected: set[str] = set()
    struct = next(
        (
            item
            for item in data.get("structs", ())
            if item.get("python_name") == class_name and _public(item, target)
        ),
        None,
    )
    if struct is not None:
        field_names = {
            _identifier(field.get("name") or "field")
            for field in struct.get("fields", ())
        }
        expected.update(field_names)
        expected.update(
            _identifier(function["python_name"])
            for function in data.get("functions", ())
            if function.get("role") == "struct_method"
            and function.get("receiver") == class_name
            and _public(function, target)
            and _identifier(function["python_name"]) not in field_names
        )

    object_ = next(
        (
            item
            for item in data.get("objects", ())
            if item.get("python_name") == class_name and _public(item, target)
        ),
        None,
    )
    if object_ is not None:
        expected.update(
            owner["name"]
            for enum in data.get("enums", ())
            if _public(enum, target)
            for owner in enum.get("owners", ())
            if owner.get("object") == class_name
        )
        if any(
            function.get("role") == "constructor"
            and function.get("receiver") == class_name
            and _public(function, target)
            for function in data.get("functions", ())
        ):
            expected.add("__init__")
        expected.update(
            _identifier(function["python_name"])
            for function in data.get("functions", ())
            if function.get("role") == "object_method"
            and function.get("receiver") == class_name
            and _public(function, target)
        )
    return expected


def validate_pyi_data(
    data: Mapping[str, Any], source: str, *, target: str = "all"
) -> list[str]:
    """Return manifest discrepancies for one generated stub source."""

    errors = []
    if data.get("schema_version") != API_SCHEMA_VERSION:
        return ["unsupported API schema version"]
    if target not in TARGETS + ("all",):
        return ["unsupported stub target: %s" % target]
    api_errors = validate_api_data(data)
    if api_errors:
        return ["invalid API model: %s" % error for error in api_errors]
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return ["stub is not valid Python: %s" % error]

    actual_top = set(_top_level_nodes(tree))
    expected_top = _expected_top_level(data, target)
    for name in sorted(expected_top - actual_top):
        errors.append("missing top-level export: %s" % name)
    for name in sorted(actual_top - expected_top):
        errors.append("unexpected top-level export: %s" % name)

    classes = _class_nodes(tree)
    for item in data.get("enums", ()):
        if not (_public(item, target) and item.get("module_name")):
            continue
        name = _identifier(item["module_name"])
        class_node = classes.get(name)
        if class_node is None:
            continue
        actual_members = set(_member_nodes(class_node))
        expected_members = _expected_enum_members(item)
        for member in sorted(expected_members - actual_members):
            errors.append("missing enum member: %s.%s" % (name, member))
        for member in sorted(actual_members - expected_members):
            errors.append("unexpected enum member: %s.%s" % (name, member))

    for item in data.get("objects", ()):
        if not _public(item, target):
            continue
        name = _identifier(item["python_name"])
        class_node = classes.get(name)
        if class_node is None:
            continue
        actual_members = set(_member_nodes(class_node))
        expected_members = _expected_class_members(data, item["python_name"], target)
        for member in sorted(expected_members - actual_members):
            errors.append("missing member: %s.%s" % (name, member))
        for member in sorted(actual_members - expected_members):
            if not member.startswith("__"):
                errors.append("unexpected member: %s.%s" % (name, member))

    for item in data.get("structs", ()):
        if not _public(item, target):
            continue
        name = _identifier(item["python_name"])
        class_node = classes.get(name)
        if class_node is None:
            continue
        actual_members = set(_member_nodes(class_node))
        expected_members = _expected_class_members(data, item["python_name"], target)
        for member in sorted(expected_members - actual_members):
            errors.append("missing member: %s.%s" % (name, member))
        for member in sorted(actual_members - expected_members):
            if not member.startswith("__"):
                errors.append("unexpected member: %s.%s" % (name, member))

    return errors


def validate_pyi_file(api_path: Path, pyi_path: Path, *, target: str = "all") -> list[str]:
    with api_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return validate_pyi_data(
        data,
        pyi_path.read_text(encoding="utf-8"),
        target=target,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("api", type=Path, help="canonical generated/api.json")
    parser.add_argument("pyi", type=Path, help="generated/lvgl.pyi")
    parser.add_argument(
        "--target",
        choices=list(TARGETS) + ["all"],
        default="all",
        help="stub target represented by the pyi",
    )
    args = parser.parse_args(argv)
    errors = validate_pyi_file(args.api, args.pyi, target=args.target)
    if errors:
        for error in errors:
            print("FAIL: %s" % error, file=sys.stderr)
        return 1
    print("OK: %s matches canonical API manifest" % args.pyi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
