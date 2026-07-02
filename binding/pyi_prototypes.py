"""Parse lvgl.pp function prototypes for .pyi enrichment (does not affect C emit)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

_FUNC_PROTO_RE = re.compile(
    r"^(?:static\s+inline\s+)?"
    r"(?P<ret>.+?)\s+"
    r"(?P<name>lv_[a-zA-Z0-9_]+)\s*"
    r"\((?P<params>[^)]*)\)\s*;",
    re.MULTILINE,
)

_INT_TYPES = frozenset(
    {
        "int8_t",
        "uint8_t",
        "int16_t",
        "uint16_t",
        "int32_t",
        "uint32_t",
        "int64_t",
        "uint64_t",
        "size_t",
        "intptr_t",
        "uintptr_t",
    }
)


_TYPEDEF_CB_RE = re.compile(
    r"typedef\s+(?P<ret>.+?)\s+\(\s*\*\s*(?P<name>lv_\w+(?:_cb_t|_xcb_t))\s*\)\s*\((?P<params>[^;]*)\)\s*;",
    re.DOTALL,
)

_ENUM_TYPEDEF_RE = re.compile(
    r"typedef\s+enum\s*(?:\w+\s*)?\{.*?\}\s*(?P<name>lv_\w+_t)\s*;",
    re.DOTALL,
)

# Hardcoded typedef→enum overrides (e.g. event_code_t → EVENT, not EVENT_CODE).
_LEGACY_ENUM_TYPEDEFS: Dict[str, str] = {
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
    "event_code_t": "EVENT",
}

_STRUCT_TYPEDEF_RE = re.compile(
    r"typedef\s+struct\s*\{(?P<body>.*?)\}\s*(?P<name>lv_\w+_t)\s*;",
    re.DOTALL,
)

_STRUCT_FIELD_RE = re.compile(
    r"^\s*(?P<type>[\w\s\*]+?)\s+(?P<name>\w+)(?:\s*:\s*\d+)?\s*;\s*$",
    re.MULTILINE,
)

_OBJ_PARAM_NAMES = frozenset(
    {
        "parent",
        "base",
        "class_p",
        "screen",
        "child",
        "target",
        "relative_to",
    }
)


def split_params(params: str) -> List[str]:
    if not params or params.strip() in ("", "void"):
        return []
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in params:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            piece = "".join(current).strip()
            if piece:
                parts.append(piece)
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _strip_c_qualifiers(type_str: str) -> str:
    result = type_str.strip()
    for qual in ("const", "volatile", "restrict", "__restrict"):
        result = re.sub(rf"\b{qual}\b", "", result)
    return re.sub(r"\s+", " ", result).strip()


def parse_param(param: str) -> Tuple[str, str]:
    param = param.strip()
    if not param:
        return "Any", "arg"
    if "(" in param:
        return "callback", "cb"
    name_match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*$", param)
    if not name_match:
        return _normalize_c_type(param), "arg"
    name = name_match.group(1)
    type_part = param[: name_match.start()].strip()
    if not type_part:
        normalized = _normalize_c_type(name)
        if normalized != "Any":
            return normalized, "arg"
        return "Any", name
    return _normalize_c_type(type_part), name


def _normalize_c_type(type_str: str) -> str:
    cleaned = _strip_c_qualifiers(type_str)
    if not cleaned:
        return "Any"
    if cleaned == "void":
        return "NoneType"
    if cleaned == "bool":
        return "bool"
    if cleaned == "float":
        return "float"
    if cleaned in _INT_TYPES:
        return "int"
    if cleaned in {"char", "char *", "char*"} or cleaned.endswith("char *") or cleaned.endswith("char*"):
        return "str"
    if cleaned in {"void *", "void*"} or cleaned.endswith("void *") or cleaned.endswith("void*"):
        return "void*"
    pointer = cleaned.endswith("*")
    base = cleaned.rstrip(" *").split()[-1] if cleaned else cleaned
    if base.startswith("lv_") and base.endswith("_t"):
        return base[3:]
    if base.endswith("_obj_t"):
        return "obj"
    if pointer:
        if base.endswith("_t"):
            return base[3:] if base.startswith("lv_") else base
        return "Any"
    return base


def normalize_return_type(type_str: str) -> str:
    cleaned = _strip_c_qualifiers(type_str)
    if not cleaned or cleaned == "void":
        return "NoneType"
    if cleaned.endswith("*"):
        inner = _normalize_c_type(cleaned)
        if inner == "obj":
            return "obj"
        if inner.endswith("_t") or inner in {"display_t", "color_t"}:
            return inner
        return "Any"
    mapped = _normalize_c_type(cleaned)
    if mapped == "NoneType":
        return "NoneType"
    if mapped in {"int", "bool", "float", "str"}:
        return mapped
    return mapped


def parse_pp_prototypes(pp_path: Path) -> Dict[str, Dict[str, Any]]:
    text = pp_path.read_text(encoding="utf-8", errors="replace")
    index: Dict[str, Dict[str, Any]] = {}
    for match in _FUNC_PROTO_RE.finditer(text):
        name = match.group("name")
        ret = match.group("ret").strip()
        params = split_params(match.group("params"))
        args = []
        for param in params:
            arg_type, arg_name = parse_param(param)
            args.append({"type": arg_type, "name": arg_name})
        index[name] = {
            "type": "function",
            "args": args,
            "return_type": normalize_return_type(ret),
        }
    return index


def _typedef_export_name(c_name: str) -> str:
    if c_name.startswith("lv_"):
        return c_name[3:]
    return c_name


def _callback_signature(ret: str, params: str) -> Dict[str, Any]:
    args = []
    for param in split_params(params):
        arg_type, arg_name = parse_param(param)
        args.append({"type": arg_type, "name": arg_name})
    return {
        "type": "callback",
        "function": {
            "args": args,
            "return_type": normalize_return_type(ret),
        },
    }


def _refine_callback_signature(
    export_name: str,
    signature: Dict[str, Any],
) -> Dict[str, Any]:
    """Refine loose pp callback types (e.g. anim void* receiver → anim_t)."""
    func = signature.get("function")
    if not isinstance(func, Mapping):
        return signature
    if not export_name.startswith("anim_"):
        return signature
    refined_args: List[Dict[str, Any]] = []
    changed = False
    for index, arg in enumerate(func.get("args", [])):
        if not isinstance(arg, Mapping):
            refined_args.append(arg)
            continue
        merged = dict(arg)
        if index == 0 and merged.get("type") in {"void*", "Any"}:
            merged["type"] = "anim_t"
            changed = True
        refined_args.append(merged)
    if not changed:
        return signature
    refined = dict(signature)
    refined_func = dict(func)
    refined_func["args"] = refined_args
    refined["function"] = refined_func
    return refined


def parse_pp_callback_typedefs(pp_path: Path) -> Dict[str, Dict[str, Any]]:
    text = pp_path.read_text(encoding="utf-8", errors="replace")
    typedefs: Dict[str, Dict[str, Any]] = {}
    for match in _TYPEDEF_CB_RE.finditer(text):
        export = _typedef_export_name(match.group("name"))
        signature = _refine_callback_signature(
            export,
            _callback_signature(match.group("ret"), match.group("params")),
        )
        c_name = match.group("name")
        typedefs[c_name] = signature
        typedefs[export] = signature
    return typedefs


def parse_pp_enum_typedef_names(pp_path: Path) -> List[str]:
    text = pp_path.read_text(encoding="utf-8", errors="replace")
    names: List[str] = []
    for match in _ENUM_TYPEDEF_RE.finditer(text):
        names.append(_typedef_export_name(match.group("name")))
    return names


def enum_typedef_candidates(typedef_name: str) -> List[str]:
    base = typedef_name[:-2] if typedef_name.endswith("_t") else typedef_name
    candidates = [base.upper()]
    if base.startswith("screen_"):
        candidates.append("SCR_" + base[7:].upper())
    if base.startswith("scr_"):
        candidates.append("SCREEN_" + base[4:].upper())
    if base.endswith("_code"):
        candidates.append(base[:-5].upper())
    return candidates


def build_enum_typedef_map(
    enum_names: Sequence[str],
    pp_path: Optional[Path] = None,
    *,
    extra: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Map exported C enum typedef names (e.g. screen_load_anim_t) to IR enum keys."""
    enum_set = set(enum_names)
    mapping: Dict[str, str] = dict(_LEGACY_ENUM_TYPEDEFS)
    if extra:
        mapping.update(extra)
    if pp_path is not None and pp_path.is_file():
        for typedef_name in parse_pp_enum_typedef_names(pp_path):
            if typedef_name in mapping:
                continue
            for candidate in enum_typedef_candidates(typedef_name):
                if candidate in enum_set:
                    mapping[typedef_name] = candidate
                    break
    return mapping


def parse_pp_struct_fields(pp_path: Path) -> Dict[str, List[Dict[str, str]]]:
    text = pp_path.read_text(encoding="utf-8", errors="replace")
    fields_by_struct: Dict[str, List[Dict[str, str]]] = {}
    for match in _STRUCT_TYPEDEF_RE.finditer(text):
        body = match.group("body")
        struct_name = _typedef_export_name(match.group("name"))
        fields: List[Dict[str, str]] = []
        for field_match in _STRUCT_FIELD_RE.finditer(body):
            field_type = _normalize_c_type(field_match.group("type"))
            field_name = field_match.group("name")
            if field_name:
                fields.append({"name": field_name, "type": field_type})
        if fields:
            fields_by_struct[struct_name] = fields
    return fields_by_struct


_CALLBACK_TYPEDEFS: Dict[str, Dict[str, Any]] = {
    "event_cb_t": {
        "type": "callback",
        "function": {
            "args": [{"type": "event_t", "name": "e"}],
            "return_type": "NoneType",
        },
    },
    "lv_event_cb_t": {
        "type": "callback",
        "function": {
            "args": [{"type": "event_t", "name": "e"}],
            "return_type": "NoneType",
        },
    },
}


def build_callback_typedef_map(
    pp_path: Optional[Path] = None,
    *,
    extra: Optional[Mapping[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    merged = dict(_CALLBACK_TYPEDEFS)
    if extra:
        merged.update(extra)
    if pp_path is not None and pp_path.is_file():
        merged.update(parse_pp_callback_typedefs(pp_path))
    return merged


def module_c_name(export_name: str, *, module_prefix: str = "lv") -> str:
    if export_name.startswith(f"{module_prefix}_"):
        return export_name
    return f"{module_prefix}_{export_name}"


def method_c_name(obj_name: str, method_name: str, *, module_prefix: str = "lv") -> str:
    py_method = "del" if method_name == "delete" else method_name
    return f"{module_prefix}_{obj_name}_{py_method}"


def struct_prefix(struct_name: str) -> str:
    if struct_name.endswith("_t"):
        return struct_name[:-2]
    return struct_name


def struct_method_c_name(struct_name: str, method_name: str, *, module_prefix: str = "lv") -> str:
    prefix = struct_prefix(struct_name)
    py_method = "del" if method_name == "delete" else method_name
    return f"{module_prefix}_{prefix}_{py_method}"


def _struct_receiver_types(struct_name: str) -> frozenset[str]:
    return frozenset({struct_name, struct_prefix(struct_name)})


def _is_obj_type(arg_type: str) -> bool:
    return arg_type in {"obj", "obj_t", "lv_obj_t*"} or arg_type.endswith("_obj_t*")


def _is_named_obj_receiver(arg: Mapping[str, Any]) -> bool:
    if arg.get("name") not in {"obj", "self"}:
        return False
    arg_type = arg.get("type", "")
    return arg_type in {"obj", "obj_t", "lv_obj_t*"} or arg_type.endswith("_obj_t*")


def _is_trailing_obj_receiver(arg: Mapping[str, Any]) -> bool:
    return arg.get("name") in {"obj", "self"} and _is_named_obj_receiver(arg)


def _is_trailing_struct_receiver(arg: Mapping[str, Any], struct_name: str) -> bool:
    arg_type = arg.get("type", "")
    if arg_type not in _struct_receiver_types(struct_name):
        return False
    name = arg.get("name", "")
    prefix = struct_prefix(struct_name)
    return name in {prefix, "disp", "obj", "self", "a", "at", "area", "area_p", "color", "c"}


def strip_receiver_args(
    args: Sequence[Mapping[str, Any]],
    *,
    receiver_struct: Optional[str] = None,
    receiver_obj: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not args:
        return []
    result = [dict(arg) for arg in args]

    if receiver_obj:
        if result and _is_named_obj_receiver(result[0]):
            return result[1:]
        if (
            result
            and _is_obj_type(result[0].get("type", ""))
            and result[0].get("name") not in _OBJ_PARAM_NAMES
        ):
            return result[1:]
        if len(result) > 1 and _is_trailing_obj_receiver(result[-1]):
            return result[:-1]
        return result

    if receiver_struct:
        receiver_types = _struct_receiver_types(receiver_struct)
        if result and result[0].get("type", "") in receiver_types:
            return result[1:]
        if len(result) > 1 and _is_trailing_struct_receiver(result[-1], receiver_struct):
            return result[:-1]

    return result


def normalize_callback_arg(
    arg: Mapping[str, Any],
    *,
    callback_typedefs: Optional[Mapping[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    merged = dict(arg)
    if merged.get("type") == "callback" and isinstance(merged.get("function"), Mapping):
        return merged
    typedef_map = callback_typedefs if callback_typedefs is not None else _CALLBACK_TYPEDEFS
    arg_type = str(merged.get("type", ""))
    typedef = typedef_map.get(arg_type)
    if typedef is not None:
        merged = dict(typedef)
        if arg.get("name"):
            merged["name"] = arg["name"]
        return merged
    return merged


def merge_pp_arg(
    pp_arg: Mapping[str, Any],
    ir_arg: Optional[Mapping[str, Any]],
    *,
    callback_typedefs: Optional[Mapping[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if ir_arg is not None:
        if ir_arg.get("type") == "callback" and isinstance(ir_arg.get("function"), Mapping):
            pp_type = str(pp_arg.get("type", ""))
            if pp_type.endswith(("_cb_t", "_xcb_t")):
                return normalize_callback_arg(pp_arg, callback_typedefs=callback_typedefs)
            merged = dict(ir_arg)
            if pp_arg.get("name"):
                merged["name"] = pp_arg["name"]
            return merged
        if ir_arg.get("type") == "function pointer":
            return normalize_callback_arg(pp_arg, callback_typedefs=callback_typedefs)
        merged = dict(ir_arg)
        if pp_arg.get("name"):
            merged["name"] = pp_arg["name"]
        pp_type = pp_arg.get("type")
        if pp_type and ir_arg.get("type") != "callback":
            merged["type"] = pp_type
        if merged.get("type", "").endswith(("_cb_t", "_xcb_t")):
            return normalize_callback_arg(merged, callback_typedefs=callback_typedefs)
        return merged
    return normalize_callback_arg(pp_arg, callback_typedefs=callback_typedefs)


def align_args_to_pp(
    ir_args: Sequence[Mapping[str, Any]],
    pp_args: Sequence[Mapping[str, Any]],
    *,
    receiver_struct: Optional[str] = None,
    receiver_obj: Optional[str] = None,
    callback_typedefs: Optional[Mapping[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    pp_params = strip_receiver_args(
        pp_args,
        receiver_struct=receiver_struct,
        receiver_obj=receiver_obj,
    )
    if not pp_params:
        return strip_receiver_args(
            ir_args,
            receiver_struct=receiver_struct,
            receiver_obj=receiver_obj,
        )

    ir_by_name = {
        arg.get("name"): arg for arg in ir_args if arg.get("name")
    }
    aligned: List[Dict[str, Any]] = []
    used: set[str] = set()
    for pp_arg in pp_params:
        name = pp_arg.get("name")
        ir_arg = ir_by_name.get(name) if name else None
        aligned.append(merge_pp_arg(pp_arg, ir_arg, callback_typedefs=callback_typedefs))
        if name:
            used.add(name)

    return aligned


def enrich_function_info(
    export_name: str,
    info: Mapping[str, Any],
    pp_index: Mapping[str, Dict[str, Any]],
    *,
    obj_name: Optional[str] = None,
    module_prefix: str = "lv",
    callback_typedefs: Optional[Mapping[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    merged = dict(info)
    proto = lookup_pp_proto(
        pp_index,
        export_name,
        obj_name=obj_name,
        module_prefix=module_prefix,
    )

    if not merged.get("args"):
        candidates = []
        if obj_name is not None:
            candidates.append(method_c_name(obj_name, export_name, module_prefix=module_prefix))
            if obj_name != "obj":
                candidates.append(method_c_name("obj", export_name, module_prefix=module_prefix))
        candidates.append(module_c_name(export_name, module_prefix=module_prefix))
        for c_name in candidates:
            candidate = pp_index.get(c_name)
            if candidate and candidate.get("args"):
                proto = candidate
                merged["args"] = list(candidate["args"])
                if not merged.get("return_type") and candidate.get("return_type"):
                    merged["return_type"] = candidate["return_type"]
                break
        if not merged.get("return_type") and proto and proto.get("return_type"):
            merged["return_type"] = proto["return_type"]

    if proto and proto.get("args") and merged.get("args"):
        merged["args"] = align_args_to_pp(
            merged["args"],
            proto["args"],
            receiver_obj=obj_name,
            callback_typedefs=callback_typedefs,
        )
        merged["args"] = [
            normalize_callback_arg(arg, callback_typedefs=callback_typedefs)
            for arg in merged["args"]
        ]
        if not merged.get("return_type") and proto.get("return_type"):
            merged["return_type"] = proto["return_type"]
    elif not merged.get("return_type"):
        if proto and proto.get("return_type"):
            merged["return_type"] = proto["return_type"]
    return merged


def enrich_struct_function_info(
    struct_name: str,
    export_name: str,
    info: Mapping[str, Any],
    pp_index: Mapping[str, Dict[str, Any]],
    *,
    module_prefix: str = "lv",
    callback_typedefs: Optional[Mapping[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    merged = dict(info)
    proto = lookup_pp_proto(
        pp_index,
        export_name,
        struct_name=struct_name,
        module_prefix=module_prefix,
    )

    if not merged.get("args"):
        candidates = [
            struct_method_c_name(struct_name, export_name, module_prefix=module_prefix),
            method_c_name(struct_name, export_name, module_prefix=module_prefix),
            module_c_name(export_name, module_prefix=module_prefix),
        ]
        for c_name in candidates:
            candidate = pp_index.get(c_name)
            if candidate and candidate.get("args"):
                proto = candidate
                merged["args"] = strip_receiver_args(
                    list(candidate["args"]),
                    receiver_struct=struct_name,
                )
                if not merged.get("return_type") and candidate.get("return_type"):
                    merged["return_type"] = candidate["return_type"]
                break
        if not merged.get("return_type") and proto and proto.get("return_type"):
            merged["return_type"] = proto["return_type"]
        merged["args"] = [
            normalize_callback_arg(arg, callback_typedefs=callback_typedefs)
            for arg in merged.get("args", [])
        ]
        return merged

    if proto and proto.get("args"):
        merged["args"] = align_args_to_pp(
            merged["args"],
            proto["args"],
            receiver_struct=struct_name,
            callback_typedefs=callback_typedefs,
        )
        merged["args"] = [
            normalize_callback_arg(arg, callback_typedefs=callback_typedefs)
            for arg in merged["args"]
        ]
        if not merged.get("return_type") and proto.get("return_type"):
            merged["return_type"] = proto["return_type"]
    elif not merged.get("return_type"):
        if proto and proto.get("return_type"):
            merged["return_type"] = proto["return_type"]
    return merged


def lookup_pp_proto(
    pp_index: Mapping[str, Dict[str, Any]],
    export_name: str,
    *,
    obj_name: Optional[str] = None,
    struct_name: Optional[str] = None,
    module_prefix: str = "lv",
) -> Optional[Dict[str, Any]]:
    candidates: List[str] = []
    if struct_name is not None:
        candidates.append(
            struct_method_c_name(struct_name, export_name, module_prefix=module_prefix)
        )
        candidates.append(method_c_name(struct_name, export_name, module_prefix=module_prefix))
    if obj_name is not None:
        candidates.append(method_c_name(obj_name, export_name, module_prefix=module_prefix))
        if obj_name != "obj":
            candidates.append(method_c_name("obj", export_name, module_prefix=module_prefix))
    candidates.append(module_c_name(export_name, module_prefix=module_prefix))
    for c_name in candidates:
        proto = pp_index.get(c_name)
        if proto and proto.get("args"):
            return proto
    return None


def enrich_ir_metadata(
    metadata: Dict[str, Any],
    pp_index: Mapping[str, Dict[str, Any]],
    *,
    module_prefix: str = "lv",
    pp_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Fill missing function args/return types from lvgl.pp (IR/.pyi only; no C emit)."""
    callback_typedefs = build_callback_typedef_map(pp_path)
    metadata["callback_typedefs"] = callback_typedefs
    metadata["enum_typedefs"] = build_enum_typedef_map(
        list(metadata.get("enums", {})),
        pp_path,
    )
    if pp_path is not None and pp_path.is_file():
        metadata["struct_fields"] = parse_pp_struct_fields(pp_path)

    for name, info in list(metadata.get("functions", {}).items()):
        if info.get("type") == "function":
            metadata["functions"][name] = enrich_function_info(
                name,
                info,
                pp_index,
                module_prefix=module_prefix,
                callback_typedefs=callback_typedefs,
            )

    for obj_name, obj_data in metadata.get("objects", {}).items():
        members = obj_data.get("members", {})
        for member_name, info in list(members.items()):
            if info.get("type") == "function":
                members[member_name] = enrich_function_info(
                    member_name,
                    info,
                    pp_index,
                    obj_name=obj_name,
                    module_prefix=module_prefix,
                    callback_typedefs=callback_typedefs,
                )

    for struct_name, members in metadata.get("struct_functions", {}).items():
        for member_name, info in list(members.items()):
            if info.get("type") == "function":
                members[member_name] = enrich_struct_function_info(
                    struct_name,
                    member_name,
                    info,
                    pp_index,
                    module_prefix=module_prefix,
                    callback_typedefs=callback_typedefs,
                )

    return metadata


def default_pp_path_for_metadata(metadata_path: Path) -> Optional[Path]:
    pp_path = metadata_path.resolve().parent / "lvgl.pp"
    return pp_path if pp_path.is_file() else None
