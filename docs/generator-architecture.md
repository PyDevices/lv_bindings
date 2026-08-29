# Generator architecture

The generator has one target-neutral public contract and three equal-status
native backends. Its pipeline is:

```text
LVGL headers + lv_conf.h
  -> deterministic preprocessing
  -> immutable C declaration IR
  -> canonical Python API model + policy
  -> MicroPython | CircuitPython | CPython lowering
  -> generated C/header + shared stub
```

## Sources of truth

- `lvgl/` and `lv_conf.h` define the C declarations and configured features.
- `requirements.txt` pins `pycparser==3.0`; `fake_libc_include/` is vendored
  from the matching parser release. Parser or fake-libc changes require full
  regeneration and all-target validation.
- `binding/ir.py` is the target-neutral declaration representation.
- `binding/api_model.py` defines the public Python model. The generated,
  schema-versioned `generated/api.json` includes a deterministic content hash.
- `binding/api_policy.json` is the reviewed exception manifest. Unsupported
  public declarations are fatal unless an exact policy entry records the
  declaration, affected targets, reason, and test coverage.
- `binding/emit_pyi_canonical.py` emits `generated/lvgl.pyi` only from
  `generated/api.json`.

Generated C is never edited by hand. The committed outputs are
`lvgl_micropython.c`, `lvgl_circuitpython.c`, `lvgl_circuitpython.h`, and
`lvgl_python.c`. `lvgl.pp` is the deterministic preprocessed translation unit
used for diagnostics and baseline reproduction.

## Shared analysis and backend boundary

`binding.generate` preprocesses and parses once. `binding.generator` snapshots
one immutable declaration IR and canonical API model, then gives the same
snapshot to every selected backend. Parsing, declaration ownership,
inheritance, visibility, naming, target availability, and diagnostics policy
are decided before target lowering.

MicroPython and CircuitPython lower to their shared `mp_obj_t` object API while
retaining separate registration and VM/GC glue. CPython lowers to native
`PyObject *` wrappers and owns GIL, lock, extension initialization, and wheel
integration. Those runtime differences cannot silently change the public API.
Namespace verification compares every generated module to `api.json`.

Internal AST metadata still used while rendering C is per-run implementation
state, not a public IR or a cross-target alignment mechanism. Synthesized
callback declarations that are created after declaration indexing use a narrow
AST fallback solely for receiver classification.

Native emitters read their inputs directly from one `BindingContext` and
publish an explicit `EmitterResult`; they never mirror a run into module
globals. Runtime and CPython-native helper bindings are scoped `ContextVar`
state, so a repeated or nested in-process backend invocation restores its
enclosing context on exit. Isolation tests cover module namespaces, distinct
per-run results, deterministic repeated output, and nested CPython emission.

## Public API policy

All targets use the established upstream-compatible names. There is no
target-specific or alternate naming profile. Generic `Blob` and `Struct`
helpers remain private; concrete reachable LVGL structs, `C_Pointer`,
`LvReferenceError`, lifecycle names, widgets, enums, callbacks, constants, and
variables follow the canonical model.

The current target exceptions are `lv_tjpgd_init` and `lv_tjpgd_deinit`, which
are unavailable on CircuitPython and CPython because those builds exclude the
TJPGD implementation. They are declared in `binding/api_policy.json` and have
policy, namespace, and runtime coverage. The compatibility report must contain
zero unexplained differences.

## Commands and validation

```bash
# Generate all targets or one target
./regenerate_all.sh
./regenerate_all.sh --target micropython
./regenerate_all.sh --target circuitpython
./regenerate_all.sh --target cpython

# Typings only and read-only reproducibility checks
./regenerate_all.sh --pyi-only
./regenerate_all.sh --check --hash

# Repository and release gates
TMPDIR=/tmp/lvgl-bindings-pytest .venv/bin/python -m pytest -q -s tests
./scripts/verify_bindings.sh
./scripts/release_dry_run.sh
```

The API report compares the canonical model to the compact, classified
historical upstream baseline. `scratch/upstream_baseline/run.sh` verifies that
the pinned upstream generator still reproduces that baseline without placing
its source or full outputs in this repository.

Consumer builds are part of integration validation: MicroPython and
CircuitPython begin with the `cmods/build_mp.sh` and `cmods/build_cp.sh`
orchestrators; CPython rebuilds its extension and wheel from the synced source.
See [releasing-bindings.md](releasing-bindings.md) for exact-commit
synchronization and publication boundaries.
