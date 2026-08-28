#!/usr/bin/env python3
"""Verify the compact historical baseline against pinned upstream output."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def _normalize_value(value):
    if not isinstance(value, dict):
        return {"kind": "unknown"}
    value_type = value.get("type")
    if value_type == "function":
        return {
            "kind": "function",
            "args": [arg.get("type", "<unknown>") for arg in value.get("args", [])],
            "return_type": value.get("return_type", "<unspecified>"),
            "static": bool(value.get("static", False)),
        }
    if value_type == "enum_type":
        return {"kind": "enum", "members": sorted(value.get("members", {}))}
    if value_type == "enum_member":
        return {"kind": "enum_member"}
    normalized = {"kind": value_type or "unknown"}
    if isinstance(value.get("members"), dict):
        normalized["members"] = {
            name: _normalize_value(member)
            for name, member in sorted(value["members"].items())
        }
    return normalized


def _normalize_metadata(metadata):
    objects = metadata.get("objects", {})
    functions = metadata.get("functions", {})
    enums = metadata.get("enums", {})
    struct_functions = metadata.get("struct_functions", {})
    return {
        "functions": {
            name: _normalize_value(functions[name]) for name in sorted(functions)
        },
        "objects": {
            name: {
                "members": {
                    member: _normalize_value(value)
                    for member, value in sorted(objects[name].get("members", {}).items())
                }
            }
            for name in sorted(objects)
        },
        "enums": {name: _normalize_value(enums[name]) for name in sorted(enums)},
        "structs": sorted(metadata.get("structs", [])),
        "struct_functions": {
            name: {
                member: _normalize_value(value)
                for member, value in sorted(struct_functions[name].items())
            }
            for name in sorted(struct_functions)
        },
        "blobs": sorted(metadata.get("blobs", [])),
        "int_constants": sorted(metadata.get("int_constants", [])),
    }


def _compact_manifest(manifest):
    signatures = []
    ids = {}

    def ref(value):
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if key not in ids:
            ids[key] = len(signatures)
            signatures.append(value)
        return ids[key]

    result = {
        "format": "signature_table_v1",
        "signatures": signatures,
        "functions": {name: ref(value) for name, value in manifest["functions"].items()},
        "objects": {
            name: {"members": {member: ref(value) for member, value in data["members"].items()}}
            for name, data in manifest["objects"].items()
        },
        "enums": {name: ref(value) for name, value in manifest["enums"].items()},
        "struct_functions": {
            name: {member: ref(value) for member, value in members.items()}
            for name, members in manifest["struct_functions"].items()
        },
        "structs": manifest["structs"],
        "blobs": manifest["blobs"],
        "int_constants": manifest["int_constants"],
    }
    return result


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-metadata", type=Path, required=True)
    parser.add_argument("--upstream-c", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args(argv)

    with gzip.open(args.baseline, "rt", encoding="utf-8") as stream:
        baseline = json.load(stream)
    upstream = json.loads(args.upstream_metadata.read_text(encoding="utf-8"))
    compact = _compact_manifest(_normalize_metadata(upstream))
    if compact != baseline["baseline"]:
        raise SystemExit("pinned upstream metadata does not match compact baseline")

    expected_metadata = baseline["provenance"]["upstream_outputs_sha256"]["lvgl.json"]
    actual_metadata = _sha256(args.upstream_metadata)
    if actual_metadata != expected_metadata:
        raise SystemExit(
            "pinned upstream metadata hash changed:\nexpected %s\nactual   %s"
            % (expected_metadata, actual_metadata)
        )
    c_text = args.upstream_c.read_text(encoding="utf-8")
    if "Auto-Generated file, DO NOT EDIT!" not in c_text:
        raise SystemExit("pinned upstream generator did not emit its C binding")
    # The upstream C banner embeds its output command and temporary checkout
    # path, so its historical raw hash is provenance, not a reproducibility
    # gate. Generated C text is intentionally outside the API baseline metric.
    print("upstream metadata matches the compact historical baseline; C emission succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
