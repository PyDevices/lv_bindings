# Publishing lv_bindings

This document describes how to cut a new **lv_bindings** release after moving the
`lvgl` submodule to a different LVGL version.

## Version scheme

lv_bindings tags mirror **LVGL major.minor**. The patch number counts binding
releases on that LVGL line:


| Tag      | Meaning                                                 |
| -------- | ------------------------------------------------------- |
| `v9.5.0` | First lv_bindings release for LVGL 9.5.x                |
| `v9.5.1` | Second lv_bindings release still on LVGL 9.5.x          |
| `v9.4.0` | First lv_bindings release after switching to LVGL 9.4.x |


The tag does **not** copy LVGL's patch version. LVGL `v9.5.0` and `v9.5.2` both
map to the **9.5** lv_bindings line; the lv_bindings patch increments only when
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

Shows the planned lv_bindings tag, commit message, and whether `lvgl` /
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

- [lv_micropython_cmod](https://github.com/PyDevices/lv_micropython_cmod) — sync
  `generated/lvgl_micropython.c`, `lvgl/`, `lv_conf.h`
- [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod) — sync
  `generated/lvgl_circuitpython.c`, `generated/lvgl_circuitpython.h`, `lvgl/`,
  `lv_conf.h`
- [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod) — sync
  `generated/lvgl_python.c`, `lvgl/`, `lv_conf.h`; see
  [CPython auto-release](#cpython-auto-release-lv_cpython_mod) below

After tagging, consumer repos can pin to a specific lv_bindings release with
`git checkout v9.5.0` (or sync scripts that reference that tag).

## CPython auto-release (lv_cpython_mod)

When `generated/lvgl_python.c`, `lv_conf.h`, or the `lvgl` submodule pin changes on `main`, the [trigger-lv-cpython-mod-release](.github/workflows/trigger-lv-cpython-mod-release.yml) workflow starts **Sync and release** on [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod) (sync → commit → tag → TestPyPI).

### Setup

Add repository secret **`LVCPYTHON_MOD_DISPATCH_TOKEN`** (Settings → Secrets → Actions):
a PAT with **`actions:write`** on `PyDevices/lv_cpython_mod` (fine-grained or classic
`repo` scope).

### Manual sync

Without pushing to `main`, or for local testing, run in `lv_cpython_mod`:

```bash
./scripts/sync_from_lv_bindings.sh
```

## Example session

```bash
cd lvgl && git fetch --tags origin && git checkout v9.5.0 && cd ..

./regenerate_all.sh --dry-run
# LVGL submodule: v9.5.0 (API 9.5.0)
# lv_bindings tag: v9.5.0
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
release. `regenerate_all.sh` bumps only the lv_bindings patch tag for the current
LVGL major.minor line.
