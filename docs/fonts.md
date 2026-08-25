# Loading fonts at runtime

How to use fonts that are **not** compiled into your build, with
[`fonts/*.bin`](../fonts/) and [`python/fs_driver.py`](../python/fs_driver.py).
Works identically on all three consumers (lvgl-micropython,
lvgl-circuitpython, lvgl-python).

## Why runtime fonts

Space-constrained builds enable only a few `LV_FONT_MONTSERRAT_*` entries in
`lv_conf.h`. Every other built-in font is available in this repo's
[`fonts/`](../fonts/) directory in LVGL's binary font format — same glyph
ranges, same merged FontAwesome symbols (`lv.SYMBOL.*`), same bpp as its
compiled-in counterpart. Copy a `.bin` to the board and load it; no firmware
rebuild, no `lv_conf.h` change, no binding regeneration.

The trade-off: a compiled-in font lives in flash and costs no RAM, while a
loaded font is parsed into the heap (roughly its file size — see the sizes in
`fonts/`; Montserrat runs ~7–97 KB by size, the CJK fonts ~160–195 KB). Keep
your everyday fonts compiled in; load the occasional large size, or a script
you only sometimes need, at runtime.

## Getting a font onto the board

```bash
curl -LO https://raw.githubusercontent.com/PyDevices/lvgl-bindings/main/fonts/montserrat_20.bin
mpremote cp montserrat_20.bin :
```

On desktop (lvgl-python), just keep the `.bin` next to your script.

## Loading with fs_driver (recommended)

`fs_driver.py` registers a Python-backed LVGL filesystem driver: LVGL's
file API (`lv_fs`) calls back into Python's `open()`/`read()`/`seek()`, so it
reaches whatever filesystem the interpreter sees — MicroPython VFS (including
SD cards and ROMFS), CircuitPython storage, or the host OS — without enabling
any `LV_USE_FS_*` C driver.

```python
import lvgl as lv
import fs_driver

fs_driver.register("S")                       # drive letter, once at startup
font = lv.binfont_create("S:montserrat_20.bin")

label = lv.label(lv.screen_active())
label.set_text("Hello " + lv.SYMBOL.OK)
label.set_style_text_font(font, 0)
```

- The drive letter is arbitrary; `register()` is idempotent per letter and
  returns the `lv.fs_drv_t` it owns.
- Everything after `S:` is passed to `open()` verbatim: `S:montserrat_20.bin`
  is relative to the current directory, `S:/sd/fonts/montserrat_20.bin` is
  absolute.
- The font streams from the file in small reads, so peak RAM during load is
  just the parsed font — the whole file is never buffered. This is the reason
  to prefer `fs_driver` over `binfont_create_from_buffer` on small boards.
- `lv.binfont_create` returns `None` on failure (bad path, truncated file).
- Free a font you no longer need with `lv.binfont_destroy(font)` — after
  removing it from any styles that still reference it.

The driver is general `lv_fs` plumbing, not font-specific: once registered,
image sources like `lv.image.set_src("S:logo.png")` work through it too.

### Where fs_driver comes from

The canonical copy is `python/fs_driver.py` in this repo. Each consumer
ships a synced copy the same way as `display_driver.py`: frozen into
lvgl-micropython and lvgl-circuitpython builds, `py_modules` in the
lvgl-python wheel — so `import fs_driver` just works. For a stock MicroPython
board it is also mip-installable:

```python
mip.install("github:PyDevices/lvgl-bindings/packages/fs_driver.json")
```

## Loading from a buffer (no driver)

When the file is small or already in memory, skip the driver:

```python
data = open("montserrat_20.bin", "rb").read()
font = lv.binfont_create_from_buffer(data, len(data))
```

This briefly holds both the file contents and the parsed font in RAM; the
`data` reference can be dropped afterwards. It is also the right tool for
font bytes that arrive from somewhere other than a file (network, frozen
module, ROMFS `memoryview`).

## Converting your own fonts

Any TTF/WOFF can be converted with
[lv_font_conv](https://github.com/lvgl/lv_font_conv) — pick only the glyphs
you need to keep the file (and heap cost) small:

```bash
npx lv_font_conv --font MyFont.ttf --size 20 --bpp 4 \
    -r 0x20-0x7F --no-compress --format bin -o myfont_20.bin
```

Keep `--no-compress` unless your build enables `LV_USE_FONT_COMPRESSED`.

## Regenerating fonts/

[`scripts/generate_font_bins.py`](../scripts/generate_font_bins.py) rebuilds
every `.bin` by replaying the recipes from the LVGL submodule's own
`lvgl/scripts/built_in_font/generate_all.py`, so ranges and symbol sets track
the pinned LVGL version. Rerun it after bumping the `lvgl` pin:

```bash
./scripts/generate_font_bins.py                     # everything
./scripts/generate_font_bins.py --only montserrat_20
```

It needs `lv_font_conv` on PATH, or node/npx to fetch it. The subpixel and
compressed Montserrat variants are intentionally skipped — `LV_USE_FONT_SUBPX`
and `LV_USE_FONT_COMPRESSED` are off in our `lv_conf.h`, so the loader could
not render them.

## Font licenses

The `.bin` fonts embed the same faces as the LVGL built-ins: Montserrat (OFL),
FontAwesome (OFL/CC BY), DejaVu (Bitstream Vera/public domain), unscii
(public domain), Source Han Sans (OFL). Full texts:
`lvgl/scripts/built_in_font/font_license/`.
