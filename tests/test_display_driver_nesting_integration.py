"""Consumer-integration regression test for the display_driver.py helper.

``python/display_driver.py`` is the canonical copy of the LVGL event-loop
helper this repo ships; consumer repos (lvgl-micropython, lvgl-circuitpython,
lvgl-python) vendor a synced copy verbatim. Its ``event_loop.task_handler``
and ``event_loop.async_refresh`` gate re-entrant ``lv.task_handler()`` calls
on ``lv._nesting.value``.

``_nesting`` is not an LVGL declaration -- it is a binding-internal callback
re-entrancy counter, synthesized in ``analyze.py`` and deliberately marked
private in the canonical API model (see ``api_model.build_api_model``).
Commit cc02710 ("generator: enforce canonical public API semantics")
additionally stopped emitting it as a MicroPython/CircuitPython module
global, and a follow-up commit (c9ff7ee, "generator: remove dead embedded
callback nesting state") then deleted the underlying C counter entirely,
believing it unused -- its only reader is this helper, outside the
translation unit. The combination silently broke every consumer's LVGL
event loop with ``AttributeError: module 'lvgl' has no attribute
'_nesting'``.

This test executes the real ``event_loop.task_handler`` against a mock
``lv`` built strictly from the names the freshly generated
``generated/lvgl_micropython.c`` actually exports (via
``binding.verify_namespace.mp_module_names``), so any future drift between
what the helper reads and what the generator emits -- for ``_nesting`` or
any other attribute -- fails this test instead of only surfacing as a live
AttributeError on device. It fails on the pre-fix tree: the mock built from
a pre-fix ``generated/lvgl_micropython.c`` omits ``_nesting``, so
``task_handler`` raises AttributeError, which its own broad
``except Exception`` swallows into ``exception_sink`` -- this test treats
that swallow itself as the failure, by asserting ``lv.task_handler()``
actually ran.
"""
from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

from binding.verify_namespace import mp_module_names

REPO_ROOT = Path(__file__).resolve().parents[1]
DISPLAY_DRIVER = REPO_ROOT / "python" / "display_driver.py"
MICROPYTHON_C = REPO_ROOT / "generated" / "lvgl_micropython.c"
CIRCUITPYTHON_C = REPO_ROOT / "generated" / "lvgl_circuitpython.c"


def _load_event_loop_class(lv_module):
    """Exec just the real ``event_loop`` class body against ``lv_module``.

    The full ``display_driver`` module imports the PyDevices app framework
    (appdev/events/keys/multimer) and requires a live ``appdev.App`` at
    import time -- none of which lvgl-bindings depends on or should stub
    out wholesale. That app-bootstrapping is orthogonal to the nesting-guard
    bug this test targets, so this extracts and executes only the
    ``event_loop`` class definition from the real source file, against a
    caller-supplied ``lv``.
    """
    source = DISPLAY_DRIVER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DISPLAY_DRIVER))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "event_loop"
    )
    class_source = ast.get_source_segment(source, class_node)
    assert class_source, "could not extract the event_loop class source"

    namespace = {
        "lv": lv_module,
        "sys": sys,
        "asyncio_available": False,
        "asyncio": None,
        "ticks_ms": None,
        "ticks_add": None,
        "ticks_diff": None,
        "app": None,
        "LVGL_PERIOD_MS": 10,
    }
    exec(compile(class_source, str(DISPLAY_DRIVER), "exec"), namespace)
    return namespace["event_loop"]


class _NestingCounter:
    """Stands in for the compiled ``mp__nesting`` blob wrapper's shape."""

    value = 0


def _mock_lv_from_compiled_namespace(generated_c_text):
    """Build an ``lv`` stand-in exposing exactly the names the freshly
    generated bindings emit for this target -- nothing invented.
    """
    names = mp_module_names(generated_c_text)
    mock = types.SimpleNamespace()
    for name in names:
        setattr(mock, name, lambda *a, **kw: None)
    if "_nesting" in names:
        mock._nesting = _NestingCounter()
    mock.is_initialized = lambda: True
    mock.init = lambda: None
    calls = {"task_handler": 0}

    def task_handler():
        calls["task_handler"] += 1

    mock.task_handler = task_handler
    return mock, names, calls


def test_micropython_globals_expose_nesting_counter():
    names = mp_module_names(MICROPYTHON_C.read_text(encoding="utf-8"))
    assert "_nesting" in names, (
        "generated/lvgl_micropython.c no longer exports _nesting; "
        "python/display_driver.py reads lv._nesting.value at runtime "
        "(see event_loop.task_handler / event_loop.async_refresh)"
    )


def test_circuitpython_globals_expose_nesting_counter():
    names = mp_module_names(CIRCUITPYTHON_C.read_text(encoding="utf-8"))
    assert "_nesting" in names, (
        "generated/lvgl_circuitpython.c no longer exports _nesting; "
        "python/display_driver.py reads lv._nesting.value at runtime "
        "(see event_loop.task_handler / event_loop.async_refresh)"
    )


def test_task_handler_nesting_guard_runs_against_compiled_micropython_globals():
    mock_lv, names, calls = _mock_lv_from_compiled_namespace(
        MICROPYTHON_C.read_text(encoding="utf-8")
    )

    event_loop = _load_event_loop_class(mock_lv)
    loop = event_loop(period_ms=10)
    # __init__ starts paused (self._pause = 1) until an App-driven enable();
    # we're calling task_handler() directly, so unpause it here instead.
    loop._pause = 0

    errors = []
    loop.exception_sink = errors.append

    loop.task_handler()

    assert not errors, (
        "task_handler() swallowed an exception instead of running "
        "lv.task_handler(): %r" % (errors,)
    )
    assert calls["task_handler"] == 1, (
        "lv.task_handler() never ran; the lv._nesting.value re-entrancy "
        "guard likely raised AttributeError and task_handler's own "
        "except-Exception swallowed it into exception_sink"
    )
