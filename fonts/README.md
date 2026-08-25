# Runtime-loadable fonts

Every LVGL built-in font, pre-converted to LVGL's binary font format
(`lv_font_conv --format bin`). These load at runtime on any of the three
consumers (lvgl-micropython, lvgl-circuitpython, lvgl-python) — no firmware
rebuild, no `lv_conf.h` change. Each font mirrors its built-in counterpart
exactly: same glyph ranges, same merged FontAwesome symbol set (`lv.SYMBOL.*`),
same bpp. The subpixel and compressed Montserrat variants are omitted because
our builds disable `LV_USE_FONT_SUBPX` and `LV_USE_FONT_COMPRESSED`.

Built-in fonts live in flash and cost no RAM; a loaded `.bin` font is parsed
into the heap (roughly its file size). Keep the everyday fonts compiled in and
load the occasional size or script from here.

## Usage

Copy a font to the board (or keep it next to your desktop script):

```bash
curl -LO https://raw.githubusercontent.com/PyDevices/lvgl-bindings/main/fonts/montserrat_20.bin
mpremote cp montserrat_20.bin :
```

Load it by streaming through `fs_driver` (lowest peak RAM; the file is never
fully buffered):

```python
import lvgl as lv
import fs_driver

fs_driver.register("S")
font = lv.binfont_create("S:montserrat_20.bin")
label.set_style_text_font(font, 0)
```

or, without any driver, from a buffer:

```python
data = open("montserrat_20.bin", "rb").read()
font = lv.binfont_create_from_buffer(data, len(data))
```

`lv.binfont_destroy(font)` frees a font you no longer need.

## Regenerating

```bash
./scripts/generate_font_bins.py                 # everything
./scripts/generate_font_bins.py --only montserrat_20 unscii_8
```

The script replays the recipes from the LVGL submodule's own
`lvgl/scripts/built_in_font/generate_all.py`, so ranges and symbols track the
pinned LVGL version. Rerun it after bumping the `lvgl` pin. It needs
`lv_font_conv` on PATH or node/npx to fetch it.

## Licenses

Same faces as the LVGL built-ins: Montserrat (OFL), FontAwesome (OFL/CC BY),
DejaVu (Bitstream Vera/public domain), unscii (public domain), Source Han Sans
(OFL). Full texts: `lvgl/scripts/built_in_font/font_license/`.
