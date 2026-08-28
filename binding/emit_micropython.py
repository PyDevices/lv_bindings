"""MicroPython target entry: analyze → emit_c_micropython_style."""
from __future__ import print_function

import builtins

from . import emit_c_micropython_style as emit_c_mod
from . import runtime
from .analyze import analyze
from .emit_backend import prepare_target_lowering

print = builtins.print


def run(ctx):
    ctx.init_patterns()
    runtime.sync_from_ctx(ctx)
    try:
        # The MP-style object/enum pass has a full-generation dependency that
        # is intentionally represented by an unbounded phase. CircuitPython
        # and CPython use their finite lifecycle phases below.
        prepare_target_lowering(ctx, target="micropython", max_phase=None)
        if not getattr(ctx, "_analysis_ready", False):
            analyze()
            runtime.absorb_from(__import__("binding.analyze", fromlist=["analyze"]))
        runtime.publish(__import__("sys").modules)
        emit_c_mod.emit_c()
    finally:
        runtime.absorb_from(emit_c_mod)
        runtime.sync_to_ctx(ctx)
