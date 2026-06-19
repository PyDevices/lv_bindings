# lv_bindings

LVGL header-to-C binding generator for MicroPython, CircuitPython, and future Python targets.

## Layout

```
lv_bindings/
  binding/              # Modular Python generator
  lvgl/                 # LVGL submodule (git submodule update --init)
  lv_conf.h             # Shared LVGL config for all targets
  generated/            # Output (gitignored): lvmp.c, lvcp.c
  regenerate_lvmp.sh    # MicroPython bindings
  regenerate_lvcp.sh    # CircuitPython bindings
  regenerate_lvpy.sh    # CPython bindings (native PyInit_lvgl)
  verify_bindings.sh    # Regression checks
```

## Clone

```bash
git clone git@github.com:PyDevices/lv_bindings.git lv_bindings
cd lv_bindings
git submodule update --init lvgl
```

HTTPS alternative: `https://github.com/PyDevices/lv_bindings.git`

Place `lv_bindings/` as a sibling of `lv_micropython_cmod/` or `lv_circuitpython_mod/` in your workspace (or clone into `cmods/` when using the cmods wrapper).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Generate bindings

Bindings are not committed. Regenerate after changing `lvgl/`, `lv_conf.h`, or `binding/`:

```bash
./regenerate_lvmp.sh          # MicroPython → generated/lvmp.c
./regenerate_lvcp.sh          # CircuitPython → generated/lvcp.c
./regenerate_lvpy.sh          # CPython → generated/lvpy.c
```

Set `LV_BINDINGS_DEBUG=1` to keep preprocessed `.pp` and `.json` metadata files.

```bash
./verify_bindings.sh          # Regenerate both + regression checks
./clean_generated.sh          # Remove generated/ and pycparser caches
```

## Consumers

| Repo | Uses |
|------|------|
| [lv_micropython_cmod](https://github.com/PyDevices/lv_micropython_cmod) | `generated/lvmp.c`, `lvgl/`, `lv_conf.h` |
| [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod) | `generated/lvcp.c`, `lvgl/`, `lv_conf.h` |
| `lv_cpython_mod` (sibling repo) | `generated/lvpy.c`, `lvgl/`, `lv_conf.h`, `setup.py` |
