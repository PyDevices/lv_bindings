#!/usr/bin/env python3
"""Create a compact normalized API baseline and comparison report.

This is an investigation/oracle tool, not part of the binding generator.  It
normalizes the metadata emitted by the pinned upstream generator and by the
current target generators so that API names, locations, and signatures can be
compared without comparing generated-C formatting.
"""

from __future__ import print_function

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


UPSTREAM_URL = "https://github.com/lvgl/lv_binding_micropython.git"
UPSTREAM_REF = "60dfbd41f99c2757d1fe3bffab246c818afebcc4"
COMPARISON_SECTIONS = (
    "functions",
    "objects",
    "enums",
    "structs",
    "blobs",
    "int_constants",
)
SIGNATURE_SECTIONS = ("module",)
UNCOMPARED_SECTIONS = ("object_method_signatures", "struct_functions")
KNOWN_DIFFERENCES = {
    "micropython": [
        "Current output adds the `OBJ_FLAG` enum namespace and members.",
        "Current output omits the private `global_t` helper struct.",
        "The 100 module signature differences are primarily upstream metadata lossiness around callbacks and function pointers.",
    ],
    "circuitpython": [
        "Includes the MicroPython `OBJ_FLAG` and private `global_t` differences.",
        "Current output omits `tjpgd_init` and `tjpgd_deinit` because the target build excludes TJPGD.",
        "The 100 module signature differences are primarily upstream metadata lossiness around callbacks and function pointers.",
    ],
    "cpython": [
        "Current output omits the three private GC helpers and the two TJPGD functions.",
        "Current output omits 17 internal/helper structs and `_nesting` while adding CPython symbol blobs.",
        "Current output adds 744 module-level struct-function aliases and five formatting-method object entries.",
        "The `OBJ_FLAG` difference and 100 module signature differences are shared with the other targets.",
    ],
}


def _load_json(path):
    return json.loads(Path(path).read_text())


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
        return {
            "kind": "enum",
            "members": sorted(value.get("members", {}).keys()),
        }
    if value_type == "enum_member":
        return {"kind": "enum_member"}

    normalized = {"kind": value_type or "unknown"}
    if "members" in value and isinstance(value["members"], dict):
        normalized["members"] = {
            name: _normalize_value(value["members"][name])
            for name in sorted(value["members"])
        }
    return normalized


def normalize_metadata(metadata):
    """Return a deterministic metadata representation used by comparisons."""

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
        "enums": {
            name: _normalize_value(enums[name]) for name in sorted(enums)
        },
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


def _overlay_canonical_metadata(target, canonical):
    """Use canonical signatures for target entries that share the API.

    The existing CPython emitter's auxiliary metadata omits some signature
    fields for aliases.  Its canonical IR is already the source used to emit
    those common entries, so use those records while retaining target-only
    names and target-only sections.
    """

    merged = copy.deepcopy(target)
    for section in ("functions", "enums", "struct_functions"):
        target_section = merged.get(section, {})
        canonical_section = canonical.get(section, {})
        for name in target_section:
            if name in canonical_section:
                target_section[name] = copy.deepcopy(canonical_section[name])

    target_objects = merged.get("objects", {})
    canonical_objects = canonical.get("objects", {})
    for name, target_object in target_objects.items():
        canonical_object = canonical_objects.get(name)
        if not canonical_object:
            continue
        target_members = target_object.get("members", {})
        canonical_members = canonical_object.get("members", {})
        for member in target_members:
            if member in canonical_members:
                target_members[member] = copy.deepcopy(canonical_members[member])

    return merged


def _flatten(manifest, include_uncompared=False):
    entries = {}

    for name, signature in manifest["functions"].items():
        entries["module.function." + name] = signature

    for name, value in manifest["objects"].items():
        entries["object." + name] = {"kind": "object"}
        for member, member_value in value["members"].items():
            entries["object." + name + "." + member] = member_value

    for name, value in manifest["enums"].items():
        entries["enum." + name] = value
        for member in value.get("members", []):
            entries["enum." + name + "." + member] = {"kind": "enum_member"}

    for name in manifest["structs"]:
        entries["struct." + name] = {"kind": "struct"}

    for name in manifest["blobs"]:
        entries["blob." + name] = {"kind": "blob"}

    for name in manifest["int_constants"]:
        entries["constant." + name] = {"kind": "int_constant"}

    if include_uncompared:
        for name, members in manifest["struct_functions"].items():
            for member, value in members.items():
                entries["struct_function." + name + "." + member] = value

    return entries


def _section_for_entry(entry):
    return entry.split(".", 1)[0]


def compare_manifests(baseline, target):
    baseline_entries = _flatten(baseline)
    target_entries = _flatten(target)
    baseline_keys = set(baseline_entries)
    target_keys = set(target_entries)
    common_keys = baseline_keys & target_keys
    signature_keys = {
        key for key in common_keys if _section_for_entry(key) in SIGNATURE_SECTIONS
    }
    signature_mismatches = sorted(
        key for key in signature_keys if baseline_entries[key] != target_entries[key]
    )
    exact_matches = len(common_keys) - len(signature_mismatches)
    missing = sorted(baseline_keys - target_keys)
    extra = sorted(target_keys - baseline_keys)

    by_section = {}
    for section in sorted(
        set(_section_for_entry(key) for key in baseline_keys | target_keys)
    ):
        base = {key for key in baseline_keys if _section_for_entry(key) == section}
        current = {key for key in target_keys if _section_for_entry(key) == section}
        by_section[section] = {
            "baseline": len(base),
            "target": len(current),
            "missing": sorted(base - current),
            "extra": sorted(current - base),
            "signature_mismatches": sorted(
                key for key in signature_mismatches if _section_for_entry(key) == section
            ),
        }

    return {
        "baseline_entries": len(baseline_entries),
        "target_entries": len(target_entries),
        "name_location_matches": len(common_keys),
        "name_location_coverage": len(common_keys)
        / float(len(baseline_entries) or 1),
        "signature_entries": len(signature_keys),
        "signature_exact_matches": len(signature_keys) - len(signature_mismatches),
        "signature_coverage": (len(signature_keys) - len(signature_mismatches))
        / float(len(signature_keys) or 1),
        "exact_matches": exact_matches,
        "signature_mismatches": signature_mismatches,
        "missing": missing,
        "extra": extra,
        "coverage": exact_matches / float(len(baseline_entries) or 1),
        "by_section": by_section,
        "uncompared_sections": list(UNCOMPARED_SECTIONS),
    }


def _manifest_delta(base, target):
    delta = {}
    for section in (
        "functions",
        "objects",
        "enums",
        "struct_functions",
        "structs",
        "blobs",
        "int_constants",
    ):
        base_value = base[section]
        target_value = target[section]
        if isinstance(base_value, dict):
            base_keys = set(base_value)
            target_keys = set(target_value)
            changed = {
                key: target_value[key]
                for key in sorted(base_keys & target_keys)
                if base_value[key] != target_value[key]
            }
            delta[section] = {
                "added": {
                    key: target_value[key] for key in sorted(target_keys - base_keys)
                },
                "removed": sorted(base_keys - target_keys),
                "changed": changed,
            }
        else:
            base_set = set(base_value)
            target_set = set(target_value)
            delta[section] = {
                "added": sorted(target_set - base_set),
                "removed": sorted(base_set - target_set),
            }
    return delta


def _compact_manifest(manifest):
    """Deduplicate repeated normalized signatures for on-disk storage."""

    signature_table = []
    signature_ids = {}

    def signature_ref(value):
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if key not in signature_ids:
            signature_ids[key] = len(signature_table)
            signature_table.append(value)
        return signature_ids[key]

    return {
        "format": "signature_table_v1",
        "signatures": signature_table,
        "functions": {
            name: signature_ref(value)
            for name, value in manifest["functions"].items()
        },
        "objects": {
            name: {
                "members": {
                    member: signature_ref(value)
                    for member, value in data["members"].items()
                }
            }
            for name, data in manifest["objects"].items()
        },
        "enums": {
            name: signature_ref(value) for name, value in manifest["enums"].items()
        },
        "struct_functions": {
            name: {
                member: signature_ref(value) for member, value in members.items()
            }
            for name, members in manifest["struct_functions"].items()
        },
        "structs": manifest["structs"],
        "blobs": manifest["blobs"],
        "int_constants": manifest["int_constants"],
    }


def _compact_manifest_delta(base, target):
    """Store a target delta with the same signature-table representation."""

    raw_delta = _manifest_delta(base, target)
    signature_table = []
    signature_ids = {}

    def signature_ref(value):
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if key not in signature_ids:
            signature_ids[key] = len(signature_table)
            signature_table.append(value)
        return signature_ids[key]

    def encode_value(section, value):
        if section in ("objects",) and isinstance(value, dict):
            return {
                "members": {
                    member: signature_ref(member_value)
                    for member, member_value in value.get("members", {}).items()
                }
            }
        return signature_ref(value)

    compact = {"format": "signature_table_v1", "signatures": signature_table}
    for section, delta in raw_delta.items():
        if isinstance(delta["added"], dict):
            compact[section] = {
                "added": {
                    name: encode_value(section, value)
                    for name, value in delta["added"].items()
                },
                "removed": delta["removed"],
                "changed": {
                    name: encode_value(section, value)
                    for name, value in delta["changed"].items()
                },
            }
        else:
            compact[section] = delta
    compact["signatures"] = signature_table
    return compact


def _sha256_file(path):
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def _sha256_tree(path):
    path = Path(path)
    digest = hashlib.sha256()
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(file_path.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
    return digest.hexdigest()


def _git(root, *args):
    try:
        return subprocess.check_output(
            ["git", "-C", str(root)] + list(args), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "<unavailable>"


def _lvgl_version(path):
    text = Path(path).read_text()
    values = []
    for name in ("MAJOR", "MINOR", "PATCH"):
        match = re.search(r"^#define LVGL_VERSION_%s\s+(\d+)" % name, text, re.M)
        values.append(match.group(1) if match else "?")
    return ".".join(values)


def build_provenance(repo_root, upstream_c, upstream_metadata, preprocessed):
    generated = repo_root / "generated"
    artifacts = {}
    for relative in (
        "lvgl.json",
        "lvgl.pp",
        "lvgl.pyi",
        "lvgl_micropython.c",
        "lvgl_circuitpython.c",
        "lvgl_python.c",
    ):
        path = generated / relative
        if path.is_file():
            artifacts[relative] = _sha256_file(path)

    compiler = shutil.which("gcc") or "gcc"
    return {
        "upstream_generator": {
            "repository": UPSTREAM_URL,
            "commit": UPSTREAM_REF,
            "path": "gen/gen_mpy.py",
        },
        "lvgl": {
            "version": _lvgl_version(repo_root / "lvgl" / "lv_version.h"),
            "submodule_commit": _git(repo_root / "lvgl", "rev-parse", "HEAD"),
            "submodule_label": _git(
                repo_root / "lvgl", "describe", "--tags", "--always"
            ),
        },
        "inputs": {
            "lv_conf_sha256": _sha256_file(repo_root / "lv_conf.h"),
            "preprocessed_sha256": _sha256_file(preprocessed),
            "fake_libc_tree_sha256": _sha256_tree(repo_root / "fake_libc_include"),
        },
        "toolchain": {
            "python": sys.version.split()[0],
            "pycparser": __import__("pycparser").__version__,
            "preprocessor": compiler,
            "preprocessor_flags": ["-E", "-DPYCPARSER", "-I", "fake_libc_include"],
        },
        "generated_artifacts_sha256": artifacts,
        "upstream_outputs_sha256": {
            "lvgl_micropython.c": _sha256_file(upstream_c),
            "lvgl.json": _sha256_file(upstream_metadata),
        },
    }


def _format_names(names, limit=8):
    if not names:
        return "none"
    shown = names[:limit]
    suffix = "" if len(names) <= limit else ", … (+%d)" % (len(names) - limit)
    return ", ".join("`%s`" % name for name in shown) + suffix


def _markdown_report(provenance, baseline, targets, comparisons):
    lines = [
        "# LVGL bindings API baseline",
        "",
        "This is a compact, normalized comparison of the pinned upstream",
        "MicroPython generator against the three current target generators.",
        "It compares API names, locations, and normalized signatures; generated",
        "C text is intentionally not used as the compatibility metric.",
        "",
        "## Provenance",
        "",
        "- Upstream generator: `%s` at `%s`" % (
            provenance["upstream_generator"]["repository"],
            provenance["upstream_generator"]["commit"],
        ),
        "- LVGL: `%s` (`%s`) at `%s`" % (
            provenance["lvgl"]["version"],
            provenance["lvgl"]["submodule_label"],
            provenance["lvgl"]["submodule_commit"],
        ),
        "- `lv_conf.h` SHA-256: `%s`"
        % provenance["inputs"]["lv_conf_sha256"],
        "- Preprocessed input SHA-256: `%s`"
        % provenance["inputs"]["preprocessed_sha256"],
        "- Fake-libc tree SHA-256: `%s`"
        % provenance["inputs"]["fake_libc_tree_sha256"],
        "- Parser: `pycparser %s`"
        % provenance["toolchain"]["pycparser"],
        "- Preprocessor: `%s %s`"
        % (
            provenance["toolchain"]["preprocessor"],
            " ".join(provenance["toolchain"]["preprocessor_flags"]),
        ),
        "",
        "## Normalized baseline counts",
        "",
        "| Section | Count |",
        "| --- | ---: |",
    ]
    baseline_entries = _flatten(baseline)
    for section in sorted(set(_section_for_entry(key) for key in baseline_entries)):
        lines.append(
            "| `%s` | %d |"
            % (
                section,
                sum(1 for key in baseline_entries if _section_for_entry(key) == section),
            )
        )

    lines.extend(
        [
            "",
            "## Target comparison",
            "",
        "The name/location score is common entries divided by baseline entries.",
        "The signature score is limited to module functions: upstream metadata",
        "uses a different internal representation for widget methods, and its",
        "metadata writer explicitly leaves struct helper methods as a TODO.",
            "",
            "| Target | Name/location | Baseline entries | Target entries | Name/location coverage | Module signature coverage | Missing | Extra | Signature differences |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for target in targets:
        comparison = comparisons[target]
        lines.append(
            "| %s | %d | %d | %d | %.2f%% | %.2f%% | %d | %d | %d |"
            % (
                target,
                comparison["name_location_matches"],
                comparison["baseline_entries"],
                comparison["target_entries"],
                comparison["name_location_coverage"] * 100.0,
                comparison["signature_coverage"] * 100.0,
                len(comparison["missing"]),
                len(comparison["extra"]),
                len(comparison["signature_mismatches"]),
            )
        )

    lines.extend(["", "## Differences recorded in this baseline", ""])
    for target in targets:
        comparison = comparisons[target]
        lines.extend(
            [
                "### %s" % target,
                "",
                "- Missing from target: %s"
                % _format_names(comparison["missing"]),
                "- Extra in target: %s" % _format_names(comparison["extra"]),
            "- Module-function signature differences: %s"
                % _format_names(comparison["signature_mismatches"]),
                "",
            ]
        )

    lines.extend(
        [
            "These are baseline observations, not acceptance decisions for the",
            "new generator. The rebuild must preserve or deliberately document",
            "each target exception in its canonical API and exception manifests.",
            "",
            "## Known baseline differences",
            "",
        ]
    )
    for target in targets:
        lines.append("### %s" % target)
        lines.append("")
        lines.extend("- " + item for item in KNOWN_DIFFERENCES.get(target, []))
        lines.append("")
    return "\n".join(lines)


def _parse_target(value):
    name, separator, path = value.partition("=")
    if not separator or not name or not path:
        raise argparse.ArgumentTypeError("target must use NAME=PATH")
    return name, Path(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--upstream-metadata", type=Path, required=True)
    parser.add_argument("--upstream-c", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--preprocessed", type=Path, required=True)
    parser.add_argument("--target", action="append", type=_parse_target, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args(argv)

    upstream_raw = _load_json(args.upstream_metadata)
    canonical_raw = _load_json(args.canonical)
    baseline = normalize_metadata(upstream_raw)
    canonical = normalize_metadata(canonical_raw)

    target_manifests = {}
    for target_name, target_path in args.target:
        target_raw = _load_json(target_path)
        target_manifests[target_name] = normalize_metadata(
            _overlay_canonical_metadata(target_raw, canonical_raw)
        )

    comparisons = {
        target: compare_manifests(baseline, manifest)
        for target, manifest in target_manifests.items()
    }
    provenance = build_provenance(
        args.repo_root,
        args.upstream_c,
        args.upstream_metadata,
        args.preprocessed,
    )
    report = {
        "schema": 1,
        "provenance": provenance,
        "comparison_scope": list(COMPARISON_SECTIONS),
        "signature_scope": list(SIGNATURE_SECTIONS),
        "uncompared_sections": list(UNCOMPARED_SECTIONS),
        "known_differences": KNOWN_DIFFERENCES,
        "baseline": _compact_manifest(baseline),
        "canonical_current": _compact_manifest(canonical),
        "targets": {
            target: {
                "manifest_reference": "canonical_current",
                "manifest_delta": _compact_manifest_delta(
                    canonical, target_manifests[target]
                ),
                "comparison": comparisons[target],
            }
            for target in sorted(target_manifests)
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, separators=(",", ":"), sort_keys=True) + "\n"
    )
    args.output_markdown.write_text(
        _markdown_report(provenance, baseline, sorted(target_manifests), comparisons)
    )
    print("Wrote %s" % args.output_json)
    print("Wrote %s" % args.output_markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
