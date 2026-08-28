from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from binding.artifacts import compare_manifests, manifest_for_directory
from binding.cli import _stable_command_line
from binding.generate import _extract_circuitpython_header, _normalized_for_check, generate
from binding.generator import (
    BACKENDS,
    analysis_snapshot,
    prepare_analysis,
    run_backend,
)
from binding.preprocess import _preprocessor_command
from binding.verify_namespace import mp_module_names, py_module_names
from binding.emit_backend import (
    mp_obj_get_ull_to_bytes_source,
    prepare_target_lowering,
    resolve_emitter_headers,
    target_banner,
)


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
    shutil.copy2(generated / "api.json", tmp_path / "api.json")

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


def test_lifecycle_dunders_are_not_part_of_the_shared_public_namespace():
    micropython = (REPO_ROOT / "generated" / "lvgl_micropython.c").read_text(
        encoding="utf-8"
    )
    circuitpython = (REPO_ROOT / "generated" / "lvgl_circuitpython.c").read_text(
        encoding="utf-8"
    )
    cpython = (REPO_ROOT / "generated" / "lvgl_python.c").read_text(
        encoding="utf-8"
    )

    # MicroPython's user-module loader uses these hooks.  CircuitPython's
    # generated source excludes them when LV_CIRCUITPYTHON_BUILD is defined,
    # and CPython owns module lifecycle through the extension loader.  They
    # are therefore runtime integration details, never shared API exports.
    assert {"__init__", "__del__"} <= mp_module_names(micropython)
    assert "#ifndef LV_CIRCUITPYTHON_BUILD" in circuitpython
    assert {"__init__", "__del__"}.isdisjoint(mp_module_names(circuitpython))
    assert {"__init__", "__del__"}.isdisjoint(py_module_names(cpython))


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

    def unexpected_analysis():
        raise AssertionError("target backend re-ran analysis")

    monkeypatch.setattr("binding.emit_micropython.analyze", unexpected_analysis)
    monkeypatch.setattr("binding.emit_circuitpython.analyze", unexpected_analysis)
    monkeypatch.setattr("binding.emit_cpython.analyze", unexpected_analysis)
    runners = tuple(BACKENDS)
    namespaces = []
    for target in runners:
        output = io.StringIO()
        run = run_backend(target, args, source, "pp", output, "cmd", analysis_state=state)
        namespaces.append(run.namespace)

    assert calls.count(source) == 1
    for namespace in namespaces:
        assert namespace["declaration_ir"] is prepared.declaration_ir
        assert namespace["api_model"] is prepared.api_model


def test_backends_have_one_common_run_contract():
    assert tuple(BACKENDS) == ("micropython", "circuitpython", "cpython")
    assert {backend.name for backend in BACKENDS.values()} == set(BACKENDS)


def test_cpython_backend_uses_its_native_emitter_directly():
    from binding import emit_c_cpython, emit_c_micropython_style, emit_cpython

    assert emit_cpython.emit_c_mod is emit_c_cpython
    assert emit_cpython.emit_c_mod is not emit_c_micropython_style


def test_target_lowering_setup_uses_common_defaults():
    from binding import runtime

    runtime.reset()
    ctx = SimpleNamespace(args=SimpleNamespace(input=["fixture.h"]), headers=None)
    prepare_target_lowering(
        ctx,
        target="cpython",
        max_phase=7,
    )

    assert runtime.get("emit_options") == {"target": "cpython", "max_phase": 7}
    assert runtime.get("headers") == ["fixture.h"]
    assert runtime.get("generated_globals") == []
    assert runtime.get("module_funcs") == []
    assert runtime.get("generated_funcs") == {}


def test_target_lowering_header_and_banner_policy_is_shared():
    assert resolve_emitter_headers(["lvgl/lvgl.h", "extra.h"]) == [
        "lvgl/lvgl.h",
        "extra.h",
        "lvgl/src/lvgl_private.h",
    ]
    assert resolve_emitter_headers(["lvgl.h"]) == ["lvgl.h", "src/lvgl_private.h"]
    assert target_banner("cpython", include=True) == " *\n * Target: cpython\n"
    assert target_banner("micropython", include=False) == ""


def test_mp_64_bit_integer_lowering_is_shared_and_version_safe():
    source = mp_obj_get_ull_to_bytes_source()

    assert "#if defined(CIRCUITPY)" in source
    assert "MICROPY_VERSION_MAJOR" in source
    assert "mp_obj_int_to_bytes(obj, sizeof(val)" in source
    assert source.count("mp_obj_int_to_bytes_impl") == 2


def test_struct_pointer_helpers_preserve_target_null_and_warning_policy():
    from binding.emit_backend import struct_pointer_helpers_source

    mpy = struct_pointer_helpers_source(
        accept_none=False,
        unused_qualifier="GENMPY_UNUSED ",
        sanitized_struct_name="lv_point_t",
        struct_name="lv_point_t",
        struct_tag="",
    )
    cpython = struct_pointer_helpers_source(
        accept_none=True,
        unused_qualifier="",
        sanitized_struct_name="lv_point_t",
        struct_name="lv_point_t",
        struct_tag="",
    )

    assert "GENMPY_UNUSED static inline void*" in mpy
    assert "if (self_in == mp_const_none) return NULL;" not in mpy
    assert "GENMPY_UNUSED" not in cpython
    assert "if (self_in == mp_const_none) return NULL;" in cpython
    assert "mp_write_ptr_lv_point_t" in mpy
