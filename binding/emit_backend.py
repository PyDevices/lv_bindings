"""Shared setup for target C-lowering runs.

The individual emitters own VM-specific C output.  This module owns only the
target-neutral Python-side state needed before a lowering run begins.
"""

from __future__ import annotations

import collections
import os
from dataclasses import dataclass

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


@dataclass(frozen=True)
class FunctionReturnLowering:
    """C and metadata fragments for one exported function return value."""

    build_result: str
    build_return_value: str
    metadata_return_type: str


@dataclass(frozen=True)
class CallbackReturnLowering:
    """C fragments for one callback result through the MP compatibility API."""

    result_assignment: str
    return_value: str


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


def mp_obj_get_ull_to_bytes_source():
    """Return the VM-version-safe 64-bit integer conversion lowering.

    MicroPython 1.29 renamed ``mp_obj_int_to_bytes_impl`` and changed its
    signature.  CircuitPython continues to expose the former helper.  The
    two native emitters both retain an MP-compatible fallback path, so this
    exact lowering belongs to their shared backend contract rather than to
    either emitter's large C template.
    """
    return (
        "#if defined(CIRCUITPY)\n"
        "    mp_obj_int_to_bytes_impl(obj, big_endian, sizeof(val), (byte*)&val);\n"
        "#elif defined(MICROPY_VERSION_MAJOR) && defined(MICROPY_VERSION_MINOR) && \\\n"
        "    ((MICROPY_VERSION_MAJOR > 1) || "
        "(MICROPY_VERSION_MAJOR == 1 && MICROPY_VERSION_MINOR > 28))\n"
        "    mp_obj_int_to_bytes(obj, sizeof(val), (byte*)&val, big_endian, false, false);\n"
        "#else\n"
        "    mp_obj_int_to_bytes_impl(obj, big_endian, sizeof(val), (byte*)&val);\n"
        "#endif"
    )


def function_return_lowering(
    *,
    return_type,
    qualified_return_type,
    is_pointer,
    lv_to_mp,
    lv_mp_type,
):
    """Lower a resolved LVGL function return through the shared MP surface.

    All three targets present function results through the common ``mp_obj_t``
    compatibility surface, including CPython's native backend.  Conversion
    lookup remains emitter-owned because it may trigger recursive type
    lowering; once available, this rule owns the identical void, pointer-cast,
    and API-metadata behavior.
    """
    if return_type == "void":
        return FunctionReturnLowering("", "mp_const_none", "NoneType")
    return FunctionReturnLowering(
        "%s _res = " % qualified_return_type,
        "{type}({cast}_res)".format(
            type=lv_to_mp[return_type], cast="(void*)" if is_pointer else ""
        ),
        lv_mp_type[return_type],
    )


def callback_return_lowering(*, return_type, mp_to_lv):
    """Lower a callback result after the emitter resolves its conversion.

    Callback conversion discovery stays emitter-owned because it can recurse
    into type generation.  Once that mapping exists, all native targets use
    the same ``mp_call_function_n_kw`` result storage and conversion policy.
    """
    if return_type == "void":
        return CallbackReturnLowering("", "")
    return CallbackReturnLowering(
        "mp_obj_t callback_result = ", " %s(callback_result)" % mp_to_lv[return_type]
    )


def struct_pointer_helpers_source(
    *,
    accept_none,
    unused_qualifier,
    sanitized_struct_name,
    struct_name,
    struct_tag,
):
    """Return the common struct-pointer wrapper lowering.

    Native emitters expose LVGL structs through the same ``mp_lv_struct_t``
    representation.  The CPython compatibility fallback accepts ``None`` for
    nullable write pointers, while MicroPython/CircuitPython retain their
    historic strict conversion.  ``unused_qualifier`` preserves each VM's C
    warning policy without duplicating the conversion contract.
    """
    none_guard = "    if (self_in == mp_const_none) return NULL;\n" if accept_none else ""
    return """static inline const mp_obj_type_t *get_mp_{sanitized_struct_name}_type(void);

{unused_qualifier}static inline void* mp_write_ptr_{sanitized_struct_name}(mp_obj_t self_in)
{{
{none_guard}    mp_lv_struct_t *self = MP_OBJ_TO_PTR(cast(self_in, get_mp_{sanitized_struct_name}_type()));
    return ({struct_tag}{struct_name}*)self->data;
}}

#define mp_write_{sanitized_struct_name}(struct_obj) *(({struct_tag}{struct_name}*)mp_write_ptr_{sanitized_struct_name}(struct_obj))

{unused_qualifier}static inline mp_obj_t mp_read_ptr_{sanitized_struct_name}(void *field)
{{
    return lv_to_mp_struct(get_mp_{sanitized_struct_name}_type(), field);
}}""".format(
        none_guard=none_guard,
        unused_qualifier=unused_qualifier,
        sanitized_struct_name=sanitized_struct_name,
        struct_tag=struct_tag,
        struct_name=struct_name,
    )
