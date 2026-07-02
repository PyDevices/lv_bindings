"""Command-line interface for gen_binding.py (target, IR path, naming style)."""

from __future__ import print_function

import os
import sys
from argparse import ArgumentParser

_LV_BINDINGS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _LV_BINDINGS_DIR)

from .generator import run_circuitpython, run_cpython, run_micropython
from binding.metadata import align_namespace_to_ir, save_bindings_ir, save_metadata
from binding.naming import set_naming_style
from binding.preprocess import preprocess


def build_arg_parser():
    parser = ArgumentParser(
        description="Generate LVGL Python bindings from preprocessed headers."
    )
    parser.add_argument(
        "--target",
        choices=["micropython", "circuitpython", "cpython"],
        default="micropython",
        help="Binding target runtime (default: micropython)",
    )
    parser.add_argument(
        "-I",
        "--include",
        dest="include",
        help="Preprocessor include path",
        metavar="<Include Path>",
        action="append",
    )
    parser.add_argument(
        "-D",
        "--define",
        dest="define",
        help="Define preprocessor macro",
        metavar="<Macro Name>",
        action="append",
    )
    parser.add_argument(
        "-E",
        "--external-preprocessing",
        dest="ep",
        help="Assume input file is already preprocessed",
        metavar="<Preprocessed File>",
        action="store",
    )
    parser.add_argument(
        "-J",
        "--lvgl-json",
        dest="json",
        help="JSON from the LVGL JSON generator for missing information",
        metavar="<JSON file>",
        action="store",
    )
    parser.add_argument(
        "-M",
        "--module_name",
        dest="module_name",
        help="Module name",
        metavar="<Module name string>",
        action="store",
    )
    parser.add_argument(
        "-MP",
        "--module_prefix",
        dest="module_prefix",
        help="Module prefix that starts every function name",
        metavar="<Prefix string>",
        action="store",
    )
    parser.add_argument(
        "-MD",
        "--metadata",
        dest="metadata",
        help="Optional file to emit metadata (introspection)",
        metavar="<MetaData File Name>",
        action="store",
    )
    parser.add_argument(
        "--ir",
        dest="ir",
        help="Optional canonical IR metadata file (MP-shaped lvgl.json)",
        metavar="<IR JSON file>",
        action="store",
    )
    parser.add_argument(
        "--mode",
        choices=["emit", "ir"],
        default="emit",
        help="emit: generate target C source (default); ir: analyze + IR only",
    )
    parser.add_argument(
        "--naming-style",
        choices=["legacy", "pythonic"],
        default=os.environ.get("LV_NAMING_STYLE", "legacy"),
        help="Python export naming style (default: legacy; env: LV_NAMING_STYLE)",
    )
    parser.add_argument("input", nargs="+")
    parser.set_defaults(include=[], define=[], ep=None, json=None, input=[], ir=None)
    return parser


def _save_outputs(namespace, args):
    import os

    if args.ir and args.target == "cpython" and args.metadata and os.path.isfile(args.ir):
        align_namespace_to_ir(namespace, args.ir)
    if args.metadata:
        save_metadata(namespace, args.metadata)
    if args.ir:
        if args.target in ("micropython", "circuitpython"):
            save_bindings_ir(namespace, args.ir)
        elif args.target == "cpython" and not args.metadata:
            save_bindings_ir(namespace, args.ir)


def main(argv=None):
    if argv is None:
        argv = sys.argv
    args = build_arg_parser().parse_args(argv[1:])
    set_naming_style(args.naming_style)

    if args.mode == "ir":
        if args.target != "micropython":
            raise SystemExit("IR mode requires --target micropython")
        source, pp_cmd = preprocess(args)
        cmd_line = " ".join(argv)
        import io
        import os

        devnull = io.open(os.devnull, "w")
        _result, namespace = run_micropython(args, source, pp_cmd, devnull, cmd_line)
        devnull.close()
        ir_path = args.ir
        if not ir_path:
            raise SystemExit("IR mode requires --ir <path>")
        save_bindings_ir(namespace, ir_path)
        if args.metadata:
            save_metadata(namespace, args.metadata)
        return 0

    if args.target == "circuitpython":
        source, pp_cmd = preprocess(args)
        cmd_line = " ".join(argv)
        _result, namespace, emitted = run_circuitpython(
            args, source, pp_cmd, sys.stdout, cmd_line
        )
        _save_outputs(namespace, args)
        return 0 if emitted else 2

    if args.target == "cpython":
        source, pp_cmd = preprocess(args)
        cmd_line = " ".join(argv)
        _result, namespace, emitted = run_cpython(
            args, source, pp_cmd, sys.stdout, cmd_line
        )
        _save_outputs(namespace, args)
        return 0 if emitted else 2

    if args.target != "micropython":
        raise SystemExit("Unsupported target: %s" % args.target)

    source, pp_cmd = preprocess(args)
    cmd_line = " ".join(argv)

    _result, namespace = run_micropython(args, source, pp_cmd, sys.stdout, cmd_line)

    _save_outputs(namespace, args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
