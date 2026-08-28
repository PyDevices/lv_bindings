# Upstream baseline scratch harness

`run.sh` runs the pinned `lv_binding_micropython` generator against the
current LVGL preprocessed input, generates temporary metadata for each current
target, and writes a normalized report. It is an oracle for the rebuild, not a
production regeneration path.

Run it from the repository root:

```sh
scratch/upstream_baseline/run.sh
```

The default output is `docs/baseline/`. All upstream source, generated C, and
target metadata intermediates are created under a temporary directory and are
removed when the command exits. Set `LVGL_BINDINGS_UPSTREAM_REPO` to reuse an
existing checkout at the pinned commit instead of cloning one.
