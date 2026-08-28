"""CircuitPython target entry: analyze → emit_c_micropython_style (target=circuitpython)."""

from __future__ import print_function

from . import emit_c_micropython_style as emit_c_mod
from . import runtime
from .analyze import analyze
from .emit_backend import prepare_target_lowering


def emit_circuitpython(ctx):
    """Run shared analysis and emit CircuitPython C source to ctx.emit_print."""
    prepare_target_lowering(ctx, target="circuitpython", max_phase=7)
    if not getattr(ctx, "_analysis_ready", False):
        analyze()
    runtime.absorb_from(__import__("binding.analyze", fromlist=["analyze"]))
    runtime.publish(__import__("sys").modules)
    emit_c_mod.emit_c()


def run(ctx):
    ctx.init_patterns()
    runtime.sync_from_ctx(ctx)
    try:
        emit_circuitpython(ctx)
    finally:
        runtime.absorb_from(__import__("binding.analyze", fromlist=["analyze"]))
        runtime.absorb_from(emit_c_mod)
        runtime.sync_to_ctx(ctx)
