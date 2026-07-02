"""Generate lvgl.pyi from lvgl.json (all targets; run after regenerate)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, TextIO, Union

from .helpers import export_name
from .naming import get_naming_style
from .pyi_prototypes import (
    _CALLBACK_TYPEDEFS,
    _is_named_obj_receiver,
    _is_trailing_obj_receiver,
    default_pp_path_for_metadata,
    enrich_ir_metadata,
    parse_pp_prototypes,
)

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

# Map C typedef names to module-level enum classes in lvgl.pyi.
_ENUM_TYPEDEFS: Dict[str, str] = {
    "align_t": "ALIGN",
    "color_format_t": "COLOR_FORMAT",
    "grad_dir_t": "GRAD_DIR",
    "grad_extend_t": "GRAD_EXTEND",
    "base_dir_t": "BASE_DIR",
    "opa_t": "OPA",
    "text_align_t": "TEXT_ALIGN",
    "palette_t": "PALETTE",
    "font_kerning_t": "FONT_KERNING",
    "font_subpx_t": "FONT_SUBPX",
    "font_glyph_format_t": "FONT_GLYPH_FORMAT",
    "dir_t": "DIR",
    "result_t": "RESULT",
    "log_level_t": "LOG_LEVEL",
}


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
        struct_funcs = self.metadata.get("struct_functions", {})
        for struct_name in sorted(self.known_structs):
            safe = export_name(struct_name, "struct")
            members = struct_funcs.get(struct_name, {})
            methods = [
                (name, info)
                for name, info in sorted(members.items())
                if info.get("type") == "function"
            ]
            if not methods:
                self._add(f"class {safe}(Struct): ...")
                continue
            self._add(f"class {safe}(Struct):")
            for method_name, info in methods:
                sig = self._format_function(
                    method_name,
                    info,
                    instance_method=True,
                    receiver_struct=struct_name,
                )
                self._add(f"    def {sig}")
        self._add()

    def _emit_module_enums(self) -> None:
        for enum_name in sorted(self.enum_names):
            members = self.metadata["enums"][enum_name].get("members", {})
            if not members:
                continue
            self._emit_enum_class(enum_name, members)

    def _emit_widget_types(self) -> None:
        objects = self.metadata.get("objects", {})
        obj_members = objects.get("obj", {}).get("members", {})
        for obj_name in sorted(objects):
            members = objects[obj_name].get("members", {})
            if not members:
                continue
            parent = (
                export_name("obj", "object")
                if obj_name != "obj"
                else "Struct"
            )
            self._emit_widget_class(
                obj_name,
                members,
                parent=parent,
                inherited_members=obj_members if obj_name != "obj" else None,
            )

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
        inherited_members: Optional[Mapping[str, Any]] = None,
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
                if inherited_members is not None and member_name in inherited_members:
                    continue
                methods.append((member_name, info))

        self._add(f"class {safe}({parent}):")
        if not methods and not nested_enums and obj_name != "obj":
            self._add("    ...")
            self._add()
            return
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
            sig = self._format_function(
                method_name,
                info,
                instance_method=True,
                receiver_obj=obj_name,
            )
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
        receiver_obj: Optional[str] = None,
        receiver_struct: Optional[str] = None,
    ) -> str:
        args = list(info.get("args", []))
        if instance_method:
            args = self._strip_receiver_arg(
                args,
                receiver_obj=receiver_obj,
                receiver_struct=receiver_struct,
            )
        params = self._format_params(args)
        return_type = self._format_return_type(
            info.get("return_type"),
            instance_method,
            name,
        )
        safe_name = export_name(name, "function")
        if params:
            return f"{safe_name}({params}) -> {return_type}: ..."
        return f"{safe_name}() -> {return_type}: ..."

    def _strip_receiver_arg(
        self,
        args: Sequence[Mapping[str, Any]],
        *,
        receiver_obj: Optional[str] = None,
        receiver_struct: Optional[str] = None,
    ) -> List[Mapping[str, Any]]:
        del receiver_struct
        if not args:
            return []
        result = list(args)
        if receiver_obj and result and _is_named_obj_receiver(result[0]):
            return result[1:]
        if receiver_obj and len(result) > 1 and _is_trailing_obj_receiver(result[-1]):
            return result[:-1]
        return result

    def _format_params(self, args: Sequence[Mapping[str, Any]]) -> str:
        parts: List[str] = []
        for arg in args:
            arg_name = sanitize(arg.get("name") or "arg")
            if arg_name in _PY_KEYWORDS:
                arg_name = f"_{arg_name}"
            parts.append(f"{arg_name}: {self._format_arg_type(arg)}")
        return ", ".join(parts)

    def _format_callback_type(self, func_info: Mapping[str, Any]) -> str:
        args = func_info.get("args", [])
        param_types: List[str] = []
        for arg in args:
            if isinstance(arg, Mapping):
                param_types.append(self._format_arg_type(arg))
            else:
                param_types.append(self._map_type(str(arg)))
        ret = func_info.get("return_type")
        if ret in (None, "NoneType", "void"):
            ret_str = "None"
        else:
            ret_str = self._map_type(str(ret))
        if not param_types:
            return "Callable[..., Any]"
        return "Callable[[{}], {}]".format(", ".join(param_types), ret_str)

    def _format_arg_type(self, arg: Union[str, Mapping[str, Any], None]) -> str:
        if isinstance(arg, Mapping):
            arg_type = arg.get("type", "Any")
            if arg_type == "callback":
                func_info = arg.get("function")
                if isinstance(func_info, Mapping):
                    return self._format_callback_type(func_info)
            normalized = str(arg_type)
            if normalized in _CALLBACK_TYPEDEFS:
                typedef = _CALLBACK_TYPEDEFS[normalized]
                func_info = typedef.get("function")
                if isinstance(func_info, Mapping):
                    return self._format_callback_type(func_info)
            return self._map_type(normalized)
        if not arg:
            return "Any"
        c_type = str(arg)
        if c_type in _OBJ_POINTER_TYPES or c_type in {"obj_t"}:
            return export_name("obj", "object")
        if c_type.endswith("_obj_t*"):
            widget = c_type[: -len("_obj_t*")]
            if widget in self.known_objects:
                return export_name(widget, "object")
            return export_name("obj", "object")
        return self._map_type(c_type)

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
        if c_type in _OBJ_POINTER_TYPES or c_type in {"obj_t"}:
            return export_name("obj", "object")
        if c_type.endswith("_obj_t*"):
            widget = c_type[: -len("_obj_t*")]
            if widget in self.known_objects:
                return export_name(widget, "object")
            return export_name("obj", "object")
        if c_type in self.known_structs:
            return export_name(c_type, "struct")
        if c_type in self.known_objects:
            return export_name(c_type, "object")
        return self._map_type(c_type)

    def _map_type(self, c_type: str) -> str:
        if c_type in {"int", "bool", "float", "str"}:
            return c_type
        if c_type in _OBJ_POINTER_TYPES or c_type == "obj_t":
            return export_name("obj", "object")
        if c_type in _ENUM_TYPEDEFS:
            enum_name = _ENUM_TYPEDEFS[c_type]
            if enum_name in self.enum_names:
                return export_name(enum_name, "enum")
        if c_type in self.enum_names:
            return export_name(c_type, "enum")
        if c_type in {"char*", "const char*"}:
            return "str"
        if c_type in {"void*", "const void*", "const uint8_t*"}:
            return "Any"
        if c_type in {"function pointer", "callback"}:
            return "Callable[..., Any]"
        if c_type in self.known_structs:
            return export_name(c_type, "struct")
        if c_type in self.known_objects:
            return export_name(c_type, "object")
        if c_type.endswith("*"):
            base = c_type[:-1]
            if base in self.known_structs:
                return export_name(base, "struct")
            return "Any"
        if c_type.endswith("_t") and c_type in self.known_structs:
            return export_name(c_type, "struct")
        if c_type.endswith("_t"):
            return sanitize(c_type)
        return "Any"


def struct_prefix_name(struct_name: str) -> str:
    if struct_name.endswith("_t"):
        return struct_name[:-2]
    return struct_name


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


def load_and_enrich_metadata(metadata_path: Path) -> Dict[str, Any]:
    metadata = load_metadata(metadata_path)
    pp_path = default_pp_path_for_metadata(metadata_path)
    if pp_path is None:
        return metadata
    pp_index = parse_pp_prototypes(pp_path)
    return enrich_ir_metadata(metadata, pp_index)


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
    metadata = load_and_enrich_metadata(metadata_path)
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
