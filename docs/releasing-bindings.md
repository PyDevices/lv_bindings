# Publishing lvgl-bindings

This document describes how to cut a new **lvgl-bindings** release after moving the
`lvgl` submodule to a different LVGL version.

lvgl-bindings releases are the upstream binding tags for the LVGL family. The generated
artifacts are consumed by the downstream repos, and only **lvgl-python** publishes
packaged wheels to TestPyPI; **lvgl-circuitpython** and **lvgl-micropython** sync
from these tags and rebuild their own targets rather than publishing separate packages.

## Version scheme

lvgl-bindings tags mirror **LVGL major.minor**. The patch number counts binding
releases on that LVGL line:


| Tag      | Meaning                                                 |
| -------- | ------------------------------------------------------- |
| `v9.5.0` | First lvgl-bindings release for LVGL 9.5.x                |
| `v9.5.1` | Second lvgl-bindings release still on LVGL 9.5.x          |
| `v9.4.0` | First lvgl-bindings release after switching to LVGL 9.4.x |


The tag does **not** copy LVGL's patch version. LVGL `v9.5.0` and `v9.5.2` both
map to the **9.5** lvgl-bindings line; the lvgl-bindings patch increments only when
you publish a new binding release on that line.

## Prerequisites

- Submodule initialized: `git submodule update --init lvgl`
- Python venv with generator deps: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- `gcc` available for preprocessing (used by the regenerate scripts)



## Release workflow



### 1. Check out the target LVGL version

```bash
cd lvgl
git fetch --tags origin
git checkout v9.5.0    # or any other LVGL tag
cd ..
```

Confirm with `git -C lvgl describe --tags` and `grep LVGL_VERSION lvgl/lvgl.h`.

### 2. Preview the release (optional)

```bash
./regenerate_all.sh --dry-run
```

Shows the planned lvgl-bindings tag, commit message, and whether `lvgl` /
`generated/` already differ from the index — without regenerating, committing,
or tagging.

### 3. Regenerate, commit, and tag

```bash
./regenerate_all.sh
```

This script:

1. Regenerates `generated/lvgl_micropython.c`, `generated/lvgl_circuitpython.c`, `generated/lvgl_python.c`, and `generated/lvgl.pyi`
2. Commits the LVGL submodule pin and generated files (if anything changed)
3. Creates an annotated tag (e.g. `v9.5.0`) on the new commit

If regeneration produces no diff, the script skips commit and tag (nothing new
to release).

### 4. Push

```bash
git push origin HEAD --tags
```

Use your branch name instead of `HEAD` if you are not on `main`.

## Script options

```bash
./regenerate_all.sh --dry-run     # preview only
./regenerate_all.sh --no-commit   # regenerate only
./regenerate_all.sh --no-tag      # regenerate and commit, no tag
```



## Validation

For a full regen plus regression checks (line counts, metadata parity, etc.):

```bash
./scripts/verify_bindings.sh
```

Run this before publishing when you change the generator or LVGL config
(`lv_conf.h`), or when cutting a major LVGL bump.

## Downstream consumers

- [lvgl-micropython](https://github.com/PyDevices/lvgl-micropython) — sync
  `generated/lvgl_micropython.c`, `lvgl/`, `lv_conf.h`, and
  `python/display_driver.py` → `lib/` (`./scripts/sync_from_lvgl_bindings.sh`)
- [lvgl-circuitpython](https://github.com/PyDevices/lvgl-circuitpython) — sync
  `generated/lvgl_circuitpython.c`, `generated/lvgl_circuitpython.h`, `lvgl/`,
  `lv_conf.h`, and `python/display_driver.py` → `lib/`
- [lvgl-python](https://github.com/PyDevices/lvgl-python) — sync
  `generated/lvgl_python.c`, `generated/lvgl.pyi`, `lvgl/`, `lv_conf.h`, and
  `python/display_driver.py`; see
  [CPython auto-release](#cpython-auto-release-lvgl-python) below

## Type stubs (`generated/lvgl.pyi`)

Regenerated with every binding release. Used by Pylance, basedpyright, and mypy.
For typing-generator work, run `./regenerate_all.sh --pyi-only`; this reads the
existing shared IR and preprocessed header and does not regenerate C, commit, or tag.

**CPython (`pydevices-lvgl`):** `pip install -e .` copies `generated/lvgl.pyi` beside
the built `lvgl*.so` / `.pyd`. Wheels from this repo include the same file next to
the extension after install.

**Manual overlay** (any port): point the type checker at the stub file:

- Pylance / VS Code: `python.analysis.stubPath` → directory containing `lvgl.pyi`
- Pyright CLI: `stubPath` in `pyrightconfig.json`
- Package layout: `typings/lvgl/__init__.pyi` can re-export or symlink to `lvgl.pyi`

MicroPython / CircuitPython: copy or symlink `generated/lvgl.pyi` into your project
or editor stub path (no `.so` packaging).

After tagging, consumer repos can pin to a specific lvgl-bindings release with
`git checkout v9.5.0` (or sync scripts that reference that tag).

## CPython auto-release (lvgl-python)

When `generated/lvgl_python.c`, `lv_conf.h`, `python/display_driver.py`, or the `lvgl` submodule pin changes on `main`, the [trigger-lvgl-python-release](../.github/workflows/trigger-lvgl-python-release.yml) workflow starts **Sync and release** on [lvgl-python](https://github.com/PyDevices/lvgl-python) (sync → versioned commit → published GitHub Release → shared TestPyPI build).

### Setup

Add repository secret for repository dispatch (Settings → Secrets → Actions):
a PAT with **`actions:write`** on `PyDevices/lvgl-python`.

### Manual sync

Without pushing to `main`, or for local testing, run in `lvgl-python`:

```bash
./scripts/sync_from_lvgl_bindings.sh
```

## Example session

```bash
cd lvgl && git fetch --tags origin && git checkout v9.5.0 && cd ..

./regenerate_all.sh --dry-run
# LVGL submodule: v9.5.0 (API 9.5.0)
# lvgl-bindings tag: v9.5.0
# ...

./regenerate_all.sh
git push origin main --tags
```

If you later fix the generator while still on LVGL 9.5:

```bash
./regenerate_all.sh --dry-run   # tag should be v9.5.1 (or next patch on the 9.5 line)
./regenerate_all.sh
git push origin main --tags
```

You do not need to recheck out `lvgl` unless you are moving to a different LVGL
release. `regenerate_all.sh` bumps only the lvgl-bindings patch tag for the current
LVGL major.minor line.
