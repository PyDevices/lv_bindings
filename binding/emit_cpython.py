"""CPython target entry: analyze → emit_c_micropython_style dispatch → emit_c_cpython."""

from __future__ import print_function

import collections

from . import emit_c_micropython_style as emit_c_mod
from . import runtime
from .analyze import analyze, get_ctor, get_methods, has_ctor


def _init_emit_defaults(ctx):
    defaults = {
        "generated_struct_functions": collections.OrderedDict(),
        "struct_aliases": collections.OrderedDict(),
        "callbacks_used_on_structs": collections.OrderedDict(),
        "generated_callbacks": collections.OrderedDict(),
        "generated_funcs": collections.OrderedDict(),
        "enum_referenced": collections.OrderedDict(),
        "generated_obj_names": collections.OrderedDict(),
        "generated_globals": [],
        "module_funcs": [],
        "functions_not_generated": collections.OrderedDict(),
        "cpython_struct_sizes": collections.OrderedDict(),
    }
    for name, value in defaults.items():
        if name not in runtime.export_names():
            continue
        runtime.set_(name, value)
    if not hasattr(ctx, "headers") or ctx.headers is None:
        runtime.set_("headers", list(ctx.args.input))


def _finalize_cpython_metadata(ctx):
    """Align module_funcs / struct metadata with MP-shaped exports for IR parity."""
    exports = runtime.get("_cpython_module_exports")
    if exports:
        ctx.module_funcs = list(exports)
    else:
        funcs = getattr(ctx, "funcs", [])
        obj_names = getattr(ctx, "obj_names", [])
        method_names = set()
        for obj_name in obj_names:
            for method in get_methods(obj_name):
                method_names.add(method.name)
            if has_ctor(obj_name):
                method_names.add(get_ctor(obj_name).name)
        ctx.module_funcs = [func for func in funcs if func.name not in method_names]

    rt_structs = runtime.get("generated_structs", {})
    if rt_structs:
        ctx.generated_structs = rt_structs
    rt_aliases = runtime.get("struct_aliases", {})
    if rt_aliases:
        ctx.struct_aliases = rt_aliases


def emit_cpython(ctx):
    runtime.set_(
        "emit_options",
        {"target": "cpython", "max_phase": 7},
    )
    analyze()
    _init_emit_defaults(ctx)
    runtime.absorb_from(__import__("binding.analyze", fromlist=["analyze"]))
    runtime.publish(__import__("sys").modules)
    emit_c_mod.emit_c()


def run(ctx):
    ctx.init_patterns()
    runtime.sync_from_ctx(ctx)
    try:
        emit_cpython(ctx)
    finally:
        runtime.absorb_from(__import__("binding.analyze", fromlist=["analyze"]))
        runtime.absorb_from(emit_c_mod)
        from . import emit_c_cpython as emit_c_cpython_mod

        runtime.absorb_from(emit_c_cpython_mod)
        runtime.sync_to_ctx(ctx)
        _finalize_cpython_metadata(ctx)
