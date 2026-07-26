# Hand-written Python helpers

Pure-Python modules that ship with the LVGL bindings. These are **not**
generator output — edit them here, then sync into consumer repos.

| File | Import | Notes |
|------|--------|-------|
| `display_driver.py` | `import display_driver` | LVGL flush/input/`event_loop` glue for **pydisplay** (`board_config`, `eventsys`, `multimer`) |

## Sync into consumers

| Repo | Destination | How it ships |
|------|-------------|--------------|
| [lv_micropython_cmod](https://github.com/PyDevices/lv_micropython_cmod) | `lib/display_driver.py` | Frozen via `manifest.py` |
| [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod) | `lib/display_driver.py` | Frozen via `manifest.py` (unix builds) |
| [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod) | `display_driver.py` | `py_modules` in the `lvgl-cpython` wheel |

Each consumer has `scripts/sync_from_lv_bindings.sh` (or extends the CPython
one) that copies this file from **PyDevices/lv_bindings on GitHub**.

## MIP (optional)

```text
mip.install("github:PyDevices/lv_bindings/packages/display_driver.json")
```

Requires pydisplay (`board_config`, `eventsys`, `multimer`) and an `lvgl`
binding already available.
