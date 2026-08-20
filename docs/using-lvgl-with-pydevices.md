# Using LVGL with PyDevices

How to run [LVGL](https://lvgl.io/) on the PyDevices display, input, and timing
packages, and what [`python/display_driver.py`](../python/display_driver.py)
does for you.

## The three sister projects

The PyDevices LVGL family bundles this integration for each runtime:

| Repository | Runtime |
|---|---|
| [lvgl-micropython](https://github.com/PyDevices/lvgl-micropython) | MicroPython firmware |
| [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython) | CircuitPython firmware |
| [lvgl-python](https://github.com/PyDevices/lvgl-python) | CPython (`pydevices-lvgl` wheels on TestPyPI) |

All three consume the bindings generated here, and all three share `displaydev`,
neutral board capabilities, and `multimer` — so the same LVGL Python code is
portable across them. You can even develop it interactively in
[Jupyter](https://github.com/PyDevices/pydevices/blob/main/docs/jupyter.md).

The rest of this page covers wiring LVGL up by hand, which is what you need with
upstream [lv_micropython](https://github.com/lvgl/lv_micropython) rather than one
of the sister projects.

## 1. Install the minimum PyDevices packages

```python
import mip
INDEX = "https://PyDevices.github.io/mip"
mip.install("pydevices", index=INDEX)  # displaydev, appdev, and the rest of lib/
mip.install("github:PyDevices/pydevices/board_configs/<your_board>")
```

Replace `<your_board>` with a path from
[board configs](https://github.com/PyDevices/pydevices/blob/main/docs/board-configs.md),
or follow
[install workflows](https://github.com/PyDevices/pydevices/blob/main/docs/install-workflows.md).

## 2. Build or obtain LVGL firmware

Follow upstream [lv_micropython](https://github.com/lvgl/lv_micropython) for your
board. PyDevices supplies the flush and input glue via `board_config.py`; LVGL
supplies the UI toolkit.

For production ESP32 projects, consider
[kdschlosser's lvgl_micropython](https://github.com/kdschlosser/lvgl_micropython)
C drivers wired through `BusDisplay`.

## 3. Wire `board_config` to LVGL

Your `board_config.py` should expose:

- `display_drv` — a `displaydev` driver with `blit_rect`, dimensions, and rotation
- neutral input callables where present: `host_read`, `touch_read`,
  `keypad_read`, `encoder_read`, `encoder_button_read`

Board configs describe hardware; they do not create an application runtime.
Connect LVGL's display flush callback to copy LVGL's draw buffer through
`display_drv.blit_rect` — or use the packaged `display_driver`, which does it
for you.

## `display_driver`

[`python/display_driver.py`](../python/display_driver.py) is the LVGL coordinator.
It ships with all three sister projects (frozen into the MicroPython and
CircuitPython firmwares, bundled with `pydevices-lvgl`). It requires a PyDevices
`board_config`, `events`, `keys`, and `multimer`, and is **independent of the
optional `appdev` package**.

With `display_driver`, LVGL input is wired automatically through its own
`LVGLRuntime` and virtual touch / encoder / keypad devices.

> **Do not instantiate or poll `appdev` in an LVGL app.** `lv.task_handler()`,
> driven by `display_driver.event_loop` plus `multimer`, already drains input.
> Window-close (`QUIT`) is handled by the bridge's `HostInput` path.

Build the UI, then hand control over with `runtime.run_forever()`.

## Sync versus async timers

`display_driver` includes the LVGL `event_loop`, which requires `multimer`.
Inspect **`runtime.timer_async`** — derived from `board_config.timer_async`, or
from the display driver's `requires_async_timer` — to see which backend was
selected:

| `runtime.timer_async` | Applies to |
|---|---|
| `False` (the desktop default) | MCUs, MicroPython Unix, CPython Linux — uses `multimer.auto.Timer` |
| `True` | PyScript, Jupyter, or desktop with `PYDEVICES_TIMER_ASYNC=1` — uses `multimer.AsyncTimer` |

`display_driver` passes it straight through as
`event_loop(asynchronous=runtime.timer_async)`. When it is true, `display_driver`
drives both ticks and `display.show()` from its asynchronous LVGL refresh loop.

The desktop `board_config` reads **`PYDEVICES_TIMER_ASYNC`** for the PG/SDL
branch (the default comes from `AutoDisplay` and is normally `False`); PyScript
and Jupyter always use `timer_async=True`. To force async on desktop, set it
before `board_config` loads:

```python
import os
os.environ["PYDEVICES_TIMER_ASYNC"] = "1"
import display_driver
```

Or export `PYDEVICES_TIMER_ASYNC=1` in the shell that launches the process.

## Verifying an integration

[`lv_test_timer.py`](https://github.com/PyDevices/pydevices-examples/blob/main/lib/examples/lv_test_timer.py)
is a single smoke test that follows `runtime.timer_async` via
`runtime.run_forever()`. Its UI reports the autodetected runtime, OS, display
driver class, timer backend, mode (`sync` / `async`), and LVGL version, plus a
seconds counter, spinning arc, and tap button. It deliberately does **not** read
or write environment variables — set `PYDEVICES_TIMER_ASYNC` in the parent shell
if you want a specific desktop mode.

`python examples/lv_test_timer.py kit` runs a timed LVGL timer and input check,
prints a `KIT_RESULT=` JSON line, then quits. To drive that across every desktop
runtime in both modes, use the harnesses documented in
[pydevices-examples/tools/README.md](https://github.com/PyDevices/pydevices-examples/blob/main/tools/README.md).

## See also

- [Architecture](https://github.com/PyDevices/pydevices/blob/main/docs/architecture.md)
- [displaydev](https://github.com/PyDevices/pydevices/blob/main/docs/displaydev.md)
- [multimer](https://github.com/PyDevices/pydevices/blob/main/docs/multimer.md)
- [appdev](https://github.com/PyDevices/pydevices/blob/main/docs/appdev.md)
