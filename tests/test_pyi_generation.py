"""End-to-end regression tests for the typing-only generation path."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from binding.pyi_prototypes import (
    build_enum_typedef_map,
    enrich_function_info,
    enrich_struct_function_info,
    parse_pp_callback_typedefs,
    parse_pp_prototypes,
    parse_pp_struct_fields,
    parse_pp_type_aliases,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_complete_c(tmp_path: Path, source: str) -> Path:
    pp_path = tmp_path / "sample.pp"
    pp_path.write_text(source, encoding="utf-8")
    return pp_path


def test_ast_prototypes_ignore_inline_calls_and_keep_array_names(tmp_path: Path):
    pp_path = _write_complete_c(
        tmp_path,
        """
        typedef unsigned char uint8_t;
        typedef int int32_t;
        typedef unsigned long size_t;
        typedef struct { uint8_t red; uint8_t green; uint8_t blue; } lv_color_t;
        lv_color_t lv_color_make(uint8_t r, uint8_t g, uint8_t b);
        static inline lv_color_t lv_color_hex(uint8_t c) {
            return lv_color_make(c, c, c);
        }
        void *lv_memset(void *dst, uint8_t v, size_t len);
        static inline void lv_zero(void *dst, size_t len) {
            lv_memset(dst, 0, len);
        }
        void lv_chart_set_series_values2(
            int32_t x_values[], int32_t y_values[], int32_t count);
        void lv_format(const char *fmt, ...);
        """,
    )

    prototypes = parse_pp_prototypes(pp_path)

    assert [arg["name"] for arg in prototypes["lv_color_make"]["args"]] == [
        "r",
        "g",
        "b",
    ]
    assert [arg["name"] for arg in prototypes["lv_memset"]["args"]] == [
        "dst",
        "v",
        "len",
    ]
    chart_args = prototypes["lv_chart_set_series_values2"]["args"]
    assert [arg["name"] for arg in chart_args] == ["x_values", "y_values", "count"]
    assert [arg["type"] for arg in chart_args] == ["Any", "Any", "int"]
    assert prototypes["lv_format"]["args"][-1] == {"type": "...", "name": "args"}


def test_generic_function_pointer_typedef_is_a_callable(tmp_path: Path):
    pp_path = _write_complete_c(
        tmp_path,
        """
        typedef int int32_t;
        typedef int32_t (*lv_rb_compare_t)(const void *left, const void *right);
        """,
    )

    callbacks = parse_pp_callback_typedefs(pp_path)

    assert "rb_compare_t" in callbacks
    assert callbacks["rb_compare_t"]["function"] == {
        "args": [
            {"type": "void*", "name": "left"},
            {"type": "void*", "name": "right"},
        ],
        "return_type": "int",
    }


def test_scalar_aliases_and_direct_struct_fields_are_preserved(tmp_path: Path):
    pp_path = _write_complete_c(
        tmp_path,
        """
        typedef unsigned char uint8_t;
        typedef int int32_t;
        typedef float lv_value_precise_t;
        typedef uint8_t lv_style_prop_t;
        typedef void *lv_mem_pool_t;
        typedef enum { LV_PRIVATE_A, LV_PRIVATE_B } lv_private_mode_t;
        typedef struct {
            int32_t stops[2];
            uint8_t stops_count;
            union { int32_t linear; int32_t radial; } params;
            void *state;
        } lv_grad_dsc_t;
        """,
    )

    aliases = parse_pp_type_aliases(pp_path)
    assert aliases["value_precise_t"] == "float"
    assert aliases["style_prop_t"] == "int"
    assert aliases["mem_pool_t"] == "Any"
    assert aliases["private_mode_t"] == "int"

    assert parse_pp_struct_fields(pp_path)["grad_dsc_t"] == [
        {"name": "stops", "type": "Any"},
        {"name": "stops_count", "type": "int"},
        {"name": "state", "type": "void*"},
    ]


def test_widget_enum_typedefs_resolve_to_nested_types():
    objects = {
        "arc": {
            "members": {
                "MODE": {"type": "enum_type", "members": {}},
            },
        },
    }
    mapping = build_enum_typedef_map([], objects=objects)

    assert mapping["arc_mode_t"] == "arc.MODE"
    assert mapping["obj_tree_walk_res_t"] == "obj.TREE_WALK"
    assert mapping["menu_mode_header_t"] == "menu.HEADER"


def test_enriched_receivers_are_removed_exactly_once():
    area_proto = {
        "type": "function",
        "args": [
            {"type": "area_t", "name": "dest"},
            {"type": "area_t", "name": "src"},
        ],
        "return_type": "NoneType",
    }
    area_info = enrich_struct_function_info(
        "area_t",
        "copy",
        area_proto,
        {"lv_area_copy": area_proto},
    )
    assert area_info["receiver_stripped"] is True

    swap_proto = {
        "type": "function",
        "args": [
            {"type": "obj", "name": "obj1"},
            {"type": "obj", "name": "obj2"},
        ],
        "return_type": "NoneType",
    }
    swap_info = enrich_function_info(
        "swap", swap_proto, {"lv_obj_swap": swap_proto}, obj_name="obj"
    )
    assert swap_info["receiver_stripped"] is True


def test_static_struct_enrichment_keeps_explicit_receiver_argument():
    proto = {
        "type": "function",
        "static": True,
        "args": [
            {"type": "color_t", "name": "color"},
            {"type": "color_t", "name": "low"},
            {"type": "color_t", "name": "high"},
        ],
        "return_type": "bool",
    }

    enriched = enrich_struct_function_info(
        "color_t", "is_in_range", proto, {"lv_color_is_in_range": proto}
    )

    assert [arg["name"] for arg in enriched["args"]] == ["color", "low", "high"]
    assert enriched["static"] is True


def test_generated_stub_is_valid_and_has_no_duplicate_members():
    pyi_path = REPO_ROOT / "generated" / "lvgl.pyi"
    source = pyi_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(pyi_path))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [arg.arg for arg in node.args.posonlyargs + node.args.args]
            names.extend(arg.arg for arg in node.args.kwonlyargs)
            assert len(names) == len(set(names)), f"duplicate parameter in {node.name}"
        if isinstance(node, ast.ClassDef):
            members = []
            for child in node.body:
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.append(child.name)
                elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    members.append(child.target.id)
            duplicates = [name for name, count in Counter(members).items() if count > 1]
            assert not duplicates, f"duplicate member in {node.name}: {duplicates}"


def test_generated_stub_annotations_reference_declared_names():
    tree = ast.parse(
        (REPO_ROOT / "generated" / "lvgl.pyi").read_text(encoding="utf-8")
    )
    declared = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    declared.update(
        node.target.id
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    )
    declared.update({"Any", "Callable", "ClassVar", "None", "Sequence", "TypeAlias", "bool", "bytes", "dict", "float", "int", "list", "set", "str", "tuple", "type"})
    declared.update(
        child.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for child in node.body
        if isinstance(child, ast.AnnAssign)
        and isinstance(child.target, ast.Name)
    )

    annotation_names = set()
    for node in ast.walk(tree):
        annotations = []
        if isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            annotations.append(node.returns)
        for annotation in annotations:
            annotation_names.update(
                child.id for child in ast.walk(annotation) if isinstance(child, ast.Name)
            )

    assert annotation_names <= declared


def test_generated_stub_covers_the_shared_ir_namespace():
    api = json.loads(
        (REPO_ROOT / "generated" / "api.json").read_text(encoding="utf-8")
    )
    tree = ast.parse((REPO_ROOT / "generated" / "lvgl.pyi").read_text(encoding="utf-8"))
    top_level = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }
    top_level.update(
        node.target.id
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    )

    expected = {
        function["python_name"]
        for function in api["functions"]
        if function["visibility"] == "public"
        and function["role"] == "module"
        and set(function["available_on"]) == {
            "micropython",
            "circuitpython",
            "cpython",
        }
    }
    expected.update(
        object_["python_name"]
        for object_ in api["objects"]
        if object_["visibility"] == "public"
    )
    expected.update(
        struct["python_name"]
        for struct in api["structs"]
        if struct["visibility"] == "public"
    )
    expected.update(
        enum["module_name"]
        for enum in api["enums"]
        if enum["visibility"] == "public" and enum.get("module_name")
    )
    expected.update(
        variable["python_name"]
        for variable in api["variables"]
        if variable["visibility"] == "public"
    )
    expected.add("_nesting")
    expected.update(
        constant["python_name"]
        for constant in api["constants"]
        if constant["visibility"] == "public"
    )

    assert expected <= top_level


def test_pyi_only_flag_preserves_c_and_ir_artifacts():
    protected = [
        REPO_ROOT / "generated" / "lvgl_micropython.c",
        REPO_ROOT / "generated" / "lvgl_circuitpython.c",
        REPO_ROOT / "generated" / "lvgl_circuitpython.h",
        REPO_ROOT / "generated" / "lvgl_python.c",
        REPO_ROOT / "generated" / "lvgl.json",
        REPO_ROOT / "generated" / "lvgl.pp",
        REPO_ROOT / "generated" / "api.json",
    ]

    before = {path: hashlib.sha256(path.read_bytes()).digest() for path in protected}
    subprocess.run(
        [str(REPO_ROOT / "regenerate_all.sh"), "--pyi-only"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    after = {path: hashlib.sha256(path.read_bytes()).digest() for path in protected}

    assert after == before


def test_regenerate_help_documents_pyi_only():
    result = subprocess.run(
        [str(REPO_ROOT / "regenerate_all.sh"), "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--pyi-only" in result.stdout
