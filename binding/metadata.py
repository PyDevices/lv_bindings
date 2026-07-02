"""Serialize generation namespace to lvgl.json and IR alignment helpers."""

import collections
import json

from .helpers import sanitize
from .model import GenerationResult


def _struct_functions_metadata(namespace):
    from .analyze import get_struct_functions, noncommon_part

    from . import runtime

    runtime.sync_from_namespace(namespace)
    metadata = collections.OrderedDict()
    for struct_name, generated in namespace["generated_structs"].items():
        if not generated:
            continue
        struct_funcs = get_struct_functions(struct_name)
        if not struct_funcs:
            continue
        members = collections.OrderedDict()
        for func in struct_funcs:
            if func.name not in namespace["func_metadata"]:
                continue
            member_name = sanitize(noncommon_part(func.name, struct_name))
            members[member_name] = namespace["func_metadata"][func.name]
        if members:
            metadata[namespace["simplify_identifier"](struct_name)] = members
    return metadata


def align_namespace_to_ir(namespace, ir_path):
    """Restrict CPython metadata exports to the shared MP-shaped IR."""
    with open(ir_path, "r") as ir_file:
        ir = json.load(ir_file)
    simplify_identifier = namespace["simplify_identifier"]
    export_ids = set(ir.get("functions", {}))
    namespace["module_funcs"] = [
        func
        for func in namespace["module_funcs"]
        if simplify_identifier(func.name) in export_ids
    ]
    ir_structs = set(ir.get("structs", []))
    generated_structs = namespace.get("generated_structs", {})
    struct_aliases = namespace.get("struct_aliases", {})
    raw_structs = namespace.get("structs", {})
    alias_by_simplified = {
        simplify_identifier(alias): struct_name
        for struct_name, alias in struct_aliases.items()
    }
    for struct_name in list(generated_structs.keys()):
        simplified = simplify_identifier(struct_name)
        alias_name = simplify_identifier(struct_aliases.get(struct_name, struct_name))
        if simplified in ir_structs or alias_name in ir_structs:
            generated_structs[struct_name] = True
    for ir_name in ir_structs:
        if ir_name in alias_by_simplified:
            generated_structs[alias_by_simplified[ir_name]] = True
            continue
        for struct_name in list(raw_structs.keys()) + list(generated_structs.keys()):
            if simplify_identifier(struct_name) == ir_name:
                generated_structs[struct_name] = True
                break
    namespace["generated_structs"] = generated_structs
    namespace["_ir_struct_list"] = sorted(ir_structs)


def save_metadata(namespace, path):
    simplify_identifier = namespace["simplify_identifier"]
    get_enum_name = namespace["get_enum_name"]

    metadata = _build_metadata(namespace, simplify_identifier, get_enum_name)

    with open(path, "w") as metadata_file:
        json.dump(metadata, metadata_file, indent=4)


def _build_metadata(namespace, simplify_identifier, get_enum_name):
    metadata = collections.OrderedDict()
    metadata["objects"] = {
        obj_name: namespace["obj_metadata"].get(
            obj_name, {"members": collections.OrderedDict()}
        )
        for obj_name in namespace["obj_names"]
    }
    metadata["functions"] = {
        simplify_identifier(f.name): namespace["func_metadata"][f.name]
        for f in namespace["module_funcs"]
    }
    metadata["enums"] = {
        get_enum_name(enum_name): namespace["obj_metadata"].get(
            enum_name, {"members": collections.OrderedDict()}
        )
        for enum_name in namespace["enums"].keys()
        if enum_name not in namespace["enum_referenced"]
    }
    metadata["structs"] = list(namespace["_ir_struct_list"]) if "_ir_struct_list" in namespace else [
        simplify_identifier(struct_name)
        for struct_name in namespace["generated_structs"]
        if namespace["generated_structs"][struct_name]
    ]
    if "_ir_struct_list" not in namespace:
        metadata["structs"] += [
            simplify_identifier(namespace["struct_aliases"][struct_name])
            for struct_name in namespace["struct_aliases"].keys()
        ]
    metadata["struct_functions"] = _struct_functions_metadata(namespace)
    metadata["blobs"] = [
        simplify_identifier(global_name)
        for global_name in namespace["generated_globals"]
    ]
    metadata["int_constants"] = [
        get_enum_name(int_constant) for int_constant in namespace["int_constants"]
    ]
    return metadata


def save_bindings_ir(namespace, path):
    """Write canonical MP-shaped IR (lvgl.json schema)."""
    save_metadata(namespace, path)


def build_result(ctx):
    return GenerationResult(
        module_name=ctx.module_name,
        module_prefix=ctx.module_prefix,
        obj_names=ctx.obj_names,
        obj_metadata=ctx.obj_metadata,
        func_metadata=ctx.func_metadata,
        module_funcs=ctx.module_funcs,
        enums=ctx.enums,
        enum_referenced=ctx.enum_referenced,
        generated_structs=ctx.generated_structs,
        struct_aliases=ctx.struct_aliases,
        generated_globals=ctx.generated_globals,
        int_constants=ctx.int_constants,
        headers=getattr(ctx, "headers", []),
        pp_cmd=ctx.pp_cmd,
        cmd_line=ctx.cmd_line,
    )
