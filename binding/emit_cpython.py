"""CPython target entry: analyze → emit_c_cpython."""

from __future__ import print_function

from . import emit_c_cpython as emit_c_mod
from . import runtime
from .analyze import analyze, get_ctor, get_methods, has_ctor
from .emit_backend import prepare_target_lowering


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
    prepare_target_lowering(ctx, target="cpython", max_phase=7)
    if not getattr(ctx, "_analysis_ready", False):
        analyze()
    runtime.absorb_from(__import__("binding.analyze", fromlist=["analyze"]))
    runtime.publish(__import__("sys").modules)
    emit_c_mod.emit_c()


def run(ctx):
    from .emit_cpython_native import reset_emit_helpers

    ctx.init_patterns()
    runtime.sync_from_ctx(ctx)
    try:
        emit_cpython(ctx)
    finally:
        runtime.absorb_from(__import__("binding.analyze", fromlist=["analyze"]))
        runtime.absorb_from(emit_c_mod)
        runtime.sync_to_ctx(ctx)
        _finalize_cpython_metadata(ctx)
        reset_emit_helpers()
