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

- [x] Work from a dedicated branch, for example
  `lvgl-generator-overhaul`.
- [ ] Before each phase, inspect all four repository statuses and preserve
  unrelated existing changes.
- [x] Never hand-edit generated C. All generated C changes must come from the
  generator and be explained by the canonical model or backend; generator-led
  changes are authorized for this rebuild.
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
- [x] Record lifecycle dunders separately from the metadata baseline; they are
  runtime exports rather than metadata entries.
- [x] Replace the large historical baseline JSON with a deterministic compact
  ``.json.gz`` manifest; keep its reproducible scratch oracle, readable
  Markdown provenance report, and audited classification manifest. Do not
  retain a second uncompressed copy in the repository.

### Gate

- [x] The pinned upstream generator runs against the current LVGL checkout.
- [x] Current generated artifacts remain unchanged.
- [x] The report contains no unexplained current-target differences.

### Handoff

- Commit SHA: `cc7b814`
- Validation command(s): `scratch/upstream_baseline/run.sh docs/baseline`; `PYTHONPATH=. .venv/bin/pytest -q -s tests/test_pyi_generation.py tests/test_pyi_prototypes.py`; all three Unix smoke tests
- Notes: `Name/location coverage: MP 100.00%, CircuitPython 99.99%, CPython 99.90%. Generated binding artifacts unchanged. Upstream widget-method and struct-helper signature metadata remain explicit baseline limitations. Lifecycle dunders are documented separately: MicroPython uses loader hooks, while CircuitPython and CPython keep lifecycle outside the shared public API.`

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
- [x] Represent function declarations, parameters, struct fields, anonymous and
  forward declarations, callbacks, static-inline prototypes, and source
  locations in the declaration IR.
- [x] Parse the preprocessed translation unit once in the unified all-target
  command and pass one immutable declaration IR to each target context.
- [x] Remove target conditions from parsing and analysis.

Progress note: target lowering still uses the legacy AST-facing analysis
surface. The next structural step is to migrate those decisions to the
declaration IR; the current shared snapshot prevents a target from reparsing
or reanalyzing the translation unit while preserving the C output gate.

Constructor and direct widget-method ownership decisions now come from the
shared API model, including exact constructor matching, longest-prefix
ownership, and static-method detection from the first argument. The emitter
still receives AST nodes for C rendering, and the generated-C body gate remains
clean.

The declaration IR now normalizes C ``(void)`` parameter lists, preserves
function specifiers such as ``static inline``, and has focused coverage for
qualified pointers, arrays, callbacks, anonymous records, unions, and forward
aliases. A target-neutral API-model library has been started, but policy,
reachability, and backend lowering remain in Checkpoint 3 and later. The
shared generator now materializes that model as ``generated/api.json`` with a
content hash; the legacy ``lvgl.json`` file remains the C-generator
introspection artifact while the canonical model becomes the source of truth
for Python-facing outputs.

Parsing, declaration analysis, and API-model construction contain no
target-specific branches. Target availability is represented as data in the
policy/model layer, and the remaining target branches are confined to backend
lowering in the emitters.

- [x] Add a read-only declaration index for alias resolution, first-argument
  relationships, and struct-function classification. The index is used by
  legacy-facing queries with an AST fallback for synthetic helper declarations.

### Gate

- [x] All targets consume the same parsed IR.
- [x] No target re-runs analysis.
- [x] C body goldens remain equivalent during the structural refactor.

### Handoff

- Commit SHA: `________________`
- Validation command(s): `PYTHONPATH=. .venv/bin/pytest -q -s tests/test_generation_tools.py`; `PYTHONPATH=. .venv/bin/python -m binding.generate --check`
- Notes: `All three backend entry points receive the same frozen DeclarationIR and canonical API model. The regression test makes a target-side analyze() call fail, so the one parse/analysis boundary cannot silently regress. Parsing, analysis, and API-model construction are target-neutral; target availability is policy data and target branching begins only in backend lowering.`

## Checkpoint 3 — Canonical public API model and policy

### Work

- [x] Build a second model describing the Python API rather than C syntax.
- [x] Record qualified location, Python/C names, parameters, return type,
  constructor/method/module role, enum ownership, aliases, inheritance,
  callbacks, and target availability.
- [x] Add target-neutral conversion classifications and Python type views.
- [x] Record callback/object lifetime semantics from verified runtime behavior.
- [x] Classify methods from declaration relationships and first-argument types,
  not only function-name prefixes.
- [x] Move deliberate deviations into an auditable policy file.
- [x] Require every target exception to include a reason and test reference.
- [x] Generate deterministic, versioned `generated/api.json` with an API hash.
- [x] Add a report command for compatibility and parity metrics.

Progress note: ``binding/api_model.py`` now records C/Python names, normalized
types, declaration locations, object inheritance, callback typedefs, enum
values, visibility, and target availability. ``binding/api_policy.json`` is
validated against the current translation unit and ``generated/api.json`` is
written from the same immutable model shared by all target runs. The
``binding.api_report`` command now reports inheritance-expanded qualified
exports, target availability exceptions, visibility inventory, and a
diagnostic projection against the compact historical baseline. Target-neutral
conversion categories and Python type views now cover function parameters and
returns, struct fields, typedefs, and variables. The model records explicit
callback, object-handle, struct, enum, string, typed-buffer, array,
opaque-pointer, pointer, scalar, void, and unsupported conversions;
``generated/api.json`` is schema version 3 and its validator requires every
boundary type to carry a view. Object typedefs resolve to their public wrapper
types, including opaque ``struct _lv_*_t`` definitions, and anonymous
typedef-backed records resolve through their alias. Explicitly hidden
implementation structs are prevented from leaking into public annotations;
the canonical pyi emitter lowers those views to ``Any`` where necessary.
Runtime evidence now establishes that event callbacks remain callable after
``gc.collect()`` both while their widget wrapper is referenced and after the
wrapper is released and the object is reached again through ``get_child()``.
The shared Unix smoke test passed those cases on MicroPython, CircuitPython,
and CPython. This records callback rooting across the three current runtimes;
nullability, broader object-destruction semantics, reachability, backend
lowering, and acceptance of the compatibility score are still pending.

Interim safe checkpoint: the current model reports 22,997 MicroPython
qualified exports and 22,995 CircuitPython/CPython exports, with two explicit
TJPGD availability exceptions. Its historical name/location projection is
98.58% (21,865/22,179), but the remaining missing/extra entries are not yet
classified for acceptance. The report and validator are therefore diagnostic,
not a completed C3 gate.

Enum ownership is now explicit in the model: module-level exports, nested
widget exports, duplex aliases such as ``OBJ_FLAG``/``obj.FLAG``, and normalized
members are recorded independently of the C emitters. The current generated
API hash after this increment is
``7b40051b4b443ef62cbb91893a6cb971bfc5181cb05be81a7a26e4c16c0dc73d``.

### Gate

- [x] Exact normalized upstream coverage is at least 95%.
- [x] Every difference is classified as a deliberate fix, private-symbol
  removal, or target exception.
- [x] No target is used as the semantic source of truth for another target.
- [x] The common model is identical across targets except listed exceptions.

### Handoff

- Commit SHA: `________________`
- Compatibility score: `98.87% (21,928/22,179)`
- Validation command(s): `PYTHONPATH=. .venv/bin/pytest -q -s tests/test_api_report.py`; `PYTHONPATH=. .venv/bin/python -m binding.api_report generated/api.json --baseline docs/baseline/lvgl-bindings-api-baseline.json.gz --classification docs/baseline/lvgl-bindings-api-baseline-classification.json --format markdown`
- Notes: `The baseline classification manifest covers every missing or extra historical entry. Canonical enum normalization, richer public struct exposure, upstream metadata omissions, and private runtime-helper removal are explicit categories. The shared model precedes all target emitters; the only availability differences are the two audited TJPGD exceptions.`

## Checkpoint 4 — Typings and parity verification

### Work

- [x] Generate `generated/lvgl.pyi` only from the canonical API model.
- [x] Keep legacy names only.
- [x] Accurately represent concrete widgets, structs, enums, callbacks,
  inheritance, and optional constructor parent pointers.
- [x] Accurately represent fixed C arrays as nested ``Sequence[...]`` views.
- [x] Represent overloads where the runtime exposes distinct callable forms.
- [x] Use private underscored types for generic blob/struct internals.
- [x] Exclude explicitly unavailable symbols.
- [x] Replace regex-only namespace checks with manifest-based qualified export
  verification.
- [x] Verify module exports, type/member exports, enum ownership, target
  filtering, and signatures against the canonical manifest.
- [x] Verify enum values, target exceptions, and private helper leakage in the
  pyi/runtime contract.

Progress note: ``binding/emit_pyi_canonical.py`` renders the shared stub from
``generated/api.json`` and validates the model before pyi-only generation.
Common-target emission filters target-only declarations; nested enum classes
are emitted once, struct field/method collisions follow the generated runtime
attribute precedence, string symbols use ``str`` members, explicit private
implementation types do not appear as undefined annotations, fixed C arrays
are represented as nested ``Sequence[...]`` views, class-local private
``TypeAlias`` declarations prevent field names from shadowing type names, and
the runtime helper classes include their actual inheritance and method binding;
``Struct.__cast_instance__`` is an instance method, while ``__dereference__``
accepts the runtime's optional size argument on both ``Struct`` and ``Blob``.
``Struct.__cast__`` is a generic class method taking a target type and pointer;
``Blob.__cast__`` has overloads for raw and typed casts. Its private generic
type variables are explicit verifier allow-list entries, while any other
private top-level declaration is rejected. Both dereference helpers return a
``memoryview | None`` to represent the common all-target contract when a size
cannot be derived. The CPython smoke probe exercises both ``Blob.__cast__``
forms from a valid display flush callback.
Enum expressions and implicit C enum increments are preserved in the canonical
model; stubs expose the correct member type instead of invalid Python literal
expressions. The real exception policy is rendered and manifest-validated for
the common view and each target view, with every TJPGD exception checked
against its exact public stub surface.
Incompatible LVGL widget overrides carry narrowly targeted mypy override
notes. The generated stub parses cleanly and has regression coverage for
signatures, target filtering, duplicate declarations, arrays, aliases, and
annotation references. The pinned ``mypy==2.3.1`` check passes.

### Gate

- [x] Typings unit tests pass.
- [x] The stub parses.
- [x] The stub passes static type checking.
- [x] No duplicate declarations remain.
- [x] Runtime namespace probes pass for all three targets.

### Handoff

- Commit SHA: `a0a4cd6`
- Validation command(s): `PYTHONPATH=. .venv/bin/pytest -q -s tests`; `PYTHONPATH=. .venv/bin/python -m binding.generate --pyi-only --check`; `./scripts/verify_bindings.sh`; `../lvgl-python/.venv/bin/python tools/test_lvgl_smoke.py`; `../cmods/build_mp.sh --port unix --variant standard` + `../cmods/micropython/ports/unix/build-standard/micropython tools/test_lvgl_smoke.py`; `../cmods/build_cp.sh --port unix --variant coverage` + `../cmods/circuitpython/ports/unix/build-coverage/micropython tools/test_lvgl_smoke.py`
- Notes: `The shared lvgl.pyi is emitted exclusively from schema-versioned generated/api.json. Canonical type views cover parameters, returns, fields, typedefs, variables, and fixed arrays; target-only declarations are excluded from the common stub; nested enum duplication and field/method collisions are guarded by tests. Struct fields that shadow type names use private class-local TypeAlias declarations, incompatible inherited widget signatures are marked with targeted mypy override notes, and C_Pointer inherits the runtime Struct helper with __SIZE__. Runtime inspection established that Struct.__cast_instance__ and Struct.__dereference__ are bound instance methods, while Struct.__cast__ is a class method taking a target type and pointer. Struct and Blob dereference both accept an optional size and return memoryview | None in the common all-target contract. Blob.__cast__ has overloads for raw and typed casts; private generic helper types are allow-listed and arbitrary private top-level leakage is rejected. The CPython smoke probe covers both Blob cast forms from a valid display flush callback. The dead legacy pyi emitter and its tests were removed; pyi_prototypes remains only for legacy C-generator metadata enrichment. binding.verify_pyi checks top-level and qualified member names, field/variable/enum annotations, constructors, receivers, static methods, variadics, defaults, aliases, and return types from the manifest; it runs in verify_bindings.sh. requirements-dev.txt pins mypy==2.3.1, and static checking passes. Generated C and CircuitPython header files were unchanged. Cmods builds supplied the missing Unix runtime evidence: MicroPython standard and CircuitPython coverage both built from the workspace and passed the shared smoke test, including widget creation, callbacks, and callback retention through GC.`

## Checkpoint 5 — Unified target backends

### Work

- [x] Define a backend interface driven by the same canonical model; introduce
  shared conversion lowering in the subsequent backend migration.
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
- Notes: `First migration slice: generator-level Backend/BackendRun provides one
  context, output, metadata, and result contract for all three target lowering
  modules. Generated artifacts are unchanged by design; target-specific C
  lowering is still owned by the existing emitter modules. Validation: 96
  repository tests passed; binding.generate --check passed; MicroPython Unix
  standard and CircuitPython Unix coverage rebuilt with cmods and passed the
  shared LVGL smoke probe; CPython smoke probe passed. A repository-wide pytest
  invocation additionally discovers LVGL's vendored upstream tests, which
  require unavailable doxygen, so the intended repository suite is pytest tests.`

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

- [x] Forward declarations and typedef aliases.
- [x] Anonymous structs/unions.
- [x] Qualified pointers and arrays.
- [x] Function pointers and callbacks.
- [x] Static-inline declarations.
- [x] Widget inheritance and method ownership.
- [x] Enum nesting and aliases.
- [x] Duplicate export detection.
- [x] Unsupported conversions.
- [x] Target exception validation.
- [x] Deterministic JSON/API hashes.
- [x] Typing signatures and duplicate declarations.
- [x] Generated-stub static checking.
- [x] Callback GC/lifetime behavior.
- [ ] Struct field reads/writes and buffer views.
- [ ] `None` handling for optional pointers.
- [ ] Cross-target namespace and enum-value parity.

The compatibility report must publish:

- [ ] Exact upstream contract coverage percentage.
- [ ] Common-target API coverage percentage.
- [ ] Target exception count.
- [ ] Unexplained difference count, which must be zero.
- [ ] Per-target generated artifact hashes.
