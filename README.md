# lvgl-bindings

LVGL header-to-C binding generator for MicroPython, CircuitPython, and CPython.

This repo owns the binding tags and generated sources used by the downstream LVGL repos. The release chain is centered on lvgl-bindings, while only lvgl-python publishes wheels to TestPyPI; lvgl-circuitpython and lvgl-micropython consume the synced bindings and rebuild their own targets.

## Layout

```
lvgl-bindings/
  binding/              # Modular Python generator
  lvgl/                 # LVGL submodule (git submodule update --init)
  lv_conf.h             # Shared LVGL config for all targets
  generated/            # Generated bindings (lvgl_*.c, lvgl.pyi — committed)
  python/               # Hand-written helpers (display_driver.py — committed)
  packages/             # Optional MIP manifests
  regenerate_lvmp.sh    # MicroPython bindings
  regenerate_lvcp.sh    # CircuitPython bindings
  regenerate_lvpy.sh    # CPython bindings (native PyInit_lvgl)
  scripts/              # preprocess_lvgl.sh, verify_bindings.sh
```

## Clone

```bash
git clone https://github.com/PyDevices/lvgl-bindings.git lvgl-bindings
cd lvgl-bindings
git submodule update --init lvgl
```

Place `lvgl-bindings/` as a sibling of `lvgl-micropython/`, `lvgl-circuitpython/`, and/or `lvgl-python/` in your workspace. ([cmods](https://github.com/PyDevices/cmods) is an optional convenience workspace — not required.)

## 🚀 Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Typical workflow

The practical flow is: make a small change in **`binding/`** or the LVGL submodule, regenerate the binding target you need, sync the generated files into the consumer repo, and then rebuild that repo’s firmware or extension. If you only touched the Python-side glue, start with **`python/display_driver.py`** and the consumer sync script; if you changed the C API surface or LVGL headers, regenerate the relevant target first and rebuild the consumer before trusting the result.

## Generate bindings

Regenerate after changing `lvgl/`, `lv_conf.h`, or `binding/`, then commit the updated files under `generated/`:

```bash
./regenerate_lvmp.sh          # MicroPython → lvgl_micropython.c + lvgl.pp/json/pyi
./regenerate_lvcp.sh          # CircuitPython → lvgl_circuitpython.c + lvgl_circuitpython.h + …
./regenerate_lvpy.sh          # CPython → lvgl_python.c + lvgl.pp/json/pyi
./regenerate_all.sh           # All three targets (release workflow)
```

Each regenerate script is self-contained: it preprocesses LVGL headers and writes
`generated/*.c`, shared `lvgl.json`, `lvgl.pp`, and `lvgl.pyi`.

Per-target scripts read `LV_NAMING_STYLE` from the environment (`pythonic` for PEP 8-style
export names; default is legacy / MP-shaped). Pass `--pythonic` to `regenerate_all.sh`
to set that for all three targets.

```bash
./scripts/verify_bindings.sh  # Regenerate all targets + regression checks
```

After regen, rebuild the consumer repo(s) (`lvgl-micropython`,
`lvgl-circuitpython`, `lvgl-python`) as usual.

Release workflow and tagging: [PUBLISHING.md](docs/PUBLISHING.md).

## Hand-written Python

See [`python/README.md`](python/README.md). Edit `python/display_driver.py` here, then sync
into each consumer with that repo's `scripts/sync_from_lvgl_bindings.sh`.

## Consumers


| Repo                                                                      | Sync                                                                                                                                                          |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [lvgl-micropython](https://github.com/PyDevices/lvgl-micropython)   | `generated/lvgl_micropython.c`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` → `lib/`                                                                      |
| [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython) | `generated/lvgl_circuitpython.c`, `generated/lvgl_circuitpython.h`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` → `lib/`                                  |
| [lvgl-python](https://github.com/PyDevices/lvgl-python)             | `generated/lvgl_python.c`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` — see [PUBLISHING.md](docs/PUBLISHING.md#cpython-auto-release-lvgl-python)       |


