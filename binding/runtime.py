"""Global mirror for one generation run; analyze/emit modules use get/set_."""
from __future__ import print_function

from contextvars import ContextVar

from .context import BindingContext


_ACTIVE_CONTEXT = ContextVar("lvgl_binding_context", default=None)


def current_context():
    """Return the context for the active generation run."""
    ctx = _ACTIVE_CONTEXT.get()
    if ctx is None:
        raise RuntimeError("no active binding generation context")
    return ctx

# Modules that mirror binding globals during generation.
_CONSUMER_MODULES = (
    "binding.emit_c_micropython_style",
    "binding.emit_c_cpython",
)


def export_names():
    return BindingContext.EXPORT_NAMES


def set_(name, value):
    """Assign a binding global and mirror it to consumer modules."""
    globals()[name] = value
    import sys

    publish(sys.modules, names=(name,))


def sync_from_ctx(ctx):
    """Load context inputs into runtime and publish to consumer modules."""
    import sys

    _ACTIVE_CONTEXT.set(ctx)
    for name in ctx.export_names():
        if hasattr(ctx, name):
            globals()[name] = getattr(ctx, name)
    globals()["print"] = ctx.emit_print
    publish(sys.modules)


def sync_from_namespace(namespace):
    """Load a generation namespace dict into runtime (for metadata helpers)."""
    for name in export_names():
        if name in namespace:
            globals()[name] = namespace[name]


def absorb_from(module):
    """Pull binding globals from a consumer module into runtime."""
    for name in export_names():
        if hasattr(module, name):
            globals()[name] = getattr(module, name)
    if hasattr(module, "print"):
        globals()["print"] = module.print


def sync_to_ctx(ctx):
    """Write runtime state back to the binding context."""
    for name in ctx.export_names():
        if name in globals():
            setattr(ctx, name, globals()[name])


def reset():
    """Clear mirrored generation state before starting an in-process run."""
    import sys

    from .util import clear_memoized

    clear_memoized()

    for name in export_names():
        globals().pop(name, None)
    globals().pop("print", None)
    for mod_name in _CONSUMER_MODULES:
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        for name in export_names():
            mod.__dict__.pop(name, None)
        mod.__dict__.pop("print", None)


def publish(modules, names=None):
    """Copy runtime globals into consumer modules."""
    if names is None:
        names = export_names()
    for mod_name in _CONSUMER_MODULES:
        mod = modules.get(mod_name)
        if mod is None:
            continue
        for name in names:
            if name in globals():
                setattr(mod, name, globals()[name])
        if "print" in globals():
            mod.print = globals()["print"]


_MISSING = object()


def get(name, default=_MISSING):
    """Return a binding global from runtime."""
    if name in globals():
        return globals()[name]
    if default is not _MISSING:
        return default
    raise NameError(name)


def emit(*args, **kwargs):
    """Write generated output through the active binding context explicitly."""
    return get("print")(*args, **kwargs)


class _Namespace(object):
    """Attribute access to binding globals (read/write through runtime)."""

    def __getattr__(self, name):
        try:
            return get(name)
        except NameError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        set_(name, value)


ns = _Namespace()
