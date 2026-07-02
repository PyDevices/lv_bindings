# `.pyi` generator feedback (from pydisplay / LVGL 9.5.4)

Feedback for refining `binding/emit_pyi.py` and `binding/pyi_prototypes.py`, based on real usage in [pydisplay](https://github.com/PyDevices/pydisplay) (`display_driver.py`, `lv_utils.py`, LVGL examples) and type-checking with **Pylance** / **basedpyright** against `generated/lvgl.pyi`.

**Consumer setup (for reproducing):** see pydisplay `tools/README.md` — `python.analysis.stubPath`, venv symlink via `tools/link_lvgl_stubs.sh`, and `tools/typings/lvgl/__init__.pyi` → `../lvgl.pyi` for Pylance package layout.

---

## Summary

**Implemented (lv_bindings generator, July 2026):** P1 `self` on instance methods; P2 `ENUM | int`; duplex `OBJ_FLAG`; driver callback typing; P4 `Struct.__init__` dict overload; P5 `@staticmethod` for static struct methods; P6 `_Nesting.value` + `font_get_default` in stubs; P8 `lvgl.pyi` shipped beside CPython extension on `pip install`.

**Open (P1b, July 2026):** three leftover signatures where the C receiver was converted to `self` but a **duplicate receiver parameter** was not stripped, or a nullable C pointer was not marked optional. See [Priority 1b](#priority-1b--strip-duplicate-receivers-and-nullable-pointer-params).

Historical note — the dominant bug **was**:

> C receiver stripping removes the first `lv_*_t *` parameter but **does not insert `self`**, so Pyright binds the instance (`disp`, `indev`, `style`, `btn`, …) to the first *remaining* parameter.

This affects **~1,170 struct methods** and **all widget methods inherited from `obj`** in the current 9.5 stubs.

Secondary issues: enum-constant vs enum-class parameter types, a few out-parameter signatures, and missing binding/runtime-only symbols.

---

## Priority 1 — Add `self` to emitted instance methods

### Symptom

```python
disp = lv.display_create(320, 480)
disp.set_theme(th)          # error: display_t not assignable to theme_t
indev.set_type(lv.INDEV_TYPE.POINTER)  # error: indev_t not assignable to INDEV_TYPE
style.init()                # error: cannot access attribute "init"
btn.align(lv.ALIGN.CENTER, 0, 0)     # error: cannot access attribute "align"
```

### Current emitter behaviour

`emit_pyi.py` → `_format_function(..., instance_method=True)` calls `_strip_receiver_arg()` which removes the C `disp` / `obj` / `color` receiver from `args`, then emits the rest **without** a `self` parameter:

```python
# binding/emit_pyi.py (conceptual)
def set_theme(th: theme_t) -> None: ...   # emitted today — wrong for Python
```

```python
# what type checkers need
def set_theme(self, th: theme_t) -> None: ...
```

`pyi_prototypes.strip_receiver_args()` correctly models the **C API**; `emit_pyi._format_function()` must add `self` (or `cls` for `@classmethod`) when `instance_method=True`.

### Affected emission sites

| Site | `instance_method=True` | Notes |
|------|------------------------|-------|
| `_emit_struct_types()` | `receiver_struct=struct_name` | `display_t`, `indev_t`, `style_t`, `anim_t`, … |
| `_emit_widget_class()` | `receiver_obj=obj_name` | `obj`, `button`, `label`, … |
| Widget subclasses | inherit `obj` methods only at runtime | Stubs put methods on `obj`; same `self` fix applies |

### Suggested fix

In `_format_function()` when `instance_method` is true, prepend `self` to the formatted param list **after** receiver stripping:

```python
params = self._format_params(args)
if instance_method:
    params = f"self{', ' + params if params else ''}"
```

Use `typing_extensions.Self` as the return type for `create()`-style widget factories only if you want stricter typing later — not required for the first fix.

### Regression tests to add (`tests/test_pyi_prototypes.py` or new `tests/test_emit_pyi.py`)

```python
# display_t instance method
assert "def set_theme(self, th: theme_t)" in sig

# indev_t
assert "def set_type(self, indev_type: INDEV_TYPE | int)" in sig  # see Priority 2

# style_t
assert "def init(self) -> None" in sig

# obj widget method
assert "def align(self, align: ALIGN, x_ofs: int, y_ofs: int)" in sig
```

### Validation command (pydisplay)

```bash
cd pydisplay
./tools/link_lvgl_stubs.sh
.venv/bin/basedpyright src/add_ons/display_driver.py src/examples/lv_touch_test.py
```

Before `self` fix: **30+ errors** on those two files. After P1+P2 (July 2026): **3 LVGL-signature errors** remain in pydisplay — see Priority 1b. Target: **0 LVGL-signature errors** (ignoring unrelated `board_config` / multimer typing).

---

## Priority 1b — Strip duplicate receivers and nullable pointer params

**Status: open** (verified against pydisplay `generated/lvgl.pyi` after P1+P2 land).

P1 adds `self` and P1's `strip_receiver_args()` removes the C struct receiver from `args` — but some methods still emit a **second parameter that duplicates `self`** (receiver stripping missed), or omit **`| None`** on C pointers that accept `NULL`.

### Symptom → pydisplay call site

| Stub (wrong) | Runtime call | basedpyright error |
|--------------|--------------|------------------|
| `group_t.set_default(self, arg: Any)` | `lv.group_create().set_default()` | Argument missing for parameter `"arg"` |
| `display_t.flush_ready(self, disp: Any)` | `self.lv_display.flush_ready()` | Argument missing for parameter `"disp"` |
| `obj.remove_style(self, style: style_t, selector: …)` | `arc.remove_style(None, lv.PART.KNOB)` | `None` not assignable to `style_t` |

### C prototypes (`generated/lvgl.pp`)

```c
void lv_group_set_default(lv_group_t * group);
void lv_display_flush_ready(lv_display_t * disp);
void lv_obj_remove_style(lv_obj_t * obj, const lv_style_t * style, lv_style_selector_t selector);
```

After binding, Python calls are **instance methods with no extra receiver argument**:

```python
group.set_default()           # sets this group as default
disp.flush_ready()            # marks this display's flush complete
obj.remove_style(None, part)  # style=NULL removes all styles in selector
```

### Root cause

`strip_receiver_args()` in `pyi_prototypes.py` does not remove the first parameter for these methods — likely because IR/PP types or names (`arg`, `disp`, `_lv_display_t *`) do not match `_struct_receiver_types()` / `_is_trailing_struct_receiver()` heuristics. P1 then prepends `self`, yielding **self + unstripped receiver**.

For `remove_style`, the C parameter is `const lv_style_t *` (nullable); the emitter should type it `style_t | None`, not bare `style_t`.

### Suggested fixes

**1. Harden receiver stripping** (`pyi_prototypes.strip_receiver_args` or post-pass in `emit_pyi._format_function`):

When `instance_method=True` and `receiver_struct` is set, also strip the first remaining arg if:

- its type equals `receiver_struct` (or struct prefix), **or**
- its name is in `{struct_prefix, "disp", "group", "indev", "obj", "style", "arg"}` **and** its type is the receiver struct or `Any`, **or**
- PP lookup shows the C function's first parameter is exactly the receiver pointer (compare `lookup_pp_proto`).

After fix, these should emit **params = `self` only**:

```python
def set_default(self) -> None: ...
def flush_ready(self) -> None: ...
```

**2. Nullable pointer parameters**

When PP marks a pointer parameter as `const T *` and the C docs / binding allow `NULL`, emit `T | None`. Minimum set for pydisplay:

```python
def remove_style(self, style: style_t | None, selector: int | PART | STATE) -> None: ...
```

General rule: optional table or heuristic — `const lv_*_t *` style/object params in remove/clear/reset APIs → `| None`.

**3. Optional: module-level duplicates**

Module functions `group_set_default(group)`, `display_flush_ready(disp)` may remain for legacy style; instance methods above are what bound objects use in Python.

### Regression tests

```python
def test_group_set_default_instance_method():
    sig = emitter._format_function(
        "set_default", info, instance_method=True, receiver_struct="group_t"
    )
    assert sig == "set_default(self) -> None: ..."

def test_display_flush_ready_instance_method():
    sig = emitter._format_function(
        "flush_ready", info, instance_method=True, receiver_struct="display_t"
    )
    assert sig == "flush_ready(self) -> None: ..."

def test_obj_remove_style_accepts_none():
    sig = emitter._format_function(
        "remove_style", info, instance_method=True, receiver_obj="obj"
    )
    assert "style: style_t | None" in sig
```

### Validation (pydisplay)

```bash
cd pydisplay
./tools/link_lvgl_stubs.sh
.venv/bin/basedpyright src/add_ons/display_driver.py src/examples/lv_test_timer_common.py
```

Expect **0 errors** attributable to `lvgl.pyi` in those files (ignore `display_drv._timer.deinit` optional typing, etc.).

---

## Priority 2 — Enum parameters: use `ENUM | int`, not bare enum class

### Symptom

Enum **members** are emitted as `int`:

```python
class PALETTE:
    BLUE: int
    CYAN: int
```

But many function parameters use the **enum class name** as the type:

```python
def palette_main(p: PALETTE) -> color_t: ...        # today
def color_format_get_size(cf: COLOR_FORMAT) -> int: ...
def set_type(indev_type: INDEV_TYPE) -> None: ...
```

Call sites pass `lv.PALETTE.BLUE` (typed `int`) → **"int is not assignable to PALETTE"**.

### Already correct in some places

Good pattern already used for flags/selectors:

```python
def add_flag(f: OBJ_FLAG | int) -> None: ...
def add_style(style: style_t, selector: int | PART | STATE) -> None: ...
```

### Suggested rule

In `_map_type()` / `_format_arg_type()`, when resolving a typedef to a module enum class `FOO`, emit:

```text
FOO | int
```

Apply to **all** enum typedef parameters and return types where members are `int` (essentially all LVGL enums in MicroPython bindings).

`_INT_ALIAS_TYPEDEFS` already does this for `obj_flag_t` → `OBJ_FLAG | int`. **Generalise** to every `enum_typedefs` / `_LEGACY_ENUM_TYPEDEFS` resolution.

### Manual fixes made in pydisplay (workarounds)

| Symbol | Was | Workaround applied |
|--------|-----|-------------------|
| `palette_main` | `p: PALETTE` | changed to `p: int` in consumer copy |
| `display_t.set_theme` | `set_theme(th: theme_t)` | added `self` in consumer copy |

These should be generator fixes, not hand-edits in downstream repos.

### Regression test

```python
def test_enum_param_accepts_int_member():
    sig = emitter._format_function("palette_main", {...}, instance_method=False)
    assert "p: PALETTE | int" in sig  # or "p: int" if you prefer simplicity
```

---

## Priority 3 — Out-parameters vs return values

### `get_coords`

Runtime (LVGL 9.5): **no** zero-arg tuple return. Caller must pass `area_t`:

```python
area = lv.area_t()
btn.get_coords(area)
```

Stub today:

```python
def get_coords(coords: area_t) -> None: ...
```

This is **correct** once `self` is added:

```python
def get_coords(self, coords: area_t) -> None: ...
```

Do **not** emit a zero-arg `get_coords() -> tuple[int, int, int, int]` variant.

Same pattern likely applies to other `lv_*_get_*` functions that write into caller-provided structs (`get_point`, `get_vect`, `area_t` out-params, etc.). Audit struct methods whose C signature ends with a non-const pointer struct parameter.

---

## Priority 4 — Struct field initializers / dict constructors

### Runtime pattern (common in pydisplay)

```python
data.point = lv.point_t({"x": 0, "y": 0})
```

Structs are mutable with fields (`point_t.x`, `point_t.y`) and accept dict construction in the binding.

### Stub gap

```python
class point_t(Struct):
    x: int
    y: int
    # no __init__ overload for dict
```

### Suggested stub

```python
class point_t(Struct):
    x: int
    y: int
    def __init__(self, fields: dict[str, int] | None = None, /, **kwargs: int) -> None: ...
```

Or a shared `Struct` base `__init__` accepting `dict[str, Any]`. Low priority for type checking (attribute assignment still works), but improves constructor diagnostics.

---

## Priority 5 — Static / class methods on structs

Some `struct_functions` are C **static** APIs, not instance methods. After adding `self`, these may need `@staticmethod` or a module-level function instead.

### Examples to review

| Class | Method | C semantics (likely) |
|-------|--------|-------------------|
| `style_t` | `copy(src: style_t)` | copy *into* self, or static? |
| `style_t` | `merge(src: style_t)` | same |
| `style_t` | `is_const(style: style_t)` | static — takes style as arg |
| `color_t` | `mix(c2: color_t, mix: int)` | instance |
| `point_t` | `from_precise(...)` | static factory |

`pyi_prototypes.struct_method_c_name()` and PP lookup can identify static vs instance. If the first PP parameter is **not** the struct receiver type, emit `@staticmethod` (no `self`) or emit as module-level `lv.style_copy(dest, src)`.

---

## Priority 6 — Internal / unresolved type names

### `_lv_display_t` in public stubs

```python
def set_display(disp: _lv_display_t) -> None: ...   # indev_t — type not defined
```

Should be `display_t` (or `display_t | None`).

Likely a struct prefix normalization gap in `_map_type()` for internal LVGL typedef names not in `known_structs`.

### Binding-only module globals

Used in real code but absent from stubs:

| Symbol | Used for |
|--------|----------|
| `lv._nesting` | re-entrancy guard around `task_handler()` in `lv_utils.py` |
| `lv.font_get_default()` | theme init (if not in IR) |

Options:

- Emit from IR/binding metadata as `# binding internal` section
- Document as intentional omissions
- Add manually to a `lvgl_binding_extras.pyi` partial stub

---

## Priority 7 — Callback / flush signature details

### `display_t.set_flush_cb`

Pydisplay flush callback:

```python
def _flush_cb(self, disp_drv, area, color_p):
    data = color_p.__dereference__(width * height * color_size)
```

Verify emitted type:

```python
flush_cb: Callable[[display_t, area_t, Any], None]
```

`Blob.__dereference__(self) -> Any` on flush buffer is good — keep it.

### `indev` read callback

Pydisplay uses `device.poll` as `read_cb` with a custom `(event, indev, data)` shape at the Python layer; the LVGL C callback is `(indev_t, indev_data_t) -> None`. Current stub for `set_read_cb` is fine once `self` is fixed.

---

## Priority 8 — Distribution / IDE consumption notes

Downstream projects install **`lvgl-cpython`** as a native `.so` without bundled `.pyi`. Type checkers bind to the binary unless stubs overlay it.

Document for consumers:

1. **`python.analysis.stubPath`** → directory containing `lvgl/__init__.pyi` (or `lvgl.pyi` beside the module in site-packages).
2. Pylance expects **package subdirectory** layout: `typings/lvgl/__init__.pyi` (can symlink to flat `lvgl.pyi`).
3. Venv symlink after `pip install`:

   ```bash
   ln -sf ../../../../tools/typings/lvgl.pyi .venv/lib/python3.12/site-packages/lvgl.pyi
   ```

   (Four `..` from `site-packages`, not three.)

4. `pyrightconfig.json` `stubPath` mirrors Pylance for CLI checking.

Consider shipping `lvgl.pyi` (or `lvgl-stubs` per PEP 561) inside the `lvgl-cpython` wheel to avoid manual symlinks.

---

## Real-world API corrections (not generator bugs, but doc-worthy)

These were wrong in example code, not the stubs:

| Old (invalid LVGL 9.5) | Correct |
|------------------------|---------|
| `lv.display_create()` | `lv.display_create(hor_res, ver_res)` |
| `lv.theme_set(lv.theme_sys())` | `th = lv.theme_default_init(disp, primary, secondary, dark, font); disp.set_theme(th)` |
| `btn.get_coords()` → tuple | `area = lv.area_t(); btn.get_coords(area)` |
| `arc.clear_flag(...)` | `arc.remove_flag(...)` (9.x) |

Generator already emits correct signatures for several of these **once `self` and enum typing are fixed**.

---

## Suggested implementation order

1. ~~**`self` on all `instance_method=True` emissions**~~ — done (P1).
2. ~~**`ENUM | int` for all enum typedef parameters**~~ — done (P2).
3. **P1b: strip duplicate receivers; `style_t | None` on nullable style params** — 3 errors left in pydisplay.
4. **Resolve `_lv_*` internal typedefs** to public struct names.
5. ~~**Audit static struct methods** (staticmethod vs instance).~~ — done (P5).
6. ~~**Optional:** `Struct.__init__` dict overload; binding-internal symbols; ship stubs with wheel.~~ — done (P4, P6, P8).

---

## Files to touch

| File | Change |
|------|--------|
| `binding/emit_pyi.py` | `_format_function`: prepend `self`; optional `@staticmethod` |
| `binding/emit_pyi.py` | `_map_type` / `_format_arg_type`: `ENUM \| int` |
| `binding/pyi_prototypes.py` | P1b: harden `strip_receiver_args`; nullable `const T *` → `T \| None` |
| `binding/emit_pyi.py` | P1b: post-strip sanity check (no arg typed as receiver struct after `self`) |
| `tests/test_pyi_prototypes.py` | receiver stripping + enum typing tests |
| `tests/test_emit_pyi.py` (new) | end-to-end signature golden tests |
| `generated/lvgl.pyi` | regenerate after fixes |

---

## Golden signatures (copy into tests)

Minimal set derived from pydisplay — if the emitter produces these, downstream type-checking passes:

```python
# module
def display_create(hor_res: int, ver_res: int) -> display_t: ...
def draw_buf_create(w: int, h: int, cf: COLOR_FORMAT | int, stride: int) -> draw_buf_t: ...
def palette_main(p: PALETTE | int) -> color_t: ...
def timer_create(timer_xcb: Callable[[timer_t], None], period: int, user_data: Any) -> timer_t: ...

# display_t
def set_flush_cb(self, flush_cb: Callable[[display_t, area_t, Any], None]) -> None: ...
def set_theme(self, th: theme_t) -> None: ...
def flush_ready(self) -> None: ...

# group_t
def set_default(self) -> None: ...

# indev_t
def set_display(self, disp: display_t) -> None: ...
def set_type(self, indev_type: INDEV_TYPE | int) -> None: ...
def set_read_cb(self, read_cb: Callable[[indev_t, indev_data_t], None]) -> None: ...

# style_t
def init(self) -> None: ...
def set_width(self, value: int) -> None: ...
def set_bg_color(self, value: color_t) -> None: ...

# obj / widgets
def align(self, align: ALIGN | int, x_ofs: int, y_ofs: int) -> None: ...
def get_coords(self, coords: area_t) -> None: ...
def add_style(self, style: style_t, selector: int | PART | STATE) -> None: ...
def remove_style(self, style: style_t | None, selector: int | PART | STATE) -> None: ...
```

---

*Generated from pydisplay LVGL 9.5.4 integration work (July 2026). Re-run validation against `src/add_ons/display_driver.py` and `src/examples/lv_test_timer_common.py` after regenerating `generated/lvgl.pyi`. Last updated: P1b follow-up (duplicate receiver stripping).*
