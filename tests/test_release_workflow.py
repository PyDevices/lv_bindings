from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_regeneration_has_no_release_mutation_options():
    script = (ROOT / "regenerate_all.sh").read_text()
    assert "--no-commit" not in script
    assert "--no-tag" not in script
    assert "git commit" not in script
    assert "git tag" not in script


def test_release_workflow_is_manual_and_publish_is_opt_in():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "default: false" in workflow
    assert "if: inputs.publish == true" in workflow
    assert "needs: [validate, matrix]" in workflow
    assert not (ROOT / ".github/workflows/trigger-lvgl-python-release.yml").exists()


def test_release_gate_is_non_mutating_and_runs_full_validation():
    script = (ROOT / "scripts/release_dry_run.sh").read_text()
    assert "pytest" in script
    assert "verify_bindings.sh" in script
    assert "regenerate_all.sh --check --hash" in script
    assert "publish_release_tag.sh" not in script


def test_linux_integration_covers_all_consumers():
    workflow = (ROOT / ".github/workflows/linux-integration.yml").read_text()
    for consumer in ("lvgl-micropython", "lvgl-circuitpython", "lvgl-python"):
        assert consumer in workflow
    assert "test_lvgl_smoke.py" in workflow
