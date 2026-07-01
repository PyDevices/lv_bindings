# AGENTS.md — lv_bindings

Generator repo for LVGL → C bindings (`generated/lvmp.c`, `generated/lvcp.c`, `generated/lvpy.c`).

## Full build & test matrix

MicroPython, CircuitPython, and CPython builds are orchestrated from the **cmods** workspace root. See **[../AGENTS.md](../AGENTS.md)** for:

- **“Build them all”** — targets 1–4 in parallel, then Windows CPython (step 5) alone
- Smoke test commands for each port
- `pip.exe` / `python.exe` vs `.venv/bin/pip` rules

## This repo only

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

./regenerate_all.sh --dry-run   # preview tag/commit
./regenerate_all.sh             # regen all + commit + tag
./verify_bindings.sh            # regen + regression checks
```

Publishing: [PUBLISHING.md](PUBLISHING.md)
