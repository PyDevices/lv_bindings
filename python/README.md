# Hand-written Python helpers

Pure-Python modules that ship with the LVGL bindings. These are **not**
generator output — edit them here, then sync into consumer repos.

| File | Import | Notes |
|------|--------|-------|
| `display_driver.py` | `import display_driver` | LVGL-owned display/input/`event_loop` glue for PyDevices (`board_config`, `events`, `keys`, `multimer`); independent of optional `appdev` |
| `fs_driver.py` | `import fs_driver` | Python-backed `lv_fs` driver: `fs_driver.register("S")`, then `lv.binfont_create("S:fonts/x.bin")` streams from the platform filesystem. Pairs with the runtime-loadable fonts in [`../fonts/`](../fonts/) |

## Sync into consumers

Both `display_driver.py` and `fs_driver.py` follow the same path:

| Repo | Destination | How it ships |
|------|-------------|--------------|
| [lvgl-micropython](https://github.com/PyDevices/lvgl-micropython) | `lib/*.py` | Frozen via `manifest.py` |
| [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython) | `lib/*.py` | Frozen via `manifest.py` (unix builds) |
| [lvgl-python](https://github.com/PyDevices/lvgl-python) | repo root | `py_modules` in the `pydevices-lvgl` wheel |

Each consumer has `scripts/sync_from_lvgl_bindings.sh` (or extends the CPython
one) that copies this file from **PyDevices/lvgl-bindings on GitHub**.

## MIP (optional)

```text
mip.install("github:PyDevices/lvgl-bindings/packages/display_driver.json")
mip.install("github:PyDevices/lvgl-bindings/packages/fs_driver.json")
```

Requires a PyDevices `board_config` (from a hardware board package or
`pydevices-desktop`), `events`, `keys`, `multimer`, and an `lvgl` binding.
