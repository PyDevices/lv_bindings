# lv_bindings

LVGL header-to-C binding generator for MicroPython, CircuitPython, and CPython.

## Layout

```
lv_bindings/
  binding/              # Modular Python generator
  lvgl/                 # LVGL submodule (git submodule update --init)
  lv_conf.h             # Shared LVGL config for all targets
  generated/            # Generated bindings (lvmp.c, lvcp.c, lvpy.c — committed)
  regenerate_lvmp.sh    # MicroPython bindings
  regenerate_lvcp.sh    # CircuitPython bindings
  regenerate_lvpy.sh    # CPython bindings (native PyInit_lvgl)
  verify_bindings.sh    # Regression checks
```

## Clone

```bash
git clone https://github.com/PyDevices/lv_bindings.git lv_bindings
cd lv_bindings
git submodule update --init lvgl
```

Place `lv_bindings/` as a sibling of `lv_micropython_cmod/` or `lv_circuitpython_mod/` in your workspace (or clone into `cmods/` when using the cmods wrapper).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Generate bindings

Regenerate after changing `lvgl/`, `lv_conf.h`, or `binding/`, then commit the updated files under `generated/`:

```bash
./regenerate_lvmp.sh          # MicroPython → generated/lvmp.c
./regenerate_lvcp.sh          # CircuitPython → generated/lvcp.c
./regenerate_lvpy.sh          # CPython → generated/lvpy.c
```

Set `LV_BINDINGS_DEBUG=1` to keep preprocessed `.pp` and `.json` metadata files (gitignored).

```bash
./verify_bindings.sh          # Regenerate all targets + regression checks
./clean_generated.sh          # Remove debug *.pp / *.json (keeps *.c)
./clean_generated.sh --all    # Also remove generated/*.c
```

## CPython auto-release (lv_cpython_mod)

When `generated/lvpy.c`, `lv_conf.h`, or the `lvgl` submodule pin changes on **`main`**, the
[trigger-lv-cpython-mod-release](.github/workflows/trigger-lv-cpython-mod-release.yml) workflow
starts **Sync and release** on [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod)
(sync → commit → tag → TestPyPI).

Add repository secret **`LVCPYTHON_MOD_DISPATCH_TOKEN`** (Settings → Secrets → Actions): a PAT
with **`actions:write`** on `PyDevices/lv_cpython_mod` (fine-grained or classic `repo` scope).

## Consumers

| Repo | Sync |
|------|------|
| [lv_micropython_cmod](https://github.com/PyDevices/lv_micropython_cmod) | `generated/lvmp.c`, `lvgl/`, `lv_conf.h` |
| [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod) | `generated/lvcp.c`, `lvgl/`, `lv_conf.h` |
| [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod) | Pushing `generated/lvpy.c`, `lv_conf.h`, or `lvgl` on `main` triggers **Sync and release** there automatically (needs `LVCPYTHON_MOD_DISPATCH_TOKEN`). Manual: `./scripts/sync_from_lv_bindings.sh` in that repo. |
