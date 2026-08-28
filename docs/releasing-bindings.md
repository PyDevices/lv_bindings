# Releasing lvgl-bindings

Bindings releases mirror the LVGL major/minor API line and use an independent
patch counter. The current line is `9.5.N`; `N` advances for each bindings
release regardless of LVGL's own patch number.

## Separation of responsibilities

The normal generator is deliberately non-releasing:

```bash
./regenerate_all.sh
./regenerate_all.sh --target micropython
./regenerate_all.sh --target circuitpython
./regenerate_all.sh --target cpython
./regenerate_all.sh --pyi-only
./regenerate_all.sh --check --hash
```

None of those commands commits, tags, pushes, dispatches another repository, or
publishes a package. `--check` generates into a temporary directory and compares
the result with committed artifacts.

## Release gate

Run the complete non-mutating gate before any release action:

```bash
./scripts/release_dry_run.sh
```

It runs all generator tests, regenerates and compares every artifact, validates
the canonical API/stub/namespace contracts, prints artifact hashes, and checks
that the expected version is on the `9.5.N` line. Its final output explicitly
confirms that no publication or git-history mutation occurred.

Preview the version alone:

```bash
./scripts/next_release_version.sh --verbose
```

## Explicit tag creation

After committing reviewed artifacts, tag only through the dedicated command:

```bash
./scripts/publish_release_tag.sh --dry-run
./scripts/publish_release_tag.sh          # create locally
./scripts/publish_release_tag.sh --push   # explicit remote mutation
```

The command rejects a dirty tree, invalid version, or existing tag. Tagging is
never part of regeneration.

## Coordinated CPython release

The **Release bindings** GitHub workflow is manual. It requires an exact full
bindings commit SHA or `vX.Y.Z` tag, performs the same dry-run gate, resolves the
source to a full commit SHA, and reports the expected version. Its `publish`
input defaults to false.

Only an explicit run with `publish=true` dispatches `lvgl-python` in release
mode. A normal push to `main` does not create downstream commits, tags,
releases, or TestPyPI uploads.

## Downstream source identity

Each consumer records the exact source in `LVGL_BINDINGS_COMMIT`:

- `lvgl-micropython` verifies the generated MicroPython C, LVGL submodule, and
  `lv_conf.h` against that commit in Make and CMake builds.
- `lvgl-circuitpython` verifies the generated CircuitPython C and header, LVGL
  submodule, and `lv_conf.h` before patch builds.
- `lvgl-python` vendors generated C/stubs/config/helpers/LVGL and records the
  resolved commit in its package source.

Consumer sync scripts reject symbolic branch names. Pass either a full
40-character commit SHA or an immutable release tag:

```bash
./scripts/sync_from_lvgl_bindings.sh --ref <40-character-commit-sha>
./scripts/sync_from_lvgl_bindings.sh --ref v9.5.N
```

## Publication boundary

`lvgl-bindings` publishes source tags, not wheels. `lvgl-python` is the package
endpoint for Linux, Windows, Android, WebAssembly, and other configured release
platforms. MicroPython and CircuitPython consume the exact generated source in
their port build systems and do not publish Python wheels.
