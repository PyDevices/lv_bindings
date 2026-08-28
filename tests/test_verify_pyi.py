import ast
import json
from io import StringIO
from pathlib import Path

from binding.api_model import api_hash_for_dict
from binding.api_policy import ApiPolicy
from binding.emit_pyi_canonical import CanonicalPyiEmitter
from binding.verify_pyi import validate_pyi_data
from tests.test_pyi_canonical import _api_data


REPO_ROOT = Path(__file__).parents[1]


def _render(data, target="all"):
    output = StringIO()
    CanonicalPyiEmitter(data, target=target, lvgl_version="9.5").emit(output)
    return output.getvalue()


def _validated_data():
    data = _api_data()
    data["api_hash"] = api_hash_for_dict(data)
    return data


def test_pyi_manifest_verifier_accepts_common_and_target_specific_stubs():
    data = _validated_data()

    assert validate_pyi_data(data, _render(data)) == []
    assert validate_pyi_data(data, _render(data, target="micropython"), target="micropython") == []


def test_pyi_manifest_verifier_reports_target_leakage():
    data = _validated_data()
    errors = validate_pyi_data(data, _render(data, target="micropython"))

    assert "unexpected top-level export: target_only" in errors


def test_pyi_manifest_verifier_allows_only_known_private_helper_types():
    data = _validated_data()
    source = _render(data) + "\n_leaked_runtime_type: object\n"

    errors = validate_pyi_data(data, source)

    assert "unexpected top-level export: _leaked_runtime_type" in errors


def test_pyi_manifest_verifier_reports_signature_drift():
    data = _validated_data()
    source = _render(data).replace(
        "def set_value(self, value: int) -> None: ...",
        "def set_value(self, value: str) -> None: ...",
    )

    errors = validate_pyi_data(data, source)

    assert any("signature mismatch: widget.set_value" in error for error in errors)


def test_target_specific_stubs_match_the_real_exception_policy():
    data = json.loads(
        (REPO_ROOT / "generated" / "api.json").read_text(encoding="utf-8")
    )
    policy = ApiPolicy.from_file(REPO_ROOT / "binding" / "api_policy.json")
    functions = {item["c_name"]: item for item in data["functions"]}
    target_exports = {}
    for target in ("all", "micropython", "circuitpython", "cpython"):
        source = _render(data, target=target)
        assert validate_pyi_data(data, source, target=target) == []
        target_exports[target] = {
            node.name
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    for exception in policy.target_exceptions.values():
        function = functions[exception.name]
        python_name = function["python_name"]
        assert function["visibility"] == "public"
        assert python_name not in target_exports["all"]
        assert python_name not in target_exports[exception.target]
        for target in function["available_on"]:
            assert python_name in target_exports[target]
