"""Unified command for generating all LVGL binding artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from .artifacts import manifest_for_directory
from .emit_pyi import write_pyi
from .preprocess import preprocess


TARGETS = ("micropython", "circuitpython", "cpython")
TARGET_OUTPUTS = {
    "micropython": "lvgl_micropython.c",
    "circuitpython": "lvgl_circuitpython.c",
    "cpython": "lvgl_python.c",
}


def _repo_root():
    return Path(__file__).resolve().parent.parent


def _relative_or_absolute(path, root):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(Path(path).resolve())


def _run_target(root, output_dir, target, naming_style, *, keep_output=True):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    c_path = output_dir / TARGET_OUTPUTS[target]
    command = [
        sys.executable,
        "binding/gen_binding.py",
        "--target",
        target,
        "-M",
        "lvgl",
        "-MP",
        "lv",
        "--naming-style",
        naming_style,
        "--read-only-ir",
        "--ir",
        _relative_or_absolute(output_dir / "lvgl.json", root),
        "-E",
        _relative_or_absolute(output_dir / "lvgl.pp", root),
        "lvgl/lvgl.h",
    ]
    result = subprocess.run(
        command,
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if keep_output:
        c_path.write_text(result.stdout, encoding="utf-8")
    return result.stdout


def _run_ir(root, output_dir, naming_style):
    command = [
        sys.executable,
        "binding/gen_binding.py",
        "--target",
        "micropython",
        "--mode",
        "ir",
        "-M",
        "lvgl",
        "-MP",
        "lv",
        "--naming-style",
        naming_style,
        "--ir",
        _relative_or_absolute(output_dir / "lvgl.json", root),
        "-E",
        _relative_or_absolute(output_dir / "lvgl.pp", root),
        "lvgl/lvgl.h",
    ]
    subprocess.run(
        command,
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def _extract_circuitpython_header(source):
    start_marker = "#ifndef LVCP_MODULE_GLOBALS_H"
    end_marker = "#endif /* LVCP_MODULE_GLOBALS_H */"
    start = source.find(start_marker)
    end = source.find(end_marker)
    if start < 0 or end < 0:
        raise RuntimeError("LVCP_MODULE_GLOBALS block not found in generated C")
    end += len(end_marker)
    return source[start:end] + "\n"


def _preprocess_to(output_dir, root):
    args = SimpleNamespace(
        ep=None,
        include=[str(root / "fake_libc_include")],
        define=[],
        input=[str(root / "lvgl" / "lvgl.h")],
    )
    source, command = preprocess(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lvgl.pp").write_text(source, encoding="utf-8")
    return command


def generate(
    *,
    root=None,
    output_dir=None,
    target="all",
    naming_style="legacy",
    pyi_only=False,
):
    """Generate selected targets into *output_dir* and return artifact metadata."""

    root = Path(root or _repo_root()).resolve()
    output_dir = Path(output_dir or root / "generated").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = output_dir / "lvgl.json"
    pp_path = output_dir / "lvgl.pp"
    pyi_path = output_dir / "lvgl.pyi"

    if pyi_only:
        if not metadata_path.is_file() or not pp_path.is_file():
            raise FileNotFoundError(
                "pyi-only requires existing %s and %s" % (metadata_path, pp_path)
            )
        write_pyi(
            metadata_path,
            pyi_path,
            target="micropython",
            naming_style=naming_style,
            repo_root=root,
        )
        return manifest_for_directory(output_dir, ("lvgl.pyi",))

    _preprocess_to(output_dir, root)
    selected = TARGETS if target == "all" else (target,)

    # The existing IR is produced by the MicroPython analysis path and is the
    # shared input for all targets until the target-neutral IR lands.
    _run_ir(root, output_dir, naming_style)

    if "micropython" in selected:
        _run_target(root, output_dir, "micropython", naming_style)

    if "circuitpython" in selected:
        source = _run_target(root, output_dir, "circuitpython", naming_style)
        (output_dir / "lvgl_circuitpython.h").write_text(
            _extract_circuitpython_header(source), encoding="utf-8"
        )

    if "cpython" in selected:
        _run_target(root, output_dir, "cpython", naming_style)

    write_pyi(
        metadata_path,
        pyi_path,
        target="micropython",
        naming_style=naming_style,
        repo_root=root,
    )
    return manifest_for_directory(output_dir)


def _normalized_for_check(path, data):
    """Normalize generated C command banners before read-only comparison."""

    if not path.endswith((".c", ".h")):
        return data
    lines = data.splitlines(True)
    normalized = []
    skip_command = False
    for line in lines:
        if line.rstrip().endswith("Command line:"):
            normalized.append(line)
            skip_command = True
            continue
        if skip_command:
            normalized.append(" * <stable generator command>\n")
            skip_command = False
            continue
        normalized.append(line)
    return "".join(normalized)


def _compare_directories(expected_dir, actual_dir, filenames):
    differences = []
    for filename in filenames:
        expected = Path(expected_dir) / filename
        actual = Path(actual_dir) / filename
        if not expected.is_file():
            differences.append("missing expected %s" % filename)
            continue
        if not actual.is_file():
            differences.append("missing generated %s" % filename)
            continue
        expected_data = _normalized_for_check(filename, expected.read_text(encoding="utf-8"))
        actual_data = _normalized_for_check(filename, actual.read_text(encoding="utf-8"))
        if expected_data != actual_data:
            differences.append("changed %s" % filename)
    return differences


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=_repo_root(), help="lvgl-bindings repository root"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="artifact directory (default: <root>/generated)",
    )
    parser.add_argument(
        "--target", choices=TARGETS + ("all",), default="all"
    )
    parser.add_argument(
        "--naming-style", choices=("legacy", "pythonic"), default="legacy"
    )
    parser.add_argument(
        "--pyi-only", action="store_true", help="regenerate only lvgl.pyi"
    )
    parser.add_argument(
        "--check", action="store_true", help="generate in a temporary directory and compare"
    )
    parser.add_argument(
        "--hash", action="store_true", help="print the generated artifact manifest"
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output_dir = (args.output_dir or root / "generated").resolve()

    if not args.check:
        manifest = generate(
            root=root,
            output_dir=output_dir,
            target=args.target,
            naming_style=args.naming_style,
            pyi_only=args.pyi_only,
        )
        if args.hash:
            print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    if args.target != "all":
        selected = (TARGET_OUTPUTS[args.target], "lvgl.json", "lvgl.pp", "lvgl.pyi")
        if args.target == "circuitpython":
            selected += ("lvgl_circuitpython.h",)
    elif args.pyi_only:
        selected = ("lvgl.pyi",)
    else:
        selected = (
            "lvgl.json",
            "lvgl.pp",
            "lvgl.pyi",
            "lvgl_micropython.c",
            "lvgl_circuitpython.c",
            "lvgl_circuitpython.h",
            "lvgl_python.c",
        )

    with tempfile.TemporaryDirectory(prefix="lvgl-bindings-check-") as temporary:
        temporary_dir = Path(temporary)
        if args.pyi_only:
            for filename in ("lvgl.json", "lvgl.pp"):
                shutil.copy2(output_dir / filename, temporary_dir / filename)
        generate(
            root=root,
            output_dir=temporary_dir,
            target=args.target,
            naming_style=args.naming_style,
            pyi_only=args.pyi_only,
        )
        differences = _compare_directories(output_dir, temporary, selected)
    if differences:
        for difference in differences:
            print(difference, file=sys.stderr)
        return 1
    print("generated artifacts match %s" % output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
