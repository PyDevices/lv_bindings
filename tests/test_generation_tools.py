from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from binding.artifacts import compare_manifests, manifest_for_directory
from binding.cli import _stable_command_line
from binding.generate import _extract_circuitpython_header, _normalized_for_check, generate
from binding.generator import analysis_snapshot, prepare_analysis, run_micropython
from binding.preprocess import _preprocessor_command


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_preprocessor_command_is_deterministic(monkeypatch):
    monkeypatch.setenv("CPP", "gcc")
    args = SimpleNamespace(
        define=["LV_TEST=1"],
        include=["include-a", "include-b"],
        input=["lvgl/lvgl.h", "extra.h"],
    )

    assert _preprocessor_command(args) == [
        "gcc",
        "-E",
        "-P",
        "-std=c99",
        "-DPYCPARSER",
        "-DLV_TEST=1",
        "-I",
        "include-a",
        "-I",
        "include-b",
        "-include",
        "extra.h",
        "lvgl/lvgl.h",
    ]


def test_artifact_manifest_hashes_and_compares(tmp_path):
    (tmp_path / "lvgl.json").write_text("{}\n")
    (tmp_path / "lvgl.pp").write_text("void lv_init(void);\n")

    first = manifest_for_directory(tmp_path, ("lvgl.json", "lvgl.pp"))
    second = manifest_for_directory(tmp_path, ("lvgl.json", "lvgl.pp"))
    assert first == second
    assert compare_manifests(first, second)["equal"]

    (tmp_path / "lvgl.pp").write_text("void lv_deinit(void);\n")
    changed = manifest_for_directory(tmp_path, ("lvgl.json", "lvgl.pp"))
    comparison = compare_manifests(first, changed)
    assert comparison["changed"] == ["lvgl.pp"]
    assert not comparison["equal"]


def test_command_line_uses_stable_executable_name():
    assert _stable_command_line(
        ["/different/checkout/binding/gen_binding.py", "--target", "cpython"]
    ) == "gen_binding.py --target cpython"


def test_circuitpython_header_extraction():
    source = "prefix\n#ifndef LVCP_MODULE_GLOBALS_H\n#define X\n#endif /* LVCP_MODULE_GLOBALS_H */\nsuffix\n"
    assert _extract_circuitpython_header(source) == (
        "#ifndef LVCP_MODULE_GLOBALS_H\n#define X\n#endif /* LVCP_MODULE_GLOBALS_H */\n"
    )


def test_check_normalizes_generated_command_banner():
    first = " * Command line:\n * /one/checkout/binding/gen_binding.py --target cpython\n"
    second = " * Command line:\n * /another/checkout/binding/gen_binding.py --target cpython\n"
    assert _normalized_for_check("lvgl_python.c", first) == _normalized_for_check(
        "lvgl_python.c", second
    )


def test_pyi_only_generation_uses_existing_inputs(tmp_path):
    generated = REPO_ROOT / "generated"
    shutil.copy2(generated / "lvgl.json", tmp_path / "lvgl.json")
    shutil.copy2(generated / "lvgl.pp", tmp_path / "lvgl.pp")

    manifest = generate(
        root=REPO_ROOT,
        output_dir=tmp_path,
        pyi_only=True,
    )

    assert (tmp_path / "lvgl.pyi").is_file()
    assert manifest["files"]["lvgl.pyi"]["bytes"] > 0


def test_unified_generator_help():
    result = subprocess.run(
        [sys.executable, "-m", "binding.generate", "--help"],
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(REPO_ROOT)},
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0
    assert "--pyi-only" in result.stdout
    assert "--check" in result.stdout


def test_prepared_analysis_parses_source_once_and_shares_declaration_ir(monkeypatch):
    import io

    from pycparser import c_parser

    source = "typedef struct fixture { int value; } fixture_t; void lv_init(void);"
    calls = []
    original_parse = c_parser.CParser.parse

    def recording_parse(parser, text, *args, **kwargs):
        calls.append(text)
        return original_parse(parser, text, *args, **kwargs)

    monkeypatch.setattr(c_parser.CParser, "parse", recording_parse)
    args = SimpleNamespace(module_name="lvgl", module_prefix="lv", json=None, input=["fixture.h"])
    prepared = prepare_analysis(args, source, "pp", "cmd", lambda *a, **k: None)
    state = analysis_snapshot(prepared)
    output = io.StringIO()
    _result, namespace = run_micropython(
        args, source, "pp", output, "cmd", analysis_state=state
    )

    assert calls.count(source) == 1
    assert namespace["declaration_ir"] is prepared.declaration_ir
    assert namespace["api_model"] is prepared.api_model
