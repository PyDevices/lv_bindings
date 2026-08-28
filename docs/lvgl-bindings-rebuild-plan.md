# LVGL bindings generator rebuild plan

This is the working implementation checklist for rebuilding the LVGL binding
generator across MicroPython, CircuitPython, and CPython. Check off an item only
after its gate passes. Record the commit SHA and validation evidence at every
checkpoint so work can safely continue in a fresh context.

## Decisions

- [x] Changes may span `lvgl-bindings`, `lvgl-micropython`,
  `lvgl-circuitpython`, and `lvgl-python`.
- [x] Use one target-neutral pipeline:
  `preprocess -> parse -> canonical API model -> target lowering -> emit`.
- [x] Use upstream-style legacy names only.
- [x] Keep upstream's widget/struct method layout and module functions; do not
  add CPython-only module-level struct-function aliases.
- [x] Target exceptions are explicit absence, recorded in a machine-checked
  exception manifest.
- [x] Generic `Blob`/`Struct` helpers are private implementation types;
  concrete LVGL structs remain public.
- [x] Keep the LVGL-matched release scheme: `9.5.N`, not a bindings-only major
  version.
- [x] Measure upstream compatibility by exact normalized API
  name/location/signature coverage, not generated-C text similarity.
- [x] Keep compact baseline manifest and provenance; do not vendor the full
  upstream generator and generated outputs.
- [x] Run Linux all-target generator/build/smoke validation on pull requests;
  retain broad CPython platform validation for releases.
- [x] Pin `pycparser==3.0` with matching fake-libc headers after validating
  output compatibility.
- [x] Treat the rebuild as a clean break; legacy generator scripts and command
  shapes do not need compatibility wrappers.

## Packaging and platform scope

The generator serves three target integrations with different downstream
packaging models. These differences must not create target-specific API
contracts; they belong in the target backend, consumer integration, and
platform validation layers.

| Target | Integration form | Platform scope |
| --- | --- | --- |
| MicroPython | User C module | Unix, Windows, WebAssembly, and MCU ports |
| CircuitPython | Patches to the CircuitPython tree | Unix, Windows, and MCU ports |
| CPython | Native extension and wheels | Unix, Windows, Android, and additional supported platforms as they are identified |

The platform lists are an initial scope, not an exhaustive promise of every
downstream build. Release validation should derive the maintained matrix from
the consumer repositories and packaging workflows. Platform-specific build
constraints, unavailable features, and lifecycle differences must be explicit
and machine-checked without changing the shared canonical API contract.

## Working rules

- [ ] Work from a dedicated branch, for example
  `lvgl-generator-overhaul`.
- [ ] Before each phase, inspect all four repository statuses and preserve
  unrelated existing changes.
- [ ] Never hand-edit generated C. All generated C changes must come from the
  generator and be explained by the canonical model or backend.
- [ ] Do not commit changes in upstream MicroPython or CircuitPython clones.
- [ ] At each checkpoint, run the listed gate, record the result, commit only
  that phase, and save the commit SHA below.
- [ ] After each successful checkpoint, compact context or start a fresh agent
  with this file plus the checkpoint notes.

## Checkpoint 0 — Baseline and provenance

### Work

- [x] Pin the upstream reference to `gen_mpy.py` commit
  `60dfbd41f99c2757d1fe3bffab246c818afebcc4`.
- [x] Record the LVGL submodule SHA, `lv_conf.h` hash, compiler flags, parser
  version, and fake-libc hash.
- [x] Add a scratch-only upstream baseline reproducer.
- [x] Produce a normalized upstream API manifest and comparison report for all
  three current targets.
- [x] Record known differences: `OBJ_FLAG`, private `global_t`, CPython
  struct aliases, TJPGD, and GC helpers.
- [ ] Record lifecycle dunders separately from the metadata baseline; they are
  runtime exports rather than metadata entries.
- [ ] Plan removal of the large duplicated historical baseline artifacts after
  the new oracle is stable.

### Gate

- [x] The pinned upstream generator runs against the current LVGL checkout.
- [x] Current generated artifacts remain unchanged.
- [x] The report contains no unexplained current-target differences.

### Handoff

- Commit SHA: `cc7b814`
- Validation command(s): `scratch/upstream_baseline/run.sh docs/baseline`; `PYTHONPATH=. .venv/bin/pytest -q -s tests/test_pyi_generation.py tests/test_pyi_prototypes.py`; all three Unix smoke tests
- Notes: `Name/location coverage: MP 100.00%, CircuitPython 99.99%, CPython 99.90%. Generated binding artifacts unchanged. Upstream widget-method and struct-helper signature metadata remain explicit baseline limitations; lifecycle dunders remain a pending runtime-export audit.`

## Checkpoint 1 — Toolchain and test foundation

### Work

- [x] Update `/home/brad/gh/pydevices/lvgl-bindings/requirements.txt` to
  `pycparser==3.0`.
- [x] Vendor or refresh fake-libc headers from the matching pycparser release.
- [x] Add deterministic preprocessing and artifact hashing.
- [x] Add a unified generator command for all targets.
- [x] Preserve a `pyi-only` path for typing-only regeneration.
- [x] Add a read-only check command that generates into a temporary directory.
- [x] Add parser and generator fixture tests.
- [x] Add initial Linux CI for generator tests and current-output checks.

### Gate

- [x] All existing typings tests pass.
- [x] The current generated C bodies and metadata remain compatible.
- [x] Existing MicroPython, CircuitPython, and CPython smoke tests pass.

### Handoff

- Commit SHA: `e64be1b`
- Validation command(s): `PYTHONPATH=. .venv/bin/pytest -q -s tests`; `PYTHONPATH=. .venv/bin/python -m binding.generate --check`; `./scripts/verify_bindings.sh`; target C-body equivalence check; artifact-manifest check
- Notes: `Pinned pycparser 3.0 and refreshed matching fake-libc headers. The unified command now owns deterministic preprocessing, all-target generation, pyi-only generation, read-only checks, and artifact hashing. Regenerated metadata/stubs include the current analyzer's richer enrichment fields while public API counts remain stable; target C bodies remain equivalent aside from stable command banners. The full repository pytest suite still includes LVGL Doxygen tests and requires doxygen, so CI scopes generator tests to tests/.`

## Checkpoint 2 — Target-neutral C declaration IR

### Work

- [ ] Replace global mutable analyzer state with pure typed intermediate
  representations.
- [x] Represent primitive, qualified, pointer, array, function-pointer, enum,
  struct, union, and typedef types in `binding/ir.py`.
- [ ] Represent function declarations, parameters, struct fields, anonymous and
  forward declarations, callbacks, static-inline prototypes, and source
  locations.
- [x] Represent function declarations, parameters, struct fields, callbacks,
  static-inline prototypes, and source locations in the declaration IR.
- [x] Parse the preprocessed translation unit once in the unified all-target
  command and pass one immutable declaration IR to each target context.
- [ ] Remove target conditions from parsing and analysis.

Progress note: target lowering still uses the legacy AST-facing analysis
surface. The next structural step is to migrate those decisions to the
declaration IR; the current shared snapshot prevents a target from reparsing
or reanalyzing the translation unit while preserving the C output gate.

### Gate

- [ ] All targets consume the same parsed IR.
- [ ] No target re-runs analysis.
- [ ] C body goldens remain equivalent during the structural refactor.

### Handoff

- Commit SHA: `________________`
- Validation command(s): `________________`
- Notes: `____________________________________________________________`

## Checkpoint 3 — Canonical public API model and policy

### Work

- [ ] Build a second model describing the Python API rather than C syntax.
- [ ] Record qualified location, Python/C names, parameters, return type,
  constructor/method/module role, enum ownership, aliases, inheritance,
  callbacks, conversions, lifetime semantics, and target availability.
- [ ] Classify methods from declaration relationships and first-argument types,
  not only function-name prefixes.
- [ ] Move deliberate deviations into an auditable policy file.
- [ ] Require every target exception to include a reason and test reference.
- [ ] Generate deterministic, versioned `generated/api.json` with an API hash.
- [ ] Add a report command for compatibility and parity metrics.

### Gate

- [ ] Exact normalized upstream coverage is at least 95%.
- [ ] Every difference is classified as a deliberate fix, private-symbol
  removal, or target exception.
- [ ] No target is used as the semantic source of truth for another target.
- [ ] The common model is identical across targets except listed exceptions.

### Handoff

- Commit SHA: `________________`
- Compatibility score: `________________`
- Validation command(s): `________________`
- Notes: `____________________________________________________________`

## Checkpoint 4 — Typings and parity verification

### Work

- [ ] Generate `generated/lvgl.pyi` only from the canonical API model.
- [ ] Keep legacy names only.
- [ ] Accurately represent concrete widgets, structs, enums, callbacks,
  inheritance, optional pointers, arrays, and overloads.
- [ ] Use private underscored types for generic blob/struct internals.
- [ ] Exclude explicitly unavailable symbols.
- [ ] Replace regex-only namespace checks with manifest-based qualified export
  verification.
- [ ] Verify module exports, type/member exports, enum ownership/values,
  signatures, exceptions, and private helper leakage.

### Gate

- [ ] Typings unit tests pass.
- [ ] The stub parses and passes static type checking.
- [ ] No duplicate declarations or overloads remain.
- [ ] Runtime namespace probes pass for all three targets.

### Handoff

- Commit SHA: `________________`
- Validation command(s): `________________`
- Notes: `____________________________________________________________`

## Checkpoint 5 — Unified target backends

### Work

- [ ] Define a backend interface driven by the same canonical model and
  conversion plan.
- [ ] Keep MicroPython-specific responsibilities limited to `mp_obj_t`, VM
  roots, and module registration.
- [ ] Keep CircuitPython-specific responsibilities limited to module
  registration, lifecycle glue, and CircuitPython build integration.
- [ ] Keep CPython-specific responsibilities limited to native `PyObject`, GIL/
  lock handling, and module initialization.
- [ ] Share argument conversion, return conversion, struct wrappers, callbacks,
  enum generation, inheritance, function reuse, and errors.
- [ ] Eliminate the duplicated emitter architecture represented by
  `emit_c_micropython_style.py` and `emit_c_cpython.py`.
- [ ] Remove the `runtime.py` module-global mirroring architecture after the
  backend interface is proven.

### Gate

- [ ] All generated files compile for all three targets.
- [ ] All three Linux smoke tests pass after each backend migration.
- [ ] Every generated C diff is explained by the canonical model/backend.

### Handoff

- Commit SHA: `________________`
- Validation command(s): `________________`
- Notes: `____________________________________________________________`

## Checkpoint 6 — Semantic and API corrections

### Work

- [ ] Remove CPython-only module-level struct-function aliases.
- [ ] Remove generated lifecycle dunders from the public contract; retain
  `init`, `deinit`, and `is_initialized`.
- [ ] Remove private GC helpers and internal wrapper types from public exports.
- [ ] Make `C_Pointer` and `LvReferenceError` consistent across targets.
- [ ] Keep the intentional `OBJ_FLAG` module-level alias.
- [ ] Keep concrete LVGL struct types and their methods.
- [ ] Make enum nesting and aliases deterministic.
- [ ] Represent TJPGD and similar build conflicts as explicit target
  exceptions.
- [ ] Correct callback rooting, callback deletion, object lifetime, `None`
  handling, pointer validation, array conversion, and struct field access.
- [ ] Turn unsupported functions into hard diagnostics unless explicitly waived
  by policy.

### Gate

- [ ] The common API is identical across targets except reviewed exceptions.
- [ ] Every exception has a runtime test.
- [ ] Every conversion family has runtime coverage.
- [ ] Generated typings match the final runtime contract.

### Handoff

- Commit SHA: `________________`
- Common API score: `________________`
- Exception count: `________________`
- Validation command(s): `________________`
- Notes: `____________________________________________________________`

## Checkpoint 7 — Consumer integration, CI, and release workflow

### Work

- [ ] Update `lvgl-micropython` build paths, checks, tests, and documentation.
- [ ] Update `lvgl-circuitpython` generated-header integration, lifecycle glue,
  registration, tests, and documentation.
- [ ] Update `lvgl-python` runtime helpers, stub installation, extension tests,
  packaging, and documentation.
- [ ] Add Linux PR validation for generator tests, all-target generation,
  parity, MicroPython Unix, CircuitPython Unix, and CPython builds/smoke tests.
- [ ] Validate MicroPython user-C-module builds for supported Unix, Windows,
  WebAssembly, and MCU ports.
- [ ] Validate CircuitPython patch builds for supported Unix, Windows, and MCU
  ports.
- [ ] Keep CPython extension and wheel testing for supported Unix, Windows,
  Android, and additional release platforms in release workflows.
- [ ] Separate generation/checking from release mutation.
- [ ] Ensure release tooling validates the matrix, computes the next `9.5.N`
  version, and creates commits/tags only when explicitly invoked.
- [ ] Ensure downstream sync consumes an exact bindings commit or tag.

### Gate

- [ ] A release dry run generates all artifacts and passes every check.
- [ ] The expected LVGL-matched `9.5.N` version is produced.
- [ ] No external publication occurs during implementation validation.

### Handoff

- Bindings commit SHA: `________________`
- MicroPython commit SHA: `________________`
- CircuitPython commit SHA: `________________`
- CPython commit SHA: `________________`
- Validation command(s): `________________`
- Notes: `____________________________________________________________`

## Checkpoint 8 — Cleanup and final handoff

### Work

- [ ] Remove dead legacy emitters and analyzer paths.
- [ ] Remove target-specific metadata alignment hacks.
- [ ] Remove stale MicroPython-shaped IR terminology.
- [ ] Remove obsolete full baseline C artifacts.
- [ ] Update all documentation to describe the target-neutral architecture.
- [ ] Document policy, exceptions, parser pins, commands, synchronization, and
  migration notes.

### Final gate

- [ ] All four repositories contain only intentional changes.
- [ ] All generated artifacts are reproducible.
- [ ] All unit tests, builds, smoke tests, and parity checks pass.
- [ ] The API report contains zero unexplained differences.
- [ ] The final commit SHA is recorded below.

### Final handoff

- Bindings commit SHA: `________________`
- MicroPython commit SHA: `________________`
- CircuitPython commit SHA: `________________`
- CPython commit SHA: `________________`
- Final validation report: `________________`
- Remaining follow-up: `________________________________________________`

## Test inventory

Add focused tests for:

- [ ] Forward declarations and typedef aliases.
- [ ] Anonymous structs/unions.
- [ ] Qualified pointers and arrays.
- [ ] Function pointers and callbacks.
- [ ] Static-inline declarations.
- [ ] Widget inheritance and method ownership.
- [ ] Enum nesting and aliases.
- [ ] Duplicate export detection.
- [ ] Unsupported conversions.
- [ ] Target exception validation.
- [ ] Deterministic JSON/API hashes.
- [ ] Typing signatures and duplicate declarations.
- [ ] Callback GC/lifetime behavior.
- [ ] Struct field reads/writes and buffer views.
- [ ] `None` handling for optional pointers.
- [ ] Cross-target namespace and enum-value parity.

The compatibility report must publish:

- [ ] Exact upstream contract coverage percentage.
- [ ] Common-target API coverage percentage.
- [ ] Target exception count.
- [ ] Unexplained difference count, which must be zero.
- [ ] Per-target generated artifact hashes.
