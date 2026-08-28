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


@dataclass(frozen=True)
class TargetLoweringProfile:
    """The small, explicit set of VM constraints visible to shared lowering."""

    target: str
    supports_dynamic_function_pointer: bool


@dataclass(frozen=True)
class EnumNamespacePlan:
    """Target-neutral contents and nesting for one exported enum namespace."""

    name: str
    members: tuple[str, ...]
    nested_names: tuple[str, ...]
    widget_scoped_nested_names: tuple[str, ...]


@dataclass(frozen=True)
class ModuleRegistrationPlan:
    """Target-neutral declarations exported from the module at one phase.

    Backends use different C APIs to publish these objects, but must expose
    the same declaration set and retain declaration order.  This plan keeps
    the selection policy independent from those VM-specific C APIs.
    """

    int_constants: tuple[str, ...]
    generated_globals: tuple[str, ...]
    enum_names: tuple[str, ...]
    struct_names: tuple[str, ...]
    struct_alias_names: tuple[str, ...]
    object_names: tuple[str, ...]
    module_functions: tuple[object, ...]


_TARGET_PROFILES = {
    "micropython": TargetLoweringProfile("micropython", True),
    "circuitpython": TargetLoweringProfile("circuitpython", True),
    "cpython": TargetLoweringProfile("cpython", False),
}


def prepare_target_lowering(ctx, *, target, max_phase):
    """Set common emitter state without imposing a VM-specific C contract."""
    try:
        profile = _TARGET_PROFILES[target]
    except KeyError:
        raise ValueError("unsupported target lowering profile: %s" % target)
    runtime.set_("emit_options", {"target": target, "max_phase": max_phase})
    runtime.set_("target_lowering_profile", profile)
    for name in _EMIT_DEFAULTS:
        if name not in runtime.export_names():
            continue
        if name in ("generated_globals", "module_funcs"):
            runtime.set_(name, [])
        else:
            runtime.set_(name, collections.OrderedDict())
    if not hasattr(ctx, "headers") or ctx.headers is None:
        runtime.set_("headers", list(ctx.args.input))


def require_target_lowering(target):
    """Return the configured phase after verifying an emitter's target.

    A backend entry point selects the target before handing control to its
    native emitter.  Native emitters must not retain fallback paths for other
    backends: those paths conceal ownership mistakes and make a future
    refactor unsafe.  Keep the check next to the common lowering setup so all
    emitters can adopt the same boundary.
    """
    emit_options = runtime.get("emit_options", {})
    actual_target = emit_options.get("target")
    if actual_target != target:
        raise RuntimeError(
            "{target} emitter requires target={target!r}; got {actual!r}".format(
                target=target, actual=actual_target
            )
        )
    return emit_options.get("max_phase")


def require_one_of_target_lowerings(*targets):
    """Return configured target and phase, constrained to shared emitters.

    Some C-lowering code is intentionally shared by multiple VM backends.
    That code must still require an explicitly configured target; it may not
    quietly fall back to one target when setup is missing.
    """
    if not targets:
        raise ValueError("at least one target is required")
    emit_options = runtime.get("emit_options", {})
    actual_target = emit_options.get("target")
    if actual_target not in targets:
        expected = ", ".join(repr(target) for target in targets)
        raise RuntimeError(
            "shared emitter requires one of ({expected}); got {actual!r}".format(
                expected=expected, actual=actual_target
            )
        )
    return actual_target, emit_options.get("max_phase")


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


def enum_namespace_plan(*, enums, get_enum_members, is_method_of, is_widget_scoped):
    """Build the common enum namespace relationship plan in declaration order.

    The three targets choose different C representations for enum namespaces,
    but their public nesting and widget-scoped-reference policy is identical.
    Keeping this discovery here makes that contract explicit without imposing a
    VM-specific emitted C shape.
    """
    enum_names = tuple(enums)
    return tuple(
        EnumNamespacePlan(
            name=enum_name,
            members=tuple(get_enum_members(enum_name)),
            nested_names=tuple(
                other for other in enum_names if is_method_of(other, enum_name)
            ),
            widget_scoped_nested_names=tuple(
                other
                for other in enum_names
                if is_method_of(other, enum_name) and is_widget_scoped(other)
            ),
        )
        for enum_name in enum_names
    )


def module_registration_plan(
    *,
    max_phase,
    int_constants,
    generated_globals,
    enums,
    enum_referenced,
    generated_structs,
    struct_aliases,
    obj_names,
    module_funcs,
):
    """Select the shared public module surface for a completed phase.

    A declaration remains in its original discovery order.  Backends receive
    empty tuples for features not available in the requested phase, rather
    than each reimplementing phase gates and referenced-enum filtering.
    """
    return ModuleRegistrationPlan(
        int_constants=tuple(int_constants) if max_phase >= 1 else (),
        generated_globals=tuple(generated_globals) if max_phase >= 1 else (),
        enum_names=(
            tuple(name for name in enums if name not in enum_referenced)
            if max_phase >= 2
            else ()
        ),
        struct_names=(
            tuple(name for name, generated in generated_structs.items() if generated)
            if max_phase >= 3
            else ()
        ),
        struct_alias_names=(tuple(struct_aliases) if max_phase >= 3 else ()),
        object_names=tuple(obj_names) if max_phase >= 5 else (),
        module_functions=tuple(module_funcs) if max_phase >= 6 else (),
    )


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


def callback_return_conversion_available(*, return_type, mp_to_lv, generate_type):
    """Ensure the conversion used by a callback return is available.

    The recursive type-generation hook remains supplied by the emitter, but
    both native backends follow the same policy: ``void`` needs no conversion;
    every other missing mapping gets exactly one generation attempt before the
    caller reports its existing target-neutral diagnostic.
    """
    return return_type == "void" or conversion_available(
        conversions=mp_to_lv, type_name=return_type, generate_type=generate_type
    )


def conversion_available(*, conversions, type_name, generate_type):
    """Ensure a target-neutral conversion mapping exists, with one retry.

    Conversion maps are populated lazily because lowering a declaration may
    expose additional types.  Native backends share the same rule: use an
    existing non-empty mapping, otherwise generate once and check again.  The
    caller retains the context-specific error text and C lowering.
    """
    if conversions.get(type_name):
        return True
    generate_type()
    return bool(conversions.get(type_name))


def function_reuse_allowed(
    *,
    function_name,
    original_name,
    original_generated,
    supports_dynamic_function_pointer,
):
    """Return whether two equivalent exported functions may share a wrapper.

    A dynamic-function-pointer wrapper can safely stand in for any equivalent
    LVGL declaration. A direct-symbol wrapper, used by the native CPython
    backend, may only reuse itself: reusing it for another symbol would call
    the wrong LVGL function. This is an implementation constraint, not a
    public-API exception.
    """
    if not original_generated:
        return False
    return supports_dynamic_function_pointer or function_name == original_name


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
