#!/usr/bin/env python3
"""Unified LVGL binding smoke tests for MicroPython, CircuitPython, and CPython.

Run with the target interpreter after building that port, for example:

  # MicroPython unix
  ./micropython/ports/unix/build-standard/micropython \\
    ./lv_bindings/test_lvgl_smoke.py

  # CircuitPython unix
  ./circuitpython/ports/unix/build-coverage/micropython \\
    ./lv_bindings/test_lvgl_smoke.py

  # CPython (WSL venv)
  ./lv_cpython_mod/.venv/bin/python ./lv_bindings/test_lvgl_smoke.py

Exercises init/deinit, headless display, widgets, event callbacks, GC visibility,
and CPython-specific struct/Blob helpers where applicable.
"""
import gc
import sys


def _fail(msg):
    print("FAIL: {}".format(msg), file=sys.stderr)
    raise SystemExit(1)


def _warn(msg):
    print("WARN: {}".format(msg), file=sys.stderr)


def _pascal_case(name):
    return "".join(part.capitalize() for part in name.split("_") if part)


def _naming_style_from_env():
    """Read LV_NAMING_STYLE when the port exposes getenv or environ."""
    try:
        import os
    except ImportError:
        return ""
    getenv = getattr(os, "getenv", None)
    if getenv is not None:
        val = getenv("LV_NAMING_STYLE")
        if val:
            return val.lower()
    environ = getattr(os, "environ", None)
    if environ is not None:
        return environ.get("LV_NAMING_STYLE", "").lower()
    return ""


def _use_pythonic_naming(lv=None):
    if _naming_style_from_env() == "pythonic":
        return True
    if lv is not None:
        button = getattr(lv, "Button", None)
        legacy = getattr(lv, "button", None)
        if button is not None and legacy is None:
            return True
    return False


def _lv_export(lv, name):
    """Resolve a module-level export (legacy snake_case or pythonic PascalCase)."""
    if _use_pythonic_naming(lv):
        pascal = _pascal_case(name)
        value = getattr(lv, pascal, None)
        if value is not None:
            return value
    return getattr(lv, name, None)


def _widget_type(lv, name):
    return _lv_export(lv, name)


def _widget_attr(obj, name):
    if _use_pythonic_naming():
        pascal = _pascal_case(name)
        if hasattr(obj, pascal):
            return getattr(obj, pascal)
    return getattr(obj, name)


def _is_cpython():
    impl = getattr(sys, "implementation", None)
    return impl is not None and impl.name == "cpython"


def _prepare_import_path():
    """Avoid lv_bindings/lvgl submodule shadowing the compiled CPython extension."""
    if not _is_cpython():
        return
    import os.path as ospath

    here = ospath.dirname(ospath.abspath(__file__))
    lvgl_sub = ospath.join(here, "lvgl")
    if ospath.isdir(lvgl_sub):
        norm = ospath.normpath
        sys.path[:] = [p for p in sys.path if norm(p) != norm(here)]
    cpy_mod = ospath.join(ospath.dirname(here), "lv_cpython_mod")
    if ospath.isdir(cpy_mod) and cpy_mod not in sys.path:
        sys.path.insert(0, cpy_mod)


def _import_lv():
    _prepare_import_path()
    import lvgl as lv  # noqa: WPS433 — runtime import under test

    return lv


def _is_initialized(lv):
    if hasattr(lv, "is_initialized"):
        return lv.is_initialized()
    return False


def _setup_display(lv, width=240, height=240):
    """Minimal headless display so screen_active() and widgets behave like embedded."""

    def flush_cb(disp, area, color_p):
        disp.flush_ready()

    disp = lv.display_create(width, height)
    disp.set_flush_cb(flush_cb)

    if hasattr(disp, "set_color_format"):
        disp.set_color_format(_lv_export(lv, "COLOR_FORMAT").RGB565)
    elif hasattr(lv, "display_set_color_format"):
        lv.display_set_color_format(disp, _lv_export(lv, "COLOR_FORMAT").RGB565)

    buf = lv.draw_buf_create(width, height, _lv_export(lv, "COLOR_FORMAT").RGB565, 0)

    if hasattr(disp, "set_draw_buffers"):
        disp.set_draw_buffers(buf, None)
    elif hasattr(lv, "display_set_draw_buffers"):
        lv.display_set_draw_buffers(disp, buf, None)

    if hasattr(disp, "set_render_mode"):
        disp.set_render_mode(_lv_export(lv, "DISPLAY_RENDER_MODE").PARTIAL)
    elif hasattr(lv, "display_set_render_mode"):
        lv.display_set_render_mode(disp, _lv_export(lv, "DISPLAY_RENDER_MODE").PARTIAL)

    return disp, buf


def _teardown_display(buf):
    if buf is not None and hasattr(buf, "destroy"):
        buf.destroy()


def test_import_and_constants(lv):
    if not _is_cpython():
        return
    if not hasattr(lv, "init") or not hasattr(lv, "deinit"):
        _fail("lvgl module missing init/deinit")
    print("OK: import lvgl; init/deinit")


def test_basic(lv):
    lv.init()
    if hasattr(lv, "is_initialized") and not lv.is_initialized():
        _fail("lv.init() did not initialize LVGL")
    assert hasattr(lv, "deinit")
    assert _widget_type(lv, "label") is not None or _widget_type(lv, "obj") is not None
    event = _lv_export(lv, "EVENT")
    assert event is not None and hasattr(event, "CLICKED")
    print("OK: import lvgl; lv.init(); core symbols present")


def test_string_constants(lv):
    symbol = _lv_export(lv, "SYMBOL")
    if symbol is None:
        return
    for name in ("OK", "CLOSE", "HOME"):
        if not hasattr(symbol, name):
            _fail("missing lv.SYMBOL.{}".format(name))
    print("OK: LVGL SYMBOL namespace (lv.SYMBOL.OK, …)")


def test_enums(lv):
    if not _is_cpython():
        return
    event = _lv_export(lv, "EVENT")
    clicked = event.CLICKED
    if not isinstance(clicked, int) or clicked <= 0:
        _fail("lv.EVENT.CLICKED unexpected value: {!r}".format(clicked))
    obj_type = _widget_type(lv, "obj")
    flag = _widget_attr(obj_type, "FLAG")
    if flag is None or not hasattr(flag, "SCROLLABLE"):
        _fail("lv.obj missing FLAG enum namespace")
    if flag.SCROLLABLE != (1 << 4):
        _fail("lv.obj.FLAG.SCROLLABLE unexpected value")
    module_flag = _lv_export(lv, "OBJ_FLAG")
    if module_flag is None or not hasattr(module_flag, "SCROLLABLE"):
        _fail("lv.OBJ_FLAG missing at module level")
    if module_flag.SCROLLABLE != flag.SCROLLABLE:
        _fail("lv.OBJ_FLAG.SCROLLABLE must match lv.obj.FLAG.SCROLLABLE")
    label_type = _widget_type(lv, "label")
    if _widget_attr(label_type, "LONG_MODE") is None:
        _fail("lv.label missing LONG_MODE enum namespace")
    if _lv_export(lv, "LABEL_LONG_MODE") is not None:
        _fail("lv.LABEL_LONG_MODE must not be exposed at module level")
    print("OK: enum namespaces (lv.EVENT, lv.OBJ_FLAG, lv.obj.FLAG, lv.label.LONG_MODE)")


def test_module_types(lv):
    if not _is_cpython():
        return
    for name in ("C_Pointer", "Blob", "Struct", "LvReferenceError"):
        if not hasattr(lv, name):
            _fail("missing module export lv.{}".format(name))
    print("OK: module types (C_Pointer, Blob, Struct, LvReferenceError)")


def test_struct_helpers(lv):
    if not _is_cpython():
        return
    color_t = _lv_export(lv, "color_t")
    size = color_t.__SIZE__
    if not isinstance(size, int) or size <= 0:
        _fail("lv.color_t.__SIZE__ missing or invalid")
    for name in ("__cast__", "__dereference__", "__cast_instance__"):
        if not hasattr(color_t, name):
            _fail("lv.color_t missing helper {}".format(name))
    print("OK: struct helpers (__SIZE__, __cast__, …)")


def test_widget_types(lv):
    for name in ("obj", "label", "button"):
        if _widget_type(lv, name) is None:
            _fail("missing widget type lv.{}".format(name))
    print("OK: widget types registered (lv.obj, lv.label, …)")


def test_module_functions(lv):
    for name in ("display_create", "screen_active", "tick_inc"):
        if not hasattr(lv, name):
            _fail("missing module function lv.{}".format(name))
    if _is_cpython() and not hasattr(lv, "refr_now"):
        _fail("missing module function lv.refr_now")
    print("OK: module functions (display_create, screen_active, …)")


def test_refr_now(lv, disp=None):
    if not _is_cpython() or not hasattr(lv, "refr_now"):
        return
    own_disp = False
    own_buf = None
    if disp is None:
        disp = lv.display_create(80, 80)
        own_buf = lv.draw_buf_create(80, 8, _lv_export(lv, "COLOR_FORMAT").RGB565, 0)
        if hasattr(lv, "display_set_draw_buffers"):
            lv.display_set_draw_buffers(disp, own_buf, None)
        else:
            disp.set_draw_buffers(own_buf, None)
        if hasattr(lv, "display_set_render_mode"):
            lv.display_set_render_mode(disp, _lv_export(lv, "DISPLAY_RENDER_MODE").PARTIAL)
        else:
            disp.set_render_mode(_lv_export(lv, "DISPLAY_RENDER_MODE").PARTIAL)
        disp.set_flush_cb(lambda d, area, color_p: d.flush_ready())
        own_disp = True
    before = lv.display_get_default()
    lv.refr_now(disp)
    after = lv.display_get_default()
    if before is None or after is None:
        _fail("display_get_default() returned None around refr_now")
    if lv.screen_active() is None:
        _fail("screen_active() returned None after refr_now")
    if own_disp:
        _teardown_display(own_buf)
        if hasattr(disp, "delete"):
            disp.delete()
        elif hasattr(lv, "display_delete"):
            lv.display_delete(disp)
    print("OK: refr_now refreshes without deleting the display")


def test_widget(lv):
    scr = lv.screen_active()
    label = _widget_type(lv, "label")(scr)
    label.set_text("cmods smoke")
    if label.get_text() != "cmods smoke":
        _fail("label text mismatch: {!r}".format(label.get_text()))
    print("OK: label create/set_text on active screen")


def test_event_callback(lv):
    scr = lv.screen_active()
    fired = []

    def on_clicked(event):
        fired.append(event.get_code())

    scr.add_event_cb(on_clicked, _lv_export(lv, "EVENT").CLICKED, None)
    scr.send_event(_lv_export(lv, "EVENT").CLICKED, None)
    if not fired:
        _fail("screen CLICKED callback did not run")
    print("OK: add_event_cb + send_event")


def test_callback_gc_with_widget_ref(lv):
    scr = lv.screen_active()
    fired = []

    def handler(event):
        fired.append(1)

    scr.add_event_cb(handler, _lv_export(lv, "EVENT").CLICKED, None)
    del handler
    gc.collect()
    scr.send_event(_lv_export(lv, "EVENT").CLICKED, None)
    if fired:
        print("OK: callback survived gc.collect() while widget referenced")
    else:
        _warn(
            "callback was collected after del handler (widget still referenced); "
            "see docs/lvgl/gc_callback_audit.md"
        )


def test_button_callback(lv):
    scr = lv.screen_active()
    fired = []

    def on_click(event):
        if event.get_code() == _lv_export(lv, "EVENT").CLICKED:
            fired.append(1)

    btn = _widget_type(lv, "button")(scr)
    btn.set_size(80, 40)
    btn.add_event_cb(on_click, _lv_export(lv, "EVENT").CLICKED, None)
    btn.send_event(_lv_export(lv, "EVENT").CLICKED, None)
    if not fired:
        _fail("button CLICKED callback did not run")
    print("OK: button event callback")


def test_callback_gc_without_widget_ref(lv):
    scr = lv.screen_active()
    fired = []

    def on_click(event):
        if event.get_code() == _lv_export(lv, "EVENT").CLICKED:
            fired.append(1)

    btn = _widget_type(lv, "button")(scr)
    btn.add_event_cb(on_click, _lv_export(lv, "EVENT").CLICKED, None)
    del on_click
    btn_idx = scr.get_child_count() - 1
    del btn
    gc.collect()

    child = scr.get_child(btn_idx)
    child.send_event(_lv_export(lv, "EVENT").CLICKED, None)
    if fired:
        print("OK: callback survived gc with no Python ref to widget (reached via get_child)")
    else:
        _warn(
            "callback lost after del widget + gc.collect(); "
            "LVGL user_data may not keep callbacks rooted — see docs/lvgl/gc_callback_audit.md"
        )


def test_multi_callbacks(lv):
    if not _is_cpython():
        return
    scr = lv.screen_active()
    btn = _widget_type(lv, "button")(scr)
    btn.set_size(80, 40)
    fired = []

    def mk(name):
        def cb(event):
            fired.append((name, event.get_code()))

        return cb

    event = _lv_export(lv, "EVENT")
    for name, code in (
        ("PRESSED", event.PRESSED),
        ("RELEASED", event.RELEASED),
        ("CLICKED", event.CLICKED),
    ):
        btn.add_event_cb(mk(name), code, None)

    btn.send_event(event.PRESSED, None)
    btn.send_event(event.CLICKED, None)
    btn.send_event(event.RELEASED, None)

    expected = [
        ("PRESSED", event.PRESSED),
        ("CLICKED", event.CLICKED),
        ("RELEASED", event.RELEASED),
    ]
    if fired != expected:
        _fail("multi-callback dispatch mismatch: got {!r}, expected {!r}".format(fired, expected))
    print("OK: multiple filtered callbacks on one object")


def test_blob_dereference(lv, main_disp=None):
    if not _is_cpython() or not hasattr(lv, "Blob"):
        return
    disp = lv.display_create(16, 16)
    own_buf = lv.draw_buf_create(16, 4, _lv_export(lv, "COLOR_FORMAT").RGB565, 0)
    if hasattr(lv, "display_set_draw_buffers"):
        lv.display_set_draw_buffers(disp, own_buf, None)
    else:
        disp.set_draw_buffers(own_buf, None)
    seen = []

    def flush_cb(d, area, color_p):
        width = area.x2 - area.x1 + 1
        height = area.y2 - area.y1 + 1
        data = color_p.__dereference__(width * height * 2)
        seen.append(len(data))
        d.flush_ready()

    disp.set_flush_cb(flush_cb)
    lv.refr_now(disp)
    if not seen:
        _fail("flush callback did not run during refr_now")
    if main_disp is not None:
        if hasattr(lv, "display_set_default"):
            lv.display_set_default(main_disp)
        elif hasattr(main_disp, "set_default"):
            main_disp.set_default()
    _teardown_display(own_buf)
    if hasattr(disp, "delete"):
        disp.delete()
    elif hasattr(lv, "display_delete"):
        lv.display_delete(disp)
    print("OK: Blob.__dereference__ in flush callback")


def test_remove_style_none(lv):
    part = _lv_export(lv, "PART")
    if not _is_cpython() or part is None:
        return
    scr = lv.screen_active()
    arc = _widget_type(lv, "arc")(scr)
    arc.set_size(40, 40)
    arc.remove_style(None, part.KNOB)
    print("OK: arc.remove_style(None, PART.KNOB)")


def test_nesting(lv):
    if not hasattr(lv, "_nesting"):
        return
    if not hasattr(lv._nesting, "value"):
        _warn("lv._nesting missing value attribute")
    print("OK: lv._nesting present")


def main():
    lv = _import_lv()

    if _is_cpython():
        test_import_and_constants(lv)
        test_string_constants(lv)
        test_enums(lv)
        test_module_types(lv)
        test_struct_helpers(lv)
        test_widget_types(lv)
        test_module_functions(lv)
        test_nesting(lv)
    else:
        test_widget_types(lv)
        test_module_functions(lv)

    if _is_initialized(lv):
        lv.deinit()

    test_basic(lv)
    disp, buf = _setup_display(lv)
    try:
        if _is_cpython():
            test_refr_now(lv, disp)
            test_blob_dereference(lv, disp)
        test_widget(lv)
        test_event_callback(lv)
        test_callback_gc_with_widget_ref(lv)
        test_callback_gc_without_widget_ref(lv)
        test_button_callback(lv)
        if _is_cpython():
            test_remove_style_none(lv)
            test_multi_callbacks(lv)
    finally:
        _teardown_display(buf)
        disp = None
        buf = None
        gc.collect()
        lv.deinit()

    print("All LVGL smoke tests passed.")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit:
        raise
    except Exception as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if code != 0:
        raise SystemExit(code)
    if _is_cpython() and sys.platform == "win32":
        import os

        os._exit(0)
    raise SystemExit(0)
