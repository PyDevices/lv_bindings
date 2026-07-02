"""Generate lvgl.pyi from lvgl.json (all targets; run after regenerate)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, TextIO

from .helpers import export_name
from .naming import get_naming_style

_LV_VERSION_DEFINE_RE = re.compile(
    r"^#define\s+(LVGL_VERSION_MAJOR|LVGL_VERSION_MINOR|LVGL_VERSION_PATCH)\s+(\d+)",
    re.MULTILINE,
)

_PY_KEYWORDS = frozenset(
    {
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
    }
)

_OBJ_POINTER_TYPES = frozenset({"lv_obj_t*", "obj*"})


def sanitize(name: str) -> str:
    if name in _PY_KEYWORDS:
        return f"_{name}"
    return name.replace(" ", "_").replace("*", "_ptr")


def load_metadata(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_lvgl_version_major_minor(repo_root: Optional[Path] = None) -> str:
    """Read LVGL major.minor from the pinned lvgl submodule."""
    repo_root = (repo_root or Path(__file__).resolve().parent.parent).resolve()
    for version_file in (repo_root / "lvgl" / "lv_version.h", repo_root / "lvgl" / "lvgl.h"):
        if not version_file.is_file():
            continue
        text = version_file.read_text(encoding="utf-8")
        parts = {
            name: int(value)
            for name, value in _LV_VERSION_DEFINE_RE.findall(text)
        }
        if "LVGL_VERSION_MAJOR" in parts and "LVGL_VERSION_MINOR" in parts:
            return "{}.{}".format(
                parts["LVGL_VERSION_MAJOR"],
                parts["LVGL_VERSION_MINOR"],
            )
    raise FileNotFoundError(
        "could not read LVGL version from lvgl/lv_version.h under {}".format(repo_root)
    )


class PyiEmitter:
    def __init__(
        self,
        metadata: Mapping[str, Any],
        *,
        target: str = "cpython",
        module_name: str = "lvgl",
        lvgl_version: Optional[str] = None,
        naming_style: Optional[str] = None,
        repo_root: Optional[Path] = None,
    ) -> None:
        self.metadata = metadata
        self.target = target
        self.module_name = module_name
        self.lvgl_version = lvgl_version or read_lvgl_version_major_minor(repo_root)
        self.naming_style = naming_style or get_naming_style()
        self.known_structs: Set[str] = set(metadata.get("structs", []))
        self.known_objects: Set[str] = set(metadata.get("objects", {}))
        self.lines: List[str] = []
        self.enum_names: Set[str] = set(metadata.get("enums", {}))

    def emit(self, out: TextIO) -> None:
        self.lines = []
        self._header()
        self._emit_helper_types()
        self._emit_struct_types()
        self._emit_module_enums()
        self._emit_widget_types()
        self._emit_symbol_namespace()
        self._emit_module_functions()
        self._emit_blobs_and_constants()
        out.write("\n".join(self.lines))
        if not self.lines[-1].endswith("\n"):
            out.write("\n")

    def _add(self, line: str = "", indent: int = 0) -> None:
        if line:
            self.lines.append(f"{'    ' * indent}{line}")
        else:
            self.lines.append("")

    def _header(self) -> None:
        self._add("# LVGL {}".format(self.lvgl_version))
        self._add("# Naming style: {}".format(self.naming_style))
        self._add('"""Type stubs for LVGL Python bindings (auto-generated)."""')
        self._add("from __future__ import annotations")
        self._add()
        self._add("from collections.abc import Callable")
        self._add("from typing import Any, ClassVar")
        self._add()

    def _emit_helper_types(self) -> None:
        self._add("class LvReferenceError(Exception): ...")
        self._add()
        self._add("class C_Pointer:")
        self._add("    ptr_val: Any")
        self._add("    str_val: str | None")
        self._add("    int_val: int")
        self._add("    uint_val: int")
        self._add()
        self._add("class Blob:")
        self._add("    def __dereference__(self) -> Any: ...")
        self._add()
        self._add("class Struct:")
        self._add("    __SIZE__: ClassVar[int]")
        self._add("    @classmethod")
        self._add("    def __cast__(cls, obj: Any) -> Any: ...")
        self._add("    @classmethod")
        self._add("    def __cast_instance__(cls, obj: Any) -> Any: ...")
        self._add("    @classmethod")
        self._add("    def __dereference__(cls, obj: Any) -> Any: ...")
        self._add()

    def _emit_struct_types(self) -> None:
        for struct_name in sorted(self.known_structs):
            safe = export_name(struct_name, "struct")
            self._add(f"class {safe}(Struct): ...")
        self._add()

    def _emit_module_enums(self) -> None:
        for enum_name in sorted(self.enum_names):
            members = self.metadata["enums"][enum_name].get("members", {})
            if not members:
                continue
            self._emit_enum_class(enum_name, members)

    def _emit_widget_types(self) -> None:
        objects = self.metadata.get("objects", {})
        for obj_name in sorted(objects):
            members = objects[obj_name].get("members", {})
            if not members:
                continue
            parent = (
                export_name("obj", "object")
                if obj_name != "obj"
                else "Struct"
            )
            self._emit_widget_class(obj_name, members, parent=parent)

    def _emit_enum_class(self, name: str, members: Mapping[str, Any]) -> None:
        safe = export_name(name, "enum")
        self._add(f"class {safe}:")
        for member_name in sorted(members):
            if members[member_name].get("type") != "enum_member":
                continue
            self._add(f"    {export_name(member_name, 'enum_member')}: int", indent=0)
        self._add()

    def _emit_widget_class(
        self,
        obj_name: str,
        members: Mapping[str, Any],
        *,
        parent: str,
    ) -> None:
        safe = export_name(obj_name, "object")
        nested_enums: List[tuple[str, Mapping[str, Any]]] = []
        methods: List[tuple[str, Dict[str, Any]]] = []

        for member_name, info in members.items():
            member_type = info.get("type")
            if member_type == "enum_type":
                enum_members = info.get("members", {})
                if enum_members:
                    nested_enums.append((member_name, enum_members))
            elif member_type == "function":
                methods.append((member_name, info))

        self._add(f"class {safe}({parent}):")
        for enum_name, enum_members in sorted(nested_enums, key=lambda item: item[0]):
            enum_safe = export_name(enum_name, "enum")
            self._add(f"    class {enum_safe}:")
            for member_name in sorted(enum_members):
                if enum_members[member_name].get("type") != "enum_member":
                    continue
                self._add(f"        {export_name(member_name, 'enum_member')}: int")
            self._add(f"    {enum_safe}: ClassVar[type[{enum_safe}]]")

        obj_parent = export_name("obj", "object")
        self._add(f"    def __init__(self, parent: {obj_parent} | None = ...) -> None: ...")
        for method_name, info in sorted(methods, key=lambda item: item[0]):
            sig = self._format_function(method_name, info, instance_method=True)
            self._add(f"    def {sig}")
        self._add()

    def _emit_symbol_namespace(self) -> None:
        symbol_members = []
        for blob_name in self.metadata.get("blobs", []):
            if blob_name.startswith("SYMBOL_"):
                symbol_members.append(blob_name[len("SYMBOL_") :])
        if not symbol_members:
            return
        self._add("class SYMBOL:")
        for member in sorted(symbol_members):
            self._add(f"    {export_name(member, 'enum_member')}: str")
        self._add()

    def _emit_module_functions(self) -> None:
        function_names = sorted(self.metadata.get("functions", {}))

        emitted: Set[str] = set()
        for func_name in function_names:
            info = self.metadata["functions"].get(func_name, {})
            if not info or info.get("type") != "function":
                continue
            sig = self._format_function(func_name, info, instance_method=False)
            if sig in emitted:
                continue
            emitted.add(sig)
            self._add(f"def {sig}", indent=0)

    def _emit_blobs_and_constants(self) -> None:
        for blob_name in sorted(self.metadata.get("blobs", [])):
            if blob_name.startswith("SYMBOL_"):
                continue
            self._add(f"{export_name(blob_name, 'blob')}: Any")
        for const_name in sorted(self.metadata.get("int_constants", [])):
            self._add(f"{export_name(const_name, 'constant')}: int")

    def _format_function(
        self,
        name: str,
        info: Mapping[str, Any],
        *,
        instance_method: bool,
    ) -> str:
        args = list(info.get("args", []))
        if instance_method:
            args = self._strip_receiver_arg(args)
        params = self._format_params(args)
        return_type = self._format_return_type(info.get("return_type"), instance_method, name)
        safe_name = export_name(name, "function")
        if params:
            return f"{safe_name}({params}) -> {return_type}: ..."
        return f"{safe_name}() -> {return_type}: ..."

    def _strip_receiver_arg(self, args: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
        if not args:
            return []
        first = args[0]
        arg_type = first.get("type", "")
        if arg_type in _OBJ_POINTER_TYPES or arg_type.endswith("_obj_t*"):
            return list(args[1:])
        if first.get("name") in {"obj", "self"}:
            return list(args[1:])
        return list(args)

    def _format_params(self, args: Sequence[Mapping[str, Any]]) -> str:
        parts: List[str] = []
        for arg in args:
            arg_name = sanitize(arg.get("name") or "arg")
            if arg_name in _PY_KEYWORDS:
                arg_name = f"_{arg_name}"
            parts.append(f"{arg_name}: {self._format_arg_type(arg.get('type', 'Any'))}")
        return ", ".join(parts)

    def _format_arg_type(self, c_type: Optional[str]) -> str:
        if not c_type:
            return "Any"
        if c_type in _OBJ_POINTER_TYPES:
            return "obj"
        if c_type.endswith("_obj_t*"):
            widget = c_type[: -len("_obj_t*")]
            if widget in self.known_objects:
                return sanitize(widget)
            return "obj"
        py_type = self._map_type(c_type)
        if py_type == "Callable[..., Any]":
            return py_type
        return py_type

    def _format_return_type(
        self,
        c_type: Optional[str],
        instance_method: bool,
        name: str,
    ) -> str:
        if not c_type:
            if name.endswith("_create") or name == "create":
                return "obj"
            return "Any"
        if c_type == "NoneType":
            return "None"
        if c_type in _OBJ_POINTER_TYPES:
            return "obj"
        if c_type.endswith("_obj_t*"):
            widget = c_type[: -len("_obj_t*")]
            if widget in self.known_objects:
                return sanitize(widget)
            return "obj"
        return self._map_type(c_type)

    def _map_type(self, c_type: str) -> str:
        if c_type in {"int", "bool", "float", "str"}:
            return c_type
        if c_type in {"char*", "const char*"}:
            return "str"
        if c_type in {"void*", "const void*", "const uint8_t*"}:
            return "Any"
        if c_type in {"function pointer", "callback"}:
            return "Callable[..., Any]"
        if c_type in self.known_structs:
            return sanitize(c_type)
        if c_type.endswith("*"):
            base = c_type[:-1]
            if base in self.known_structs:
                return sanitize(base)
            return "Any"
        if c_type.endswith("_t") and c_type in self.known_structs:
            return sanitize(c_type)
        if c_type.endswith("_t"):
            return sanitize(c_type)
        return "Any"


def default_metadata_path(generated_dir: Path, target: str = "micropython") -> Path:
    del target
    return generated_dir.resolve() / "lvgl.json"


def default_output_path(generated_dir: Path, target: str = "micropython") -> Path:
    del target
    return generated_dir.resolve() / "lvgl.pyi"


ALL_TARGETS = ("cpython", "micropython", "circuitpython")


def generate_pyi(
    generated_dir: Path,
    *,
    metadata_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    module_name: str = "lvgl",
) -> Path:
    metadata_path = metadata_path or default_metadata_path(generated_dir)
    output_path = output_path or default_output_path(generated_dir)

    if not metadata_path.is_file():
        raise FileNotFoundError(f"metadata file not found: {metadata_path}")

    write_pyi(
        metadata_path,
        output_path,
        target="micropython",
        module_name=module_name,
    )
    return output_path


def generate_all_pyis(
    generated_dir: Path,
    *,
    metadata_path: Optional[Path] = None,
    module_name: str = "lvgl",
) -> List[Path]:
    return [generate_pyi(generated_dir, metadata_path=metadata_path, module_name=module_name)]


def generate_pyi_for_target(
    generated_dir: Path,
    target: str,
    *,
    metadata_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    module_name: str = "lvgl",
) -> Path:
    del target
    return generate_pyi(
        generated_dir,
        metadata_path=metadata_path,
        output_path=output_path,
        module_name=module_name,
    )


def write_pyi(
    metadata_path: Path,
    output_path: Path,
    *,
    target: str = "cpython",
    module_name: str = "lvgl",
    lvgl_version: Optional[str] = None,
    naming_style: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> None:
    metadata = load_metadata(metadata_path)
    repo_root = repo_root or metadata_path.resolve().parent.parent

    emitter = PyiEmitter(
        metadata,
        target=target,
        module_name=module_name,
        lvgl_version=lvgl_version,
        naming_style=naming_style,
        repo_root=repo_root,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        emitter.emit(handle)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import os

    from binding.naming import set_naming_style

    parser = argparse.ArgumentParser(
        description="Generate lvgl.pyi stubs from lvgl.json."
    )
    parser.add_argument(
        "--target",
        choices=list(ALL_TARGETS) + ["all"],
        default="all",
        help="Ignored (kept for compatibility); always writes generated/lvgl.pyi",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Metadata JSON (default: generated/lvgl.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output .pyi path (default: generated/lvgl.pyi)",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "generated",
        help="Directory containing generated JSON artifacts",
    )
    parser.add_argument(
        "--naming-style",
        choices=["legacy", "pythonic"],
        default=os.environ.get("LV_NAMING_STYLE", "legacy"),
        help="Python export naming style (default: legacy; env: LV_NAMING_STYLE)",
    )
    parser.add_argument(
        "--pythonic",
        action="store_const",
        const="pythonic",
        dest="naming_style",
        help="Shorthand for --naming-style pythonic",
    )
    args = parser.parse_args(argv)
    set_naming_style(args.naming_style)

    if args.target == "all":
        output_path = generate_pyi(
            args.generated_dir,
            metadata_path=args.metadata,
            output_path=args.output,
        )
        print(f"Wrote {output_path}")
        return 0

    output_path = generate_pyi(
        args.generated_dir,
        metadata_path=args.metadata,
        output_path=args.output,
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
