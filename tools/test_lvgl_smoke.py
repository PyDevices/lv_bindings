#!/usr/bin/env python3
"""Unified LVGL binding smoke tests for MicroPython, CircuitPython, and CPython.

Run with the target interpreter after building that port, for example:

  # MicroPython unix
  ./micropython/ports/unix/build-standard/micropython \\
    ./lvgl-bindings/tools/test_lvgl_smoke.py

  # CircuitPython unix
  ./circuitpython/ports/unix/build-coverage/micropython \\
    ./lvgl-bindings/tools/test_lvgl_smoke.py

  # CPython (WSL venv)
  ./lvgl-python/.venv/bin/python ./lvgl-bindings/tools/test_lvgl_smoke.py

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


def _lv_export(lv, name):
    """Resolve an established module-level export."""
    return getattr(lv, name, None)


def _widget_type(lv, name):
    return _lv_export(lv, name)


def _widget_attr(obj, name):
    return getattr(obj, name)


def _module_defines(module, name):
    namespace = getattr(module, "__dict__", None)
    if namespace is not None:
        return name in namespace
    return name in dir(module)


def _is_cpython():
    impl = getattr(sys, "implementation", None)
    return impl is not None and impl.name == "cpython"


def _runtime_target():
    impl = getattr(sys, "implementation", None)
    name = getattr(impl, "name", "")
    if name == "cpython":
        return "cpython"
    if name == "circuitpython":
        return "circuitpython"
    return "micropython"


def _prepare_import_path():
    """Avoid lvgl-bindings/lvgl submodule shadowing the compiled CPython extension."""
    if not _is_cpython():
        return
    import os.path as ospath

    here = ospath.dirname(ospath.abspath(__file__))
    lvgl_sub = ospath.join(here, "lvgl")
    if ospath.isdir(lvgl_sub):
        norm = ospath.normpath
        sys.path[:] = [p for p in sys.path if norm(p) != norm(here)]
    cpy_mod = ospath.join(ospath.dirname(here), "lvgl-python")
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
    for name in ("C_Pointer", "LvReferenceError"):
        if not hasattr(lv, name):
            _fail("missing module export lv.{}".format(name))
    for name in ("Blob", "Struct", "mp_lv_init_gc", "mp_lv_deinit_gc", "mp_lv_get_roots"):
        if hasattr(lv, name):
            _fail("private implementation export leaked as lv.{}".format(name))
    # _nesting is a deliberate, audited exception to the private-export
    # policy above: it is the binding-internal callback re-entrancy
    # counter that python/display_driver.py (shipped in this repo, synced
    # into every consumer) reads at runtime as lv._nesting.value to guard
    # against reentrant lv.task_handler() calls. It is private in the
    # canonical API model (visibility="private" in api_model.py) but is
    # still deliberately emitted for MicroPython/CircuitPython -- see
    # emit_backend.module_registration_plan, the blob-table loop in
    # emit_c_micropython_style.py, and docs/generator-architecture.md's
    # "Public API policy" section. CPython never emitted it (its own
    # ContextVar-scoped lvpy_nesting_inc/dec serves the same purpose) so it
    # stays forbidden there.
    if _is_cpython():
        if hasattr(lv, "_nesting"):
            _fail("private implementation export leaked as lv._nesting")
    else:
        if not hasattr(lv, "_nesting"):
            _fail(
                "lv._nesting missing; python/display_driver.py's "
                "task_handler()/async_refresh() read lv._nesting.value "
                "and will raise AttributeError at runtime"
            )
    if hasattr(lv, "area_get_width"):
        _fail("struct method leaked as module-level lv.area_get_width")
    if _module_defines(lv, "__init__") or _module_defines(lv, "__del__"):
        _fail("generated lifecycle dunder leaked from module")
    print("OK: common module helpers and private-export policy")


def test_struct_helpers(lv):
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
    label.set_text("lvgl smoke")
    if label.get_text() != "lvgl smoke":
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
    if not fired:
        _fail("callback was collected while its widget remained referenced")
    print("OK: callback survived gc.collect() while widget referenced")


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
    if not fired:
        _fail("callback was collected while its LVGL widget remained reachable")
    print("OK: callback survived gc with widget reached through get_child")


def test_multi_callbacks(lv):
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


def test_pointer_buffer_dereference(lv, main_disp=None):
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
        raw_pointer = color_p.__cast__()
        typed_pointer = color_p.__cast__(_lv_export(lv, "color_t"))
        if not isinstance(raw_pointer, int):
            _fail("Blob.__cast__() did not return a pointer-sized integer")
        if not isinstance(typed_pointer, _lv_export(lv, "color_t")):
            _fail("Blob.__cast__(type) did not return the requested type")
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
    print("OK: opaque pointer dereference and typed cast in flush callback")


def test_remove_style_none(lv):
    part = _lv_export(lv, "PART")
    if part is None:
        return
    scr = lv.screen_active()
    arc = _widget_type(lv, "arc")(scr)
    arc.set_size(40, 40)
    arc.remove_style(None, part.KNOB)
    print("OK: arc.remove_style(None, PART.KNOB)")


def test_struct_fields_and_arrays(lv):
    area = _lv_export(lv, "area_t")()
    area.x1 = 3
    area.y1 = 5
    area.x2 = 13
    area.y2 = 17
    if (area.x1, area.y1, area.x2, area.y2) != (3, 5, 13, 17):
        _fail("struct field read/write mismatch")
    if area.get_width() != 11 or area.get_height() != 13:
        _fail("struct method did not observe updated fields")

    scr = lv.screen_active()
    line = _widget_type(lv, "line")(scr)
    point_type = _lv_export(lv, "point_precise_t")
    points = point_type(2)
    first = point_type()
    second = point_type()
    first.x, first.y = 1, 2
    second.x, second.y = 8, 9
    points[0] = first
    points[1] = second
    line.set_points(points, 2)
    print("OK: struct fields, struct methods, and typed array conversion")


def test_callback_deletion(lv):
    btn = _widget_type(lv, "button")(lv.screen_active())
    fired = []

    def callback(event):
        fired.append(1)

    descriptor = btn.add_event_cb(callback, _lv_export(lv, "EVENT").CLICKED, None)
    if not btn.remove_event_dsc(descriptor):
        _fail("remove_event_dsc did not report a removed callback")
    btn.send_event(_lv_export(lv, "EVENT").CLICKED, None)
    if fired:
        _fail("deleted callback was invoked")
    print("OK: callback deletion")


def test_object_lifetime_and_pointer_validation(lv):
    btn = _widget_type(lv, "button")(lv.screen_active())
    btn.delete()
    try:
        btn.get_width()
    except lv.LvReferenceError:
        pass
    else:
        _fail("deleted object did not raise LvReferenceError")

    try:
        _widget_type(lv, "label")("not an LVGL parent")
    except (TypeError, ValueError, SyntaxError):
        pass
    else:
        _fail("invalid object pointer was accepted")
    print("OK: deleted-object and pointer validation")


def test_target_exceptions(lv):
    has_tjpgd = hasattr(lv, "tjpgd_init") or hasattr(lv, "tjpgd_deinit")
    if _runtime_target() == "micropython":
        if not has_tjpgd:
            _fail("MicroPython is missing its enabled TJPGD API")
    elif has_tjpgd:
        _fail("TJPGD API leaked into a target that excludes the subsystem")
    print("OK: reviewed target exception policy")


def main():
    lv = _import_lv()

    test_import_and_constants(lv)
    test_string_constants(lv)
    test_enums(lv)
    test_module_types(lv)
    test_struct_helpers(lv)
    test_widget_types(lv)
    test_module_functions(lv)
    test_target_exceptions(lv)

    if _is_initialized(lv):
        lv.deinit()

    test_basic(lv)
    disp, buf = _setup_display(lv)
    try:
        if _is_cpython():
            test_refr_now(lv, disp)
            test_pointer_buffer_dereference(lv, disp)
        test_widget(lv)
        test_struct_fields_and_arrays(lv)
        test_event_callback(lv)
        test_callback_gc_with_widget_ref(lv)
        test_callback_gc_without_widget_ref(lv)
        test_button_callback(lv)
        test_callback_deletion(lv)
        test_object_lifetime_and_pointer_validation(lv)
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
