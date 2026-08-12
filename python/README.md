# Hand-written Python helpers

Pure-Python modules that ship with the LVGL bindings. These are **not**
generator output — edit them here, then sync into consumer repos.

| File | Import | Notes |
|------|--------|-------|
| `display_driver.py` | `import display_driver` | LVGL flush/input/`event_loop` glue for **pydisplay** (`board_config`, `eventsys`, `multimer`) |

## Sync into consumers

| Repo | Destination | How it ships |
|------|-------------|--------------|
| [lvgl-micropython](https://github.com/PyDevices/lvgl-micropython) | `lib/display_driver.py` | Frozen via `manifest.py` |
| [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython) | `lib/display_driver.py` | Frozen via `manifest.py` (unix builds) |
| [lvgl-python](https://github.com/PyDevices/lvgl-python) | `display_driver.py` | `py_modules` in the `pydevices-lvgl` wheel |

Each consumer has `scripts/sync_from_lvgl_bindings.sh` (or extends the CPython
one) that copies this file from **PyDevices/lvgl-bindings on GitHub**.

## MIP (optional)

```text
mip.install("github:PyDevices/lvgl-bindings/packages/display_driver.json")
```

Requires pydisplay (`board_config`, `eventsys`, `multimer`) and an `lvgl`
binding already available.
