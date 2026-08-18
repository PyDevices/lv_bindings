# lvgl-bindings

LVGL header-to-C binding generator for MicroPython, CircuitPython, and CPython.

## The LVGL family

This repo owns the binding tags and generated sources used by the downstream LVGL repos, and is
the canonical description of how the family fits together:

- **lvgl-bindings** (this repo) — generates the C bindings (`generated/lvgl_*.c`, `lvgl.pyi`) from
  the LVGL headers for all three targets, and owns the release chain.
- **[lvgl-python](https://github.com/PyDevices/lvgl-python)** — the publishing endpoint. Turns
  synced bindings into versioned `pydevices-lvgl` wheels on TestPyPI. It is the only repo in the
  family that publishes a package.
- **[lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython)** and
  **[lvgl-micropython](https://github.com/PyDevices/lvgl-micropython)** — consumer/build repos.
  They consume the generated bindings and rebuild their own CircuitPython / MicroPython targets,
  but do not publish their own packages to TestPyPI.

Every other repo in the family links back to this section rather than repeating it.

## Documentation

- [Using LVGL with PyDevices](docs/using-lvgl-with-pydevices.md) — how the three
  sister projects fit together, and what `python/display_driver.py` does.
- [docs/](docs/) — the full index.

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

Release workflow and tagging: [releasing-bindings.md](docs/releasing-bindings.md).

## `display_driver.py` & Timer Integration

`display_driver.py` is the canonical PyDevices LVGL coordinator:
- It connects the LVGL event loop to `displaydev` and `multimer` without requiring `eventsys`.
- **Automatic Timer Startup**: Simply importing `display_driver` initializes the display, registers input devices, and starts the background hardware interrupt/signal timer.
- **Interactive REPL**: On MicroPython (`machine.Timer`), Linux desktop (`librt`), and Windows (`uwin32`), you can construct LVGL widgets and drop out to the interactive `>>>` prompt without any loop—the UI and animations keep running live in the background.
- **Standalone Desktop Applications**: Standalone scripts include `runtime.run_forever()` to keep the desktop process alive.

See [`python/README.md`](python/README.md). Edit `python/display_driver.py` here, then sync
into each consumer with that repo's `scripts/sync_from_lvgl_bindings.sh`.

## Consumers

| Repo | Role & Sync |
|---|---|
| [lvgl-micropython](https://github.com/PyDevices/lvgl-micropython) | MicroPython C module: `generated/lvgl_micropython.c`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` → `lib/` |
| [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython) | CircuitPython tree patches: `generated/lvgl_circuitpython.c`, `generated/lvgl_circuitpython.h`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` → `lib/` |
| [lvgl-python](https://github.com/PyDevices/lvgl-python) | CPython extension & TestPyPI wheel publisher: `generated/lvgl_python.c`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` (see [releasing-bindings.md](docs/releasing-bindings.md#cpython-auto-release-lvgl-python)) |



