# Generator rebuild migration

This rebuild is an intentional clean break. It replaces per-target command
paths and MicroPython-shaped metadata alignment with one canonical generator.

## Command changes

Use `python -m binding.generate` or `regenerate_all.sh`. The removed
`binding/gen_binding.py`, `regenerate_lvmp.sh`, `regenerate_lvcp.sh`, and
`regenerate_lvpy.sh` commands have no compatibility wrappers.

| Former operation | Current operation |
| --- | --- |
| Generate one target with a target script | `./regenerate_all.sh --target TARGET` |
| Generate targets independently | `./regenerate_all.sh` |
| Emit or align `lvgl.json` metadata | Read `generated/api.json` |
| Regenerate typings through prototype enrichment | `./regenerate_all.sh --pyi-only` |
| Compare full generated baseline snapshots | Run `binding.api_report` against `docs/baseline/` |

The former Pythonic naming experiment was also removed. The public API has one
upstream-compatible spelling across all targets.

## Artifact changes

`generated/lvgl.json` and `generated/baseline/` were removed. They duplicated
an emitter-shaped, MicroPython-first view and several megabytes of generated C.
The durable compatibility record is the compact
`docs/baseline/lvgl-bindings-api-baseline.json.gz`, its readable provenance
report, and its audited classification manifest. `generated/api.json` is the
current public contract; it drives typings and parity validation.

The generated C bodies retain their runtime behavior. Cleanup changes their
header command only, so it names the command that actually generated them.

## Consumer migration

Each consumer sync script accepts only a full 40-character bindings commit or
an immutable release tag and records the resolved commit in
`LVGL_BINDINGS_COMMIT`. Build integration verifies the generated source, LVGL
submodule, and configuration against that pin.

- MicroPython consumes a user C module for Unix, Windows, WebAssembly, and MCU
  ports.
- CircuitPython consumes generated source/header patches for its available
  Unix and MCU ports; the currently pinned source tree has no Windows port.
- CPython consumes the native extension and ABI-named stub in wheels for Unix,
  Windows, Android, and other configured release platforms.

The packaging mechanisms differ, but no consumer is the reference target. API
differences must be explicit policy exceptions rather than consequences of a
consumer's build system.
