"""Target run() bridges from cli to emit_* orchestrators and metadata export."""

from __future__ import print_function

import copy

from .context import BindingContext
from .emit_micropython import run as emit_run_micropython
from .metadata import build_result


_ANALYSIS_STATE_NAMES = (
    "obj_metadata",
    "func_metadata",
    "callback_metadata",
    "func_prototypes",
    "parser",
    "gen",
    "parsed_ast",
    "ast",
    "declaration_ir",
    "declaration_index",
    "lvgl_json",
    "forward_struct_decls",
    "typedefs",
    "synonym",
    "struct_typedefs",
    "structs_without_typedef",
    "structs",
    "explicit_structs",
    "opaque_structs",
    "func_defs",
    "func_decls",
    "all_funcs",
    "funcs",
    "obj_ctors",
    "obj_names",
    "parent_obj_names",
    "enum_defs",
    "func_typedefs",
    "blobs",
    "int_constants",
    "mp_to_lv",
    "lv_to_mp",
    "lv_mp_type",
    "lv_to_mp_byref",
    "lv_to_mp_funcptr",
)


def prepare_analysis(args, source, pp_cmd, cmd_line, emit_print):
    """Parse and analyze one translation unit for reuse by every target."""
    from pycparser import c_generator, c_parser

    from . import runtime
    from .analyze import analyze

    runtime.reset()
    ctx = BindingContext(args, source, pp_cmd, cmd_line, emit_print)
    ctx.init_patterns()
    ctx.parser = c_parser.CParser()
    ctx.gen = c_generator.CGenerator()
    ctx.parsed_ast = ctx.parser.parse(source, filename="<none>")
    runtime.sync_from_ctx(ctx)
    analyze()
    runtime.absorb_from(__import__("binding.analyze", fromlist=["analyze"]))
    runtime.sync_to_ctx(ctx)
    ctx.declaration_ir = runtime.get("declaration_ir")
    runtime.publish(__import__("sys").modules)
    runtime.sync_to_ctx(ctx)
    return ctx


def analysis_snapshot(ctx):
    """Return an isolated, internally consistent copy of analysis state."""
    values = {
        name: getattr(ctx, name)
        for name in _ANALYSIS_STATE_NAMES
        if hasattr(ctx, name)
    }
    snapshot = copy.deepcopy(values)
    # DeclarationIR is frozen and target-neutral.  Preserve the same object so
    # every backend receives the exact canonical declaration set, not a copy.
    if hasattr(ctx, "declaration_ir"):
        snapshot["declaration_ir"] = ctx.declaration_ir
    return snapshot


def _new_context(args, source, pp_cmd, cmd_line, emit_print, analysis_state=None):
    from .util import clear_memoized

    clear_memoized()
    ctx = BindingContext(args, source, pp_cmd, cmd_line, emit_print)
    ctx.init_patterns()
    if analysis_state is not None:
        values = copy.deepcopy(analysis_state)
        if "declaration_ir" in analysis_state:
            values["declaration_ir"] = analysis_state["declaration_ir"]
        for name, value in values.items():
            setattr(ctx, name, value)
        ctx._analysis_ready = True
    return ctx


def run_micropython(args, source, pp_cmd, out, cmd_line, analysis_state=None):
    import builtins

    def emit_print(*a, **k):
        k.setdefault("file", out)
        builtins.print(*a, **k)

    ctx = _new_context(
        args, source, pp_cmd, cmd_line, emit_print, analysis_state=analysis_state
    )
    emit_run_micropython(ctx)
    from . import helpers

    namespace = {name: getattr(ctx, name) for name in ctx.export_names()}
    namespace["simplify_identifier"] = helpers.simplify_identifier
    namespace["get_enum_name"] = helpers.get_enum_name
    return build_result(ctx), namespace


def run_circuitpython(args, source, pp_cmd, out, cmd_line, analysis_state=None):
    import builtins

    from .emit_circuitpython import run as emit_run_cp

    def emit_print(*a, **k):
        k.setdefault("file", out)
        builtins.print(*a, **k)

    ctx = _new_context(
        args, source, pp_cmd, cmd_line, emit_print, analysis_state=analysis_state
    )
    emit_run_cp(ctx)
    emitted = True
    from . import helpers

    namespace = {}
    for name in ctx.export_names():
        if hasattr(ctx, name):
            namespace[name] = getattr(ctx, name)
    namespace["simplify_identifier"] = helpers.simplify_identifier
    namespace["get_enum_name"] = helpers.get_enum_name
    return build_result(ctx), namespace, emitted


def run_cpython(args, source, pp_cmd, out, cmd_line, analysis_state=None):
    import builtins

    from .emit_cpython import run as emit_run_cpython

    def emit_print(*a, **k):
        k.setdefault("file", out)
        builtins.print(*a, **k)

    ctx = _new_context(
        args, source, pp_cmd, cmd_line, emit_print, analysis_state=analysis_state
    )
    emit_run_cpython(ctx)
    emitted = True
    from . import helpers

    namespace = {}
    for name in ctx.export_names():
        if hasattr(ctx, name):
            namespace[name] = getattr(ctx, name)
    namespace["simplify_identifier"] = helpers.simplify_identifier
    namespace["get_enum_name"] = helpers.get_enum_name
    return build_result(ctx), namespace, emitted
