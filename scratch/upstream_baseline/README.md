# Upstream baseline scratch harness

`run.sh` runs the pinned `lv_binding_micropython` generator against the
committed preprocessed input and verifies its temporary metadata and C output
against the compact historical baseline. It is a provenance oracle, not a
production regeneration path.

Run it from the repository root:

```sh
scratch/upstream_baseline/run.sh
```

All upstream source and generated output are created under a temporary
directory and removed when the command exits. The command does not rewrite the
baseline. Set `LVGL_BINDINGS_UPSTREAM_REPO` to reuse an existing checkout at
the pinned commit instead of cloning one.
