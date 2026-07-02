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


def _obj_receiver_types(obj_name: Optional[str] = None) -> frozenset[str]:
    types = {"obj", "lv_obj_t*"}
    if obj_name and obj_name != "obj":
        types.add(f"{obj_name}_obj_t*")
    return frozenset(types)


def _is_obj_receiver_arg(
    arg: Mapping[str, Any],
    obj_name: Optional[str] = None,
) -> bool:
    arg_type = arg.get("type", "")
    if arg_type in _obj_receiver_types(obj_name) or arg_type.endswith("_obj_t*"):
        return True
    return arg.get("name") in {"obj", "self"}


def strip_receiver_args(
    args: Sequence[Mapping[str, Any]],
    *,
    receiver_struct: Optional[str] = None,
    receiver_obj: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not args:
        return []
    result = [dict(arg) for arg in args]

    if receiver_obj and result and _is_obj_receiver_arg(result[0], receiver_obj):
        result = result[1:]
    elif receiver_struct:
        receiver_types = _struct_receiver_types(receiver_struct)
        first_type = result[0].get("type", "")
        if first_type in receiver_types:
            result = result[1:]

    if receiver_obj and result and _is_obj_receiver_arg(result[-1], receiver_obj):
        result = result[:-1]
    elif receiver_struct and result:
        receiver_types = _struct_receiver_types(receiver_struct)
        last_type = result[-1].get("type", "")
        if last_type in receiver_types:
            result = result[:-1]

    return result


def merge_pp_arg(
    pp_arg: Mapping[str, Any],
    ir_arg: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    if ir_arg is None:
        return dict(pp_arg)
    if ir_arg.get("type") == "callback" and isinstance(ir_arg.get("function"), Mapping):
        merged = dict(ir_arg)
        if pp_arg.get("name"):
            merged["name"] = pp_arg["name"]
        return merged
    merged = dict(ir_arg)
    if pp_arg.get("name"):
        merged["name"] = pp_arg["name"]
    return merged


def align_args_to_pp(
    ir_args: Sequence[Mapping[str, Any]],
    pp_args: Sequence[Mapping[str, Any]],
    *,
    receiver_struct: Optional[str] = None,
    receiver_obj: Optional[str] = None,
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
        aligned.append(merge_pp_arg(pp_arg, ir_arg))
        if name:
            used.add(name)

    for ir_arg in strip_receiver_args(
        ir_args,
        receiver_struct=receiver_struct,
        receiver_obj=receiver_obj,
    ):
        name = ir_arg.get("name")
        if name and name not in used:
            aligned.append(dict(ir_arg))
    return aligned


def enrich_function_info(
    export_name: str,
    info: Mapping[str, Any],
    pp_index: Mapping[str, Dict[str, Any]],
    *,
    obj_name: Optional[str] = None,
    module_prefix: str = "lv",
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
        return merged

    if proto and proto.get("args") and obj_name is not None:
        merged["args"] = align_args_to_pp(
            merged["args"],
            proto["args"],
            receiver_obj=obj_name,
        )
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
                merged["args"] = list(candidate["args"])
                if not merged.get("return_type") and candidate.get("return_type"):
                    merged["return_type"] = candidate["return_type"]
                break
        if not merged.get("return_type") and proto and proto.get("return_type"):
            merged["return_type"] = proto["return_type"]
        return merged

    if proto and proto.get("args"):
        merged["args"] = align_args_to_pp(
            merged["args"],
            proto["args"],
            receiver_struct=struct_name,
        )
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
) -> Dict[str, Any]:
    """Fill missing function args/return types from lvgl.pp (IR/.pyi only; no C emit)."""
    for name, info in list(metadata.get("functions", {}).items()):
        if info.get("type") == "function":
            metadata["functions"][name] = enrich_function_info(
                name, info, pp_index, module_prefix=module_prefix
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
                )

    return metadata


def default_pp_path_for_metadata(metadata_path: Path) -> Optional[Path]:
    pp_path = metadata_path.resolve().parent / "lvgl.pp"
    return pp_path if pp_path.is_file() else None
