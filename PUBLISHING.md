# Publishing lv_bindings

This document describes how to cut a new **lv_bindings** release after moving the
`lvgl` submodule to a different LVGL version.

## Version scheme

lv_bindings tags mirror **LVGL major.minor**. The patch number counts binding
releases on that LVGL line:

| Tag | Meaning |
|-----|---------|
| `v9.5.0` | First lv_bindings release for LVGL 9.5.x |
| `v9.5.1` | Second lv_bindings release still on LVGL 9.5.x |
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

1. Regenerates `generated/lvmp.c`, `generated/lvcp.c`, and `generated/lvpy.c`
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
./verify_bindings.sh
```

Run this before publishing when you change the generator or LVGL config
(`lv_conf.h`), or when cutting a major LVGL bump.

## Downstream consumers

Pushing binding changes on **`main`** can trigger automated sync in consumer
repos. See [README.md](README.md) for details on:

- [lv_micropython_cmod](https://github.com/PyDevices/lv_micropython_cmod)
- [lv_circuitpython_mod](https://github.com/PyDevices/lv_circuitpython_mod)
- [lv_cpython_mod](https://github.com/PyDevices/lv_cpython_mod) (auto-release on
  `generated/lvpy.c`, `lv_conf.h`, or `lvgl` pin changes)

After tagging, consumer repos can pin to a specific lv_bindings release with
`git checkout v9.5.0` (or sync scripts that reference that tag).

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
# lvgl unchanged
./regenerate_all.sh
# → tag v9.5.1
git push origin main --tags
```
