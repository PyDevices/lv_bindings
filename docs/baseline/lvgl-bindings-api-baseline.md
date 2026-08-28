# LVGL bindings API baseline

This is a compact, normalized comparison of the pinned upstream
MicroPython generator against the three current target generators.
It compares API names, locations, and normalized signatures; generated
C text is intentionally not used as the compatibility metric.

## Provenance

- Upstream generator: `https://github.com/lvgl/lv_binding_micropython.git` at `60dfbd41f99c2757d1fe3bffab246c818afebcc4`
- LVGL: `9.5.0` (`v9.5.0`) at `85aa60d18b3d5e5588d7b247abf90198f07c8a63`
- `lv_conf.h` SHA-256: `868fca93c7d770e5ede01c3d36a4d7d6bee4623fd753a4c5ad4bdb9499070cf4`
- Preprocessed input SHA-256: `e6fea03424f4aaab5d92c643406ffc801a274e57373912a5e4c8442233fa065f`
- Fake-libc tree SHA-256: `78028b76023274d20fbe5889b7d113d581468de2208f4b17069be292c81e9b84`
- Parser: `pycparser 2.21`
- Preprocessor: `/usr/bin/gcc -E -DPYCPARSER -I fake_libc_include`

## Normalized baseline counts

| Section | Count |
| --- | ---: |
| `blob` | 72 |
| `constant` | 28 |
| `enum` | 788 |
| `module` | 307 |
| `object` | 20856 |
| `struct` | 128 |

## Target comparison

The name/location score is common entries divided by baseline entries.
The signature score is limited to module functions: upstream metadata
uses a different internal representation for widget methods, and its
metadata writer explicitly leaves struct helper methods as a TODO.

| Target | Name/location | Baseline entries | Target entries | Name/location coverage | Module signature coverage | Missing | Extra | Signature differences |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| circuitpython | 22176 | 22179 | 22210 | 99.99% | 67.21% | 3 | 34 | 100 |
| cpython | 22156 | 22179 | 23001 | 99.90% | 66.89% | 23 | 845 | 100 |
| micropython | 22178 | 22179 | 22212 | 100.00% | 67.43% | 1 | 34 | 100 |

## Differences recorded in this baseline

### circuitpython

- Missing from target: `module.function.tjpgd_deinit`, `module.function.tjpgd_init`, `struct.global_t`
- Extra in target: `enum.OBJ_FLAG`, `enum.OBJ_FLAG.ADV_HITTEST`, `enum.OBJ_FLAG.CHECKABLE`, `enum.OBJ_FLAG.CLICKABLE`, `enum.OBJ_FLAG.CLICK_FOCUSABLE`, `enum.OBJ_FLAG.EVENT_BUBBLE`, `enum.OBJ_FLAG.EVENT_TRICKLE`, `enum.OBJ_FLAG.FLEX_IN_NEW_TRACK`, … (+26)
- Module-function signature differences: `module.function.anim_delete`, `module.function.anim_get`, `module.function.async_call`, `module.function.async_call_cancel`, `module.function.bin_decoder_close`, `module.function.bin_decoder_get_area`, `module.function.bin_decoder_info`, `module.function.bin_decoder_open`, … (+92)

### cpython

- Missing from target: `blob._nesting`, `module.function.mp_lv_deinit_gc`, `module.function.mp_lv_get_roots`, `module.function.mp_lv_init_gc`, `module.function.tjpgd_deinit`, `module.function.tjpgd_init`, `struct.C_Pointer`, `struct._lv_mp_int_wrapper`, … (+15)
- Extra in target: `blob.SYMBOL_AUDIO`, `blob.SYMBOL_BACKSPACE`, `blob.SYMBOL_BARS`, `blob.SYMBOL_BATTERY_1`, `blob.SYMBOL_BATTERY_2`, `blob.SYMBOL_BATTERY_3`, `blob.SYMBOL_BATTERY_EMPTY`, `blob.SYMBOL_BATTERY_FULL`, … (+837)
- Module-function signature differences: `module.function.anim_delete`, `module.function.anim_get`, `module.function.async_call`, `module.function.async_call_cancel`, `module.function.bin_decoder_close`, `module.function.bin_decoder_get_area`, `module.function.bin_decoder_info`, `module.function.bin_decoder_open`, … (+92)

### micropython

- Missing from target: `struct.global_t`
- Extra in target: `enum.OBJ_FLAG`, `enum.OBJ_FLAG.ADV_HITTEST`, `enum.OBJ_FLAG.CHECKABLE`, `enum.OBJ_FLAG.CLICKABLE`, `enum.OBJ_FLAG.CLICK_FOCUSABLE`, `enum.OBJ_FLAG.EVENT_BUBBLE`, `enum.OBJ_FLAG.EVENT_TRICKLE`, `enum.OBJ_FLAG.FLEX_IN_NEW_TRACK`, … (+26)
- Module-function signature differences: `module.function.anim_delete`, `module.function.anim_get`, `module.function.async_call`, `module.function.async_call_cancel`, `module.function.bin_decoder_close`, `module.function.bin_decoder_get_area`, `module.function.bin_decoder_info`, `module.function.bin_decoder_open`, … (+92)

These are baseline observations, not acceptance decisions for the
new generator. The rebuild must preserve or deliberately document
each target exception in its canonical API and exception manifests.

## Known baseline differences

### circuitpython

- Includes the MicroPython `OBJ_FLAG` and private `global_t` differences.
- Current output omits `tjpgd_init` and `tjpgd_deinit` because the target build excludes TJPGD.
- The 100 module signature differences are primarily upstream metadata lossiness around callbacks and function pointers.

### cpython

- Current output omits the three private GC helpers and the two TJPGD functions.
- Current output omits 17 internal/helper structs and `_nesting` while adding CPython symbol blobs.
- Current output adds 744 module-level struct-function aliases and five formatting-method object entries.
- The `OBJ_FLAG` difference and 100 module signature differences are shared with the other targets.

### micropython

- Current output adds the `OBJ_FLAG` enum namespace and members.
- Current output omits the private `global_t` helper struct.
- The 100 module signature differences are primarily upstream metadata lossiness around callbacks and function pointers.
