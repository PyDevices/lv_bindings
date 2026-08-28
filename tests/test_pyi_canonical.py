import ast
import json
from io import StringIO
from pathlib import Path

import pytest

from binding.api_model import api_hash_for_dict
from binding.emit_pyi_canonical import CanonicalPyiEmitter, load_canonical_api

TARGETS = ["micropython", "circuitpython", "cpython"]


def _view(python_type, category="scalar", conversion="integer"):
    return {
        "python_type": python_type,
        "category": category,
        "conversion": conversion,
    }


def _api_data():
    return {
        "schema_version": 3,
        "module_prefix": "lv",
        "functions": [
            {
                "c_name": "lv_widget_create",
                "python_name": "create",
                "role": "constructor",
                "receiver": "widget",
                "parameters": [
                    {
                        "name": "parent",
                        "type": {"kind": "pointer"},
                        "view": _view("obj", "object_pointer", "object_handle"),
                    }
                ],
                "return_view": _view("widget", "object_pointer", "object_handle"),
                "available_on": TARGETS,
                "visibility": "public",
            },
            {
                "c_name": "lv_widget_set_value",
                "python_name": "set_value",
                "role": "object_method",
                "receiver": "widget",
                "parameters": [
                    {
                        "name": "widget",
                        "type": {"kind": "pointer"},
                        "view": _view("obj", "object_pointer", "object_handle"),
                    },
                    {
                        "name": "value",
                        "type": {"kind": "primitive", "name": "int"},
                        "view": _view("int"),
                    },
                ],
                "return_view": _view("None", "void", "none"),
                "available_on": TARGETS,
                "visibility": "public",
                "static": False,
            },
            {
                "c_name": "lv_target_only",
                "python_name": "target_only",
                "role": "module",
                "parameters": [],
                "return_view": _view("None", "void", "none"),
                "available_on": ["micropython"],
                "visibility": "public",
            },
        ],
        "objects": [
            {
                "python_name": "obj",
                "constructor": "lv_obj_create",
                "methods": [],
                "parent": None,
                "available_on": TARGETS,
                "visibility": "public",
            },
            {
                "python_name": "widget",
                "constructor": "lv_widget_create",
                "methods": ["set_value"],
                "parent": "obj",
                "available_on": TARGETS,
                "visibility": "public",
            },
        ],
        "structs": [],
        "enums": [
            {
                "python_name": "widget_mode_t",
                "module_name": None,
                "owners": [{"object": "widget", "name": "MODE"}],
                "members": [{"name": "NORMAL", "value": "0"}],
                "member_type": "int",
                "available_on": TARGETS,
                "visibility": "public",
            }
        ],
        "typedefs": [],
        "variables": [],
        "constants": [],
    }


def test_canonical_emitter_uses_views_and_does_not_duplicate_nested_enums():
    output = StringIO()
    CanonicalPyiEmitter(
        _api_data(), target="all", lvgl_version="9.5"
    ).emit(output)
    source = output.getvalue()
    tree = ast.parse(source)

    widget = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "widget")
    names = [
        child.name
        for child in widget.body
        if isinstance(child, (ast.ClassDef, ast.FunctionDef))
    ]
    assert names.count("MODE") == 1
    assert not any(
        isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
        and child.target.id == "MODE"
        for child in widget.body
    )
    setter = next(child for child in widget.body if isinstance(child, ast.FunctionDef) and child.name == "set_value")
    assert [arg.arg for arg in setter.args.args] == ["self", "value"]
    constructor = next(
        child for child in widget.body if isinstance(child, ast.FunctionDef) and child.name == "__init__"
    )
    assert [arg.arg for arg in constructor.args.args] == ["self", "parent"]
    assert ast.unparse(constructor.args.args[1].annotation) == "obj | None"
    assert "target_only" not in {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }


def test_canonical_emitter_can_emit_target_specific_exceptions():
    output = StringIO()
    CanonicalPyiEmitter(
        _api_data(), target="micropython", lvgl_version="9.5"
    ).emit(output)
    tree = ast.parse(output.getvalue())
    assert "target_only" in {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }


def test_canonical_emitter_omits_struct_methods_shadowed_by_fields():
    data = _api_data()
    data["structs"] = [
        {
            "c_name": "lv_sample_t",
            "python_name": "sample_t",
            "kind": "struct",
            "fields": [
                {"name": "size", "type": {"kind": "primitive", "name": "int"}, "view": _view("int")}
            ],
            "available_on": TARGETS,
            "visibility": "public",
        }
    ]
    data["functions"].append(
        {
            "c_name": "lv_sample_size",
            "python_name": "size",
            "role": "struct_method",
            "receiver": "sample_t",
            "parameters": [],
            "return_view": _view("int"),
            "available_on": TARGETS,
            "visibility": "public",
        }
    )

    output = StringIO()
    CanonicalPyiEmitter(data, lvgl_version="9.5").emit(output)
    sample = next(
        node for node in ast.parse(output.getvalue()).body
        if isinstance(node, ast.ClassDef) and node.name == "sample_t"
    )
    assert [child.name for child in sample.body if isinstance(child, ast.FunctionDef)] == []
    assert [child.target.id for child in sample.body if isinstance(child, ast.AnnAssign)] == ["size"]


def test_load_canonical_api_rejects_invalid_content(tmp_path: Path):
    data = _api_data()
    data["api_hash"] = api_hash_for_dict(data)
    path = tmp_path / "api.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_canonical_api(path)["schema_version"] == 3

    data["api_hash"] = "wrong"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="api_hash does not match"):
        load_canonical_api(path)
