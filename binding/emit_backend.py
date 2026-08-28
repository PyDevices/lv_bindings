"""Shared setup for target C-lowering runs.

The individual emitters own VM-specific C output.  This module owns only the
target-neutral Python-side state needed before a lowering run begins.
"""

from __future__ import annotations

import collections
import os

from . import runtime


_EMIT_DEFAULTS = (
    "generated_struct_functions",
    "struct_aliases",
    "callbacks_used_on_structs",
    "generated_callbacks",
    "generated_funcs",
    "enum_referenced",
    "generated_obj_names",
    "generated_globals",
    "module_funcs",
    "functions_not_generated",
)


def prepare_target_lowering(ctx, *, target, max_phase):
    """Set common emitter state without imposing a VM-specific C contract."""
    runtime.set_("emit_options", {"target": target, "max_phase": max_phase})
    for name in _EMIT_DEFAULTS:
        if name not in runtime.export_names():
            continue
        if name in ("generated_globals", "module_funcs"):
            runtime.set_(name, [])
        else:
            runtime.set_(name, collections.OrderedDict())
    if not hasattr(ctx, "headers") or ctx.headers is None:
        runtime.set_("headers", list(ctx.args.input))


def resolve_emitter_headers(inputs):
    """Return the public headers plus LVGL's private declarations.

    Every backend lowers against the same declaration surface.  LVGL's public
    umbrella header deliberately omits a few declarations used by generated
    wrappers, so each native emitter must add the paired private header.
    """
    headers = list(inputs)
    for header in headers:
        if "lvgl.h" not in header:
            continue
        path, _ = os.path.split(header)
        headers.append(
            os.path.join(path, "src", "lvgl_private.h")
            if path and path != "lvgl.h"
            else "src/lvgl_private.h"
        )
        break
    return headers


def target_banner(target, *, include):
    """Return the optional target marker for a generated-file banner."""
    return " *\n * Target: {target}\n".format(target=target) if include else ""
