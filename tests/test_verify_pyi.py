from io import StringIO

from binding.api_model import api_hash_for_dict
from binding.emit_pyi_canonical import CanonicalPyiEmitter
from binding.verify_pyi import validate_pyi_data
from tests.test_pyi_canonical import _api_data


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


def test_pyi_manifest_verifier_reports_signature_drift():
    data = _validated_data()
    source = _render(data).replace(
        "def set_value(self, value: int) -> None: ...",
        "def set_value(self, value: str) -> None: ...",
    )

    errors = validate_pyi_data(data, source)

    assert any("signature mismatch: widget.set_value" in error for error in errors)
