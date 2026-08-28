from pathlib import Path

import pytest

from binding.api_model import build_api_model
from binding.api_report import (
    TARGET_ARTIFACTS,
    build_report,
    load_json,
    public_export_sets,
    target_artifact_hashes,
    write_json,
)
from binding.ir import parse_source


def _model_data():
    declarations = parse_source(
        "typedef struct _lv_obj_t lv_obj_t; "
        "lv_obj_t *lv_obj_create(lv_obj_t *parent); "
        "typedef struct widget { int value; } widget_t; "
        "lv_obj_t *lv_widget_create(lv_obj_t *parent); "
        "void lv_obj_set_user_data(lv_obj_t *obj, void *data); "
        "void lv_widget_set_value(widget_t *widget, int value); "
        "int lv_count(int limit);",
        filename="report.h",
    )
    return build_api_model(declarations).to_dict()


def test_public_export_sets_include_inherited_methods_and_constructors():
    data = _model_data()
    exports = public_export_sets(data)

    assert "object.obj" in exports["micropython"]
    assert "object.obj.create" in exports["micropython"]
    assert "object.obj.set_user_data" in exports["micropython"]
    assert "object.widget" in exports["micropython"]
    assert "object.widget.create" in exports["micropython"]
    assert "object.widget.set_user_data" in exports["micropython"]
    assert "object.widget.set_value" in exports["micropython"]
    assert "module.function.count" in exports["micropython"]


def test_report_records_target_exceptions_and_is_deterministic():
    data = _model_data()
    functions = list(data["functions"])
    functions.append(
        {
            "c_name": "lv_target_only",
            "python_name": "target_only",
            "role": "module",
            "parameters": [],
            "return_type": {"kind": "primitive", "name": "void"},
            "static": False,
            "variadic": False,
            "storage": [],
            "function_specifiers": [],
            "available_on": ["micropython"],
            "visibility": "public",
            "return_view": {
                "python_type": "None",
                "category": "void",
                "conversion": "none",
            },
        }
    )
    from binding.api_model import api_hash_for_dict

    data["functions"] = functions
    data["api_hash"] = api_hash_for_dict(data)

    report = build_report(data)
    assert report == build_report(data)
    assert report["target_parity"]["all_targets_equal"] is False
    assert report["target_parity"]["common_coverage"] < 1.0
    assert "module.function.target_only" in report["target_parity"]["availability_exceptions"]
    assert report["target_exports"]["micropython"]["count"] > report["target_exports"]["cpython"]["count"]


def test_report_compares_against_compact_baseline():
    data = _model_data()
    baseline = {
        "schema": 1,
        "baseline": {
            "format": "signature_table_v1",
            "signatures": [{"kind": "function"}],
            "functions": {"count": 0},
            "objects": {"widget": {"members": {"set_value": 0}}},
            "enums": {},
            "struct_functions": {},
            "structs": [],
            "blobs": [],
            "int_constants": [],
        },
        "targets": {},
    }

    comparison = build_report(data, baseline)["baseline_compatibility"]
    assert comparison["baseline_entries"] == 3
    assert comparison["name_location_matches"] == 3
    assert comparison["coverage"] == 1.0


def test_compact_baseline_json_is_deterministic_and_readable(tmp_path):
    first = tmp_path / "first.json.gz"
    second = tmp_path / "second.json.gz"
    baseline = {"schema": 1, "baseline": {"functions": {"count": 0}}}

    write_json(first, baseline)
    write_json(second, baseline)

    assert first.read_bytes() == second.read_bytes()
    assert load_json(first) == baseline


def test_report_hashes_each_generated_target_artifact(tmp_path):
    for index, filename in enumerate(TARGET_ARTIFACTS.values()):
        (tmp_path / filename).write_bytes(("target-%d" % index).encode())

    hashes = target_artifact_hashes(tmp_path)

    assert set(hashes) == set(TARGET_ARTIFACTS)
    assert all(len(item["sha256"]) == 64 for item in hashes.values())
    report = build_report(_model_data(), target_artifacts=hashes)
    assert report["target_artifacts"] == hashes


def test_current_baseline_differences_have_a_complete_classification():
    root = Path(__file__).resolve().parents[1]
    data = load_json(root / "generated" / "api.json")
    baseline = load_json(
        root / "docs/baseline/lvgl-bindings-api-baseline.json.gz"
    )
    classification = load_json(
        root / "docs/baseline/lvgl-bindings-api-baseline-classification.json"
    )

    comparison = build_report(data, baseline, classification)["baseline_compatibility"]
    assert comparison["coverage"] >= 0.95
    assert comparison["classification"]["unexplained"] == {"missing": [], "extra": []}


def test_report_rejects_invalid_api_data():
    with pytest.raises(ValueError, match="invalid canonical API model"):
        build_report({"schema_version": 1})


def test_report_rejects_unknown_type_target():
    data = _model_data()
    data["structs"][0]["available_on"] = ["micropython", "other"]
    from binding.api_model import api_hash_for_dict

    data["api_hash"] = api_hash_for_dict(data)

    with pytest.raises(ValueError, match="structs .* unknown target"):
        build_report(data)
