# lvgl-bindings documentation

- [Using LVGL with PyDevices](using-lvgl-with-pydevices.md) — the sister
  projects, wiring `board_config` to LVGL, what `display_driver` does, and the
  sync/async timer contract.
- [Loading fonts at runtime](fonts.md) — the `fonts/*.bin` collection,
  `fs_driver.py`, and converting your own fonts; no firmware rebuild needed.
- [releasing-bindings.md](releasing-bindings.md) — the binding release chain
  (renamed from `publishing.md` — it documents cutting a binding release, not
  package publishing).
- [generator-architecture.md](generator-architecture.md) — source-of-truth
  pipeline, policy, backend boundaries, parser pin, and validation.
- [generator-migration.md](generator-migration.md) — clean-break migration from
  the former per-target commands and metadata artifacts.

See the [root README](../README.md) for the generator itself, and its
["The LVGL family"](../README.md#the-lvgl-family) section for how the four
LVGL repos fit together.
