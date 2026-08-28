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
- [Loading fonts at runtime](docs/fonts.md) — `fonts/*.bin` and
  `python/fs_driver.py`: any built-in font without a firmware rebuild.
- [docs/](docs/) — the full index.

## Layout

```
lvgl-bindings/
  binding/              # Modular Python generator
  lvgl/                 # LVGL submodule (git submodule update --init)
  lv_conf.h             # Shared LVGL config for all targets
  generated/            # Generated bindings, API model, and shared stub (committed)
  python/               # Hand-written helpers (display_driver.py — committed)
  packages/             # Optional MIP manifests
  binding/generate.py    # Unified all-target generator
  tools/                 # Artifact hashing and smoke checks
  scripts/               # Verification and release utilities
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
PYTHONPATH=. .venv/bin/python -m binding.generate                    # all targets
PYTHONPATH=. .venv/bin/python -m binding.generate --target micropython
PYTHONPATH=. .venv/bin/python -m binding.generate --target circuitpython
PYTHONPATH=. .venv/bin/python -m binding.generate --target cpython
PYTHONPATH=. .venv/bin/python -m binding.generate --pyi-only         # shared stub only
PYTHONPATH=. .venv/bin/python -m binding.generate --check            # read-only reproducibility check
```

The unified command preprocesses LVGL once and writes the selected target C
source, the target-neutral `api.json`, shared `lvgl.json`/`lvgl.pp`, the
CircuitPython generated header, and the shared `lvgl.pyi`. The API model is
hashed and includes visibility and target availability; deliberate exceptions
are recorded in `binding/api_policy.json`. Preprocessing removes compiler line markers so the
inputs are reproducible across checkout paths. The command's `--check` mode
generates into a temporary directory and never changes the working tree.

Use `--naming-style pythonic` only when deliberately testing the alternate
profile; release generation remains on the legacy upstream-compatible names.

The shared stub is generated from `generated/lvgl.json` and `generated/lvgl.pp`.
Use `--pyi-only` when changing typing enrichment so the C bindings, API model,
and their IR inputs are not regenerated.

```bash
./scripts/verify_bindings.sh  # Read-only checks
```

After regen, rebuild the consumer repo(s) (`lvgl-micropython`,
`lvgl-circuitpython`, `lvgl-python`) as usual.

Release workflow and tagging: [releasing-bindings.md](docs/releasing-bindings.md).

## `display_driver.py` & Timer Integration

`display_driver.py` is the canonical PyDevices LVGL coordinator:
- It connects the LVGL event loop to `displaydev` and `multimer` without requiring `appdev`.
- **Automatic Timer Startup**: Simply importing `display_driver` initializes the display, registers input devices, and starts the background hardware interrupt/signal timer.
- **Interactive REPL**: On MicroPython (`machine.Timer`), Linux desktop (`librt`), and Windows (`uwin32`), you can construct LVGL widgets and drop out to the interactive `>>>` prompt without any loop—the UI and animations keep running live in the background.
- **Standalone Desktop Applications**: Standalone scripts include `app.run()` to keep the desktop process alive.

See [`python/README.md`](python/README.md). Edit `python/display_driver.py` here, then sync
into each consumer with that repo's `scripts/sync_from_lvgl_bindings.sh`.

## Consumers

| Repo | Role & Sync |
|---|---|
| [lvgl-micropython](https://github.com/PyDevices/lvgl-micropython) | MicroPython C module: `generated/lvgl_micropython.c`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` → `lib/` |
| [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython) | CircuitPython tree patches: `generated/lvgl_circuitpython.c`, `generated/lvgl_circuitpython.h`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` → `lib/` |
| [lvgl-python](https://github.com/PyDevices/lvgl-python) | CPython extension & TestPyPI wheel publisher: `generated/lvgl_python.c`, `lvgl/`, `lv_conf.h`, `python/display_driver.py` (see [releasing-bindings.md](docs/releasing-bindings.md#cpython-auto-release-lvgl-python)) |
