#!/usr/bin/env python3
"""Print or validate a manifest of generated LVGL binding artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from binding.artifacts import compare_manifests, manifest_for_directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "generated",
        help="Directory containing generated artifacts",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the manifest to this path instead of stdout",
    )
    parser.add_argument(
        "--check",
        type=Path,
        metavar="MANIFEST",
        help="Exit nonzero if the directory differs from MANIFEST",
    )
    args = parser.parse_args(argv)

    manifest = manifest_for_directory(args.directory)
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if not args.check:
        return 0

    expected = json.loads(args.check.read_text(encoding="utf-8"))
    comparison = compare_manifests(expected, manifest)
    if comparison["equal"]:
        print("artifact manifest matches %s" % args.check, file=sys.stderr)
        return 0
    print("artifact manifest mismatch:", file=sys.stderr)
    for label in ("missing", "unexpected", "changed"):
        values = comparison[label]
        if values:
            print("  %s: %s" % (label, ", ".join(values)), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
