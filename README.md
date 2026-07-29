# lv_bindings

LVGL header-to-C binding generator for MicroPython, CircuitPython, and CPython.

## Layout

```
lv_bindings/
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
git clone https://github.com/PyDevices/lv_bindings.git lv_bindings
cd lv_bindings
git submodule update --init lvgl
```

Place `lv_bindings/` as a sibling of `lv_micropython_cmod/`, `lv_circuitpython_mod/`, and/or `lv_cpython_mod/` in your workspace. ([cmods](https://github.com/PyDevices/cmods) is an optional convenience workspace — not required.)

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

After regen, rebuild the consumer repo(s) (`lv_micropython_cmod`, `lv_circuitpython_mod`, `lv_cpython_mod`) as usual. With the optional [cmods](https://github.com/PyDevices/cmods) workspace, `../build_all.sh` rebuilds and smoke-tests all of them at once.

Release workflow and tagging: [PUBLISHING.md](docs/PUBLISHING.md).

## Hand-written Python

See [`python/README.md`](python/README.md). Edit `python/display_driver.py` here, then sync
into each consumer with that repo's `scripts/sync_from_lv_bindings.sh`.

## Consumers


| Repo                                                                      | Sync                                                                                                                                                          |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [lv_micropython_cmod](https://github.com/PyDevices/lv_micropython_cmod)   | `generated/lvgl_micropython.c`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` → `lib/`                                                                      |
| [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod) | `generated/lvgl_circuitpython.c`, `generated/lvgl_circuitpython.h`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` → `lib/`                                  |
| [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod)             | `generated/lvgl_python.c`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` — see [PUBLISHING.md](docs/PUBLISHING.md#cpython-auto-release-lv_cpython_mod)       |


