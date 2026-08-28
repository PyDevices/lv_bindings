"""End-to-end regression tests for canonical stub generation."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_generated_stub_is_valid_and_has_no_duplicate_members():
    pyi_path = REPO_ROOT / "generated" / "lvgl.pyi"
    tree = ast.parse(pyi_path.read_text(encoding="utf-8"), filename=str(pyi_path))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [arg.arg for arg in node.args.posonlyargs + node.args.args]
            names.extend(arg.arg for arg in node.args.kwonlyargs)
            assert len(names) == len(set(names)), f"duplicate parameter in {node.name}"
        if isinstance(node, ast.ClassDef):
            members = {}
            for child in node.body:
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.setdefault(child.name, []).append(child)
                elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    members.setdefault(child.target.id, []).append(child)
            duplicates = [
                name
                for name, declarations in members.items()
                if len(declarations) > 1
                and not all(
                    isinstance(declaration, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and any(
                        isinstance(decorator, ast.Name) and decorator.id == "overload"
                        for decorator in declaration.decorator_list
                    )
                    for declaration in declarations
                )
            ]
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
    declared.update(
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    )
    declared.update(
        {
            "Any", "Callable", "ClassVar", "None", "Sequence", "TypeAlias",
            "bool", "bytes", "dict", "float", "int", "list", "memoryview",
            "set", "str", "tuple", "type",
        }
    )
    declared.update(
        child.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for child in node.body
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
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


def test_generated_stub_covers_the_shared_api_namespace():
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
        and set(function["available_on"])
        == {"micropython", "circuitpython", "cpython"}
    }
    expected.update(
        item["python_name"]
        for section in ("objects", "structs", "variables", "constants")
        for item in api[section]
        if item["visibility"] == "public"
    )
    expected.update(
        enum["module_name"]
        for enum in api["enums"]
        if enum["visibility"] == "public" and enum.get("module_name")
    )

    assert expected <= top_level


def test_pyi_only_flag_preserves_non_stub_artifacts():
    protected = [
        REPO_ROOT / "generated" / "lvgl_micropython.c",
        REPO_ROOT / "generated" / "lvgl_circuitpython.c",
        REPO_ROOT / "generated" / "lvgl_circuitpython.h",
        REPO_ROOT / "generated" / "lvgl_python.c",
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
