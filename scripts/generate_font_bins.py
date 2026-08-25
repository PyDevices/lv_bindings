#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2024 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Generate runtime-loadable binary fonts (fonts/*.bin) for every LVGL
built-in font.

The recipes are read from the LVGL submodule's own generator
(``lvgl/scripts/built_in_font/generate_all.py``) so the fonts, sizes, glyph
ranges, and symbol lists track upstream exactly — including the FontAwesome
symbol set merged into the Montserrat fonts, which is read from
``built_in_font_gen.py``. Each recipe is re-run through ``lv_font_conv`` with
``--format bin`` instead of C output. Subpixel and compressed variants are
skipped: our ``lv_conf.h`` builds with ``LV_USE_FONT_SUBPX`` and
``LV_USE_FONT_COMPRESSED`` off, so the loader could not render them.

The resulting ``.bin`` files load at runtime with ``lv.binfont_create()``
(through ``fs_driver.py``) or ``lv.binfont_create_from_buffer()`` on any of
the three consumers; no firmware rebuild is involved.

Requires ``lv_font_conv`` (https://github.com/lvgl/lv_font_conv) on PATH, or
node/npx (the script falls back to ``npx --yes lv_font_conv``).

Usage::

    ./scripts/generate_font_bins.py            # writes fonts/*.bin
    ./scripts/generate_font_bins.py --only montserrat_14 montserrat_20
"""

import argparse
import ast
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILT_IN_FONT_DIR = REPO_ROOT / "lvgl" / "scripts" / "built_in_font"
FONTS_DIR = REPO_ROOT / "fonts"

FONTAWESOME = "FontAwesome5-Solid+Brands+Regular.woff"


def lv_font_conv_argv():
    if shutil.which("lv_font_conv"):
        return ["lv_font_conv"]
    if shutil.which("npx"):
        return ["npx", "--yes", "lv_font_conv"]
    sys.exit("error: need lv_font_conv on PATH, or npx to fetch it")


def os_system_commands(path):
    """Yield the command string of every os.system() call in a script."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "system"
        ):
            continue
        arg = node.args[0]
        # The CJK recipes wrap the command in str.encode("utf-8").
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "encode"
        ):
            arg = arg.func.value
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            yield arg.value


def fontawesome_codepoints():
    """The built-in symbol set, from built_in_font_gen.py's `syms = "..."`."""
    src = (BUILT_IN_FONT_DIR / "built_in_font_gen.py").read_text(encoding="utf-8")
    match = re.search(r'^syms\s*=\s*"([0-9,]+)"', src, re.MULTILINE)
    if not match:
        sys.exit("error: FontAwesome symbol list not found in built_in_font_gen.py")
    return match.group(1)


def parse_gen_args(tokens):
    """Options of a ./built_in_font_gen.py invocation, as a dict."""
    opts = {"flags": set()}
    it = iter(tokens)
    for tok in it:
        if tok in ("--subpx", "--compressed"):
            opts["flags"].add(tok)
        elif tok in ("--size", "-s", "--bpp", "-o", "--output", "--font", "-r",
                     "--range", "--symbols"):
            key = {"-s": "--size", "--output": "-o", "--range": "-r"}.get(tok, tok)
            opts[key] = next(it)
    return opts


def bin_name(c_output):
    """lv_font_montserrat_8.c -> montserrat_8.bin"""
    stem = Path(c_output).stem
    if stem.startswith("lv_font_"):
        stem = stem[len("lv_font_"):]
    return stem + ".bin"


def recipes():
    """Yield (bin_name, lv_font_conv argv tail) for every eligible font."""
    fa_syms = fontawesome_codepoints()
    for command in os_system_commands(BUILT_IN_FONT_DIR / "generate_all.py"):
        tokens = shlex.split(command)
        if tokens[0] == "./built_in_font_gen.py":
            opts = parse_gen_args(tokens[1:])
            if opts["flags"]:
                continue  # subpx/compressed variants: loader can't render them
            # Mirrors built_in_font_gen.py's lv_font_conv invocation.
            args = [
                "--no-compress", "--no-prefilter",
                "--bpp", opts.get("--bpp", "4"),
                "--size", opts["--size"],
                "--font", opts.get("--font", "Montserrat-Medium.ttf"),
                "-r", opts.get("-r", "0x20-0x7F,0xB0,0x2022"),
            ]
            if "--symbols" in opts:
                args += ["--symbols", opts["--symbols"]]
            args += [
                "--font", FONTAWESOME, "-r", fa_syms,
                "--force-fast-kern-format",
            ]
            yield bin_name(opts["-o"]), args
        elif tokens[0] == "lv_font_conv":
            # Direct invocations (unscii): reuse args, drop format/output.
            args = []
            it = iter(tokens[1:])
            output = None
            for tok in it:
                if tok in ("--format", "-o", "--output"):
                    value = next(it)
                    if tok != "--format":
                        output = value
                else:
                    args.append(tok)
            yield bin_name(output), args


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--only", nargs="+", metavar="NAME",
        help="generate just these fonts (names like montserrat_14, no .bin)",
    )
    cli = parser.parse_args()

    conv = lv_font_conv_argv()
    FONTS_DIR.mkdir(exist_ok=True)

    wanted = set(cli.only or [])
    seen = set()
    for name, args in recipes():
        seen.add(name.removesuffix(".bin"))
        if wanted and name.removesuffix(".bin") not in wanted:
            continue
        out = FONTS_DIR / name
        print(f"Generating {out.relative_to(REPO_ROOT)}")
        subprocess.run(
            conv + args + ["--format", "bin", "-o", str(out)],
            cwd=BUILT_IN_FONT_DIR,
            check=True,
        )

    missing = wanted - seen
    if missing:
        sys.exit(f"error: no recipe for: {', '.join(sorted(missing))} "
                 f"(available: {', '.join(sorted(seen))})")


if __name__ == "__main__":
    main()
