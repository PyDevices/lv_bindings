# `.pyi` generator — open issues (P1b)

Most of the July 2026 stub work is done (instance-method `self`, `ENUM | int`,
driver callbacks, `Struct.__init__` overloads, `@staticmethod`, nesting /
`font_get_default`, shipping `lvgl.pyi` with the CPython wheel).

**Still open:** a few methods still emit a **duplicate receiver parameter**
after `self`, or omit `| None` on nullable C pointers.

## Wrong stubs → call sites

| Stub (wrong) | Runtime call | basedpyright |
|--------------|--------------|--------------|
| `group_t.set_default(self, arg: Any)` | `lv.group_create().set_default()` | missing `"arg"` |
| `display_t.flush_ready(self, disp: Any)` | `self.lv_display.flush_ready()` | missing `"disp"` |
| `obj.remove_style(self, style: style_t, …)` | `arc.remove_style(None, lv.PART.KNOB)` | `None` not assignable |

C prototypes (`generated/lvgl.pp`):

```c
void lv_group_set_default(lv_group_t * group);
void lv_display_flush_ready(lv_display_t * disp);
void lv_obj_remove_style(lv_obj_t * obj, const lv_style_t * style, lv_style_selector_t selector);
```

Expected Python:

```python
group.set_default()
disp.flush_ready()
obj.remove_style(None, part)  # style=NULL clears styles in selector
```

## Fix

1. Harden `strip_receiver_args` / `_format_function` so when
   `instance_method=True`, the first remaining arg is stripped if it is the
   receiver struct (by type or PP prototype), yielding `set_default(self)` /
   `flush_ready(self)`.
2. Emit `style_t | None` (and similar) for nullable `const T *` clear/remove APIs.

Regression coverage lives in `tests/test_pyi_prototypes.py`
(`test_emit_pyi_golden_driver_signatures` and related).

## Validate (pydisplay)

```bash
cd pydisplay
./tools/link_lvgl_stubs.sh
.venv/bin/basedpyright ../lv_bindings/python/display_driver.py src/examples/lv_test_timer_common.py
```

Target: **0** errors attributable to `lvgl.pyi` in those files.
