# lv_bindings

LVGL header-to-C binding generator for MicroPython, CircuitPython, and CPython.

## Layout

```
lv_bindings/
  binding/              # Modular Python generator
  lvgl/                 # LVGL submodule (git submodule update --init)
  lv_conf.h             # Shared LVGL config for all targets
  generated/            # Generated bindings (lvgl_*.c, lvgl.pyi — committed)
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

Place `lv_bindings/` as a sibling of `lv_micropython_cmod/` or `lv_circuitpython_mod/` in your workspace (or clone into `cmods/` when using the cmods workspace).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

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

After regen in a cmods workspace, run `../build_all.sh` (see [cmods AGENTS.md](../AGENTS.md)).

Release workflow and tagging: [PUBLISHING.md](PUBLISHING.md).

## Consumers


| Repo                                                                      | Sync                                                                                                                                                          |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [lv_micropython_cmod](https://github.com/PyDevices/lv_micropython_cmod)   | `generated/lvgl_micropython.c`, `lvgl/`, `lv_conf.h`                                                                                                          |
| [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod) | `generated/lvgl_circuitpython.c`, `generated/lvgl_circuitpython.h`, `lvgl/`, `lv_conf.h`                                                                      |
| [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod)             | `generated/lvgl_python.c`, `lvgl/`, `lv_conf.h` — see [PUBLISHING.md](PUBLISHING.md#cpython-auto-release-lv_cpython_mod) for automated sync on push to `main` |


