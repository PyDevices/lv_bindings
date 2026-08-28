from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    callback_return_conversion_available,
    callback_return_lowering,
    conversion_available,
    enum_namespace_plan,
    function_reuse_allowed,
    function_return_lowering,
    module_registration_plan,
    mp_obj_get_ull_to_bytes_source,
    prepare_target_lowering,
    require_one_of_target_lowerings,
    require_target_lowering,
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


def test_analysis_state_lives_on_context_not_analyze_module():
    from binding import analyze as analyze_module

    source = "typedef struct fixture { int value; } fixture_t; void lv_init(void);"
    args = SimpleNamespace(
        module_name="lvgl", module_prefix="lv", json=None, input=["fixture.h"]
    )
    prepared = prepare_analysis(args, source, "pp", "cmd", lambda *a, **k: None)

    assert prepared.funcs
    assert "funcs" not in analyze_module.__dict__
    assert "mp_to_lv" not in analyze_module.__dict__


def test_backends_have_one_common_run_contract():
    assert tuple(BACKENDS) == ("micropython", "circuitpython", "cpython")
    assert {backend.name for backend in BACKENDS.values()} == set(BACKENDS)


def test_cpython_backend_uses_its_native_emitter_directly():
    from binding import emit_c_cpython, emit_c_micropython_style, emit_cpython

    assert emit_cpython.emit_c_mod is emit_c_cpython
    assert emit_cpython.emit_c_mod is not emit_c_micropython_style


def test_cpython_emitter_contains_no_cross_target_lowering_branches():
    source = (Path(__file__).parents[1] / "binding" / "emit_c_cpython.py").read_text()

    assert "if _emit_target" not in source
    assert "mp_obj_t" not in source
    assert "MP_REGISTER_MODULE" not in source
    assert "emit_circuitpython_glue" not in source


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
    assert runtime.get("target_lowering_profile").target == "cpython"
    assert not runtime.get("target_lowering_profile").supports_dynamic_function_pointer


def test_target_lowering_contract_rejects_a_cross_target_native_emitter():
    from binding import runtime

    runtime.reset()
    runtime.set_("emit_options", {"target": "micropython", "max_phase": None})

    with pytest.raises(
        RuntimeError,
        match="cpython emitter requires target='cpython'; got 'micropython'",
    ):
        require_target_lowering("cpython")


def test_shared_target_lowering_contract_requires_explicit_supported_target():
    from binding import runtime

    runtime.reset()
    runtime.set_("emit_options", {"target": "cpython", "max_phase": 7})

    with pytest.raises(
        RuntimeError,
        match=r"shared emitter requires one of \('micropython', 'circuitpython'\); got 'cpython'",
    ):
        require_one_of_target_lowerings("micropython", "circuitpython")

    runtime.set_("emit_options", {"target": "circuitpython", "max_phase": 7})
    assert require_one_of_target_lowerings("micropython", "circuitpython") == (
        "circuitpython",
        7,
    )


def test_target_lowering_header_and_banner_policy_is_shared():
    assert resolve_emitter_headers(["lvgl/lvgl.h", "extra.h"]) == [
        "lvgl/lvgl.h",
        "extra.h",
        "lvgl/src/lvgl_private.h",
    ]
    assert resolve_emitter_headers(["lvgl.h"]) == ["lvgl.h", "src/lvgl_private.h"]
    assert target_banner("cpython", include=True) == " *\n * Target: cpython\n"


def test_enum_namespace_plan_preserves_member_nesting_and_widget_policy():
    enums = {"lv_obj_flag_t": {"LV_OBJ_FLAG_HIDDEN": "1"}, "lv_obj_flag_x_t": {}}
    plan = enum_namespace_plan(
        enums=enums,
        get_enum_members=lambda name: tuple(enums[name]),
        is_method_of=lambda child, parent: child != parent
        and child.startswith(parent.removesuffix("_t")),
        is_widget_scoped=lambda name: name.endswith("_x_t"),
    )

    assert [(item.name, item.members, item.nested_names) for item in plan] == [
        ("lv_obj_flag_t", ("LV_OBJ_FLAG_HIDDEN",), ("lv_obj_flag_x_t",)),
        ("lv_obj_flag_x_t", (), ()),
    ]
    assert plan[0].widget_scoped_nested_names == ("lv_obj_flag_x_t",)


def test_native_glue_uses_explicit_runtime_output_not_global_mirroring():
    from binding import emit_circuitpython_glue, emit_cpython_glue, emit_cpython_native
    from binding import runtime

    emitted = []
    runtime.reset()
    try:
        runtime.set_("print", lambda *args, **kwargs: emitted.append(args))
        for module in (
            emit_cpython_native,
            emit_cpython_glue,
            emit_circuitpython_glue,
        ):
            module.print(module.__name__)
    finally:
        runtime.reset()

    assert emitted == [
        ("binding.emit_cpython_native",),
        ("binding.emit_cpython_glue",),
        ("binding.emit_circuitpython_glue",),
    ]
    assert target_banner("micropython", include=False) == ""


def test_cpython_native_helper_binding_does_not_use_shared_runtime_state():
    from binding import emit_cpython_native, runtime

    runtime.reset()
    try:
        emit_cpython_native.bind_emit_helpers({"generated_funcs": {"lv_init": True}})
        assert emit_cpython_native.bound_helper("generated_funcs") == {"lv_init": True}
        assert "_py_helpers" not in runtime.__dict__
    finally:
        emit_cpython_native.reset_emit_helpers()
        runtime.reset()

    assert emit_cpython_native.bound_helper("generated_funcs") is None


def test_mp_64_bit_integer_lowering_is_shared_and_version_safe():
    source = mp_obj_get_ull_to_bytes_source()

    assert "#if defined(CIRCUITPY)" in source
    assert "MICROPY_VERSION_MAJOR" in source
    assert "mp_obj_int_to_bytes(obj, sizeof(val)" in source
    assert source.count("mp_obj_int_to_bytes_impl") == 2


def test_function_return_lowering_preserves_void_and_pointer_conversion_policy():
    mappings = {"lv_obj_t *": "lv_to_mp_obj"}
    type_metadata = {"lv_obj_t *": "lv.obj"}

    void = function_return_lowering(
        return_type="void",
        qualified_return_type="void",
        is_pointer=False,
        lv_to_mp=mappings,
        lv_mp_type=type_metadata,
    )
    pointer = function_return_lowering(
        return_type="lv_obj_t *",
        qualified_return_type="lv_obj_t *",
        is_pointer=True,
        lv_to_mp=mappings,
        lv_mp_type=type_metadata,
    )

    assert (void.build_result, void.build_return_value, void.metadata_return_type) == (
        "",
        "mp_const_none",
        "NoneType",
    )
    assert pointer.build_result == "lv_obj_t * _res = "
    assert pointer.build_return_value == "lv_to_mp_obj((void*)_res)"
    assert pointer.metadata_return_type == "lv.obj"


def test_callback_return_lowering_preserves_void_and_conversion_policy():
    mappings = {"lv_result_t": "mp_to_lv_result"}

    void = callback_return_lowering(return_type="void", mp_to_lv=mappings)
    result = callback_return_lowering(return_type="lv_result_t", mp_to_lv=mappings)

    assert (void.result_assignment, void.return_value) == ("", "")
    assert result.result_assignment == "mp_obj_t callback_result = "
    assert result.return_value == " mp_to_lv_result(callback_result)"


def test_callback_return_conversion_attempts_generation_only_when_needed():
    mappings = {"present_t": "mp_to_lv_present"}
    generated = []

    assert callback_return_conversion_available(
        return_type="void", mp_to_lv=mappings, generate_type=lambda: generated.append("void")
    )
    assert callback_return_conversion_available(
        return_type="present_t",
        mp_to_lv=mappings,
        generate_type=lambda: generated.append("present"),
    )
    assert not callback_return_conversion_available(
        return_type="missing_t",
        mp_to_lv=mappings,
        generate_type=lambda: generated.append("missing"),
    )

    def generate_resolved():
        generated.append("resolved")
        mappings["resolved_t"] = "mp_to_lv_resolved"

    assert callback_return_conversion_available(
        return_type="resolved_t", mp_to_lv=mappings, generate_type=generate_resolved
    )
    assert generated == ["missing", "resolved"]


def test_conversion_available_retries_a_missing_mapping_once():
    conversions = {"present_t": "present"}
    generated = []

    assert conversion_available(
        conversions=conversions,
        type_name="present_t",
        generate_type=lambda: generated.append("present"),
    )
    assert not conversion_available(
        conversions=conversions,
        type_name="missing_t",
        generate_type=lambda: generated.append("missing"),
    )

    def generate_resolved():
        generated.append("resolved")
        conversions["resolved_t"] = "resolved"

    assert conversion_available(
        conversions=conversions,
        type_name="resolved_t",
        generate_type=generate_resolved,
    )
    assert generated == ["missing", "resolved"]


def test_function_reuse_policy_requires_dynamic_wrapper_for_distinct_symbols():
    assert function_reuse_allowed(
        function_name="lv_label_create",
        original_name="lv_button_create",
        original_generated=True,
        supports_dynamic_function_pointer=True,
    )
    assert not function_reuse_allowed(
        function_name="lv_obj_get_x",
        original_name="lv_obj_get_y",
        original_generated=True,
        supports_dynamic_function_pointer=False,
    )
    assert not function_reuse_allowed(
        function_name="lv_obj_get_x",
        original_name="lv_obj_get_y",
        original_generated=False,
        supports_dynamic_function_pointer=True,
    )


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


def test_module_registration_plan_preserves_phase_gates_and_declaration_order():
    functions = (SimpleNamespace(name="lv_init"), SimpleNamespace(name="lv_tick_inc"))
    full = module_registration_plan(
        max_phase=6,
        int_constants=("LV_FIRST", "LV_SECOND"),
        generated_globals=("LV_GLOBAL",),
        enums={"lv_state_t": {}, "lv_obj_flag_t": {}},
        enum_referenced={"lv_obj_flag_t": True},
        generated_structs={"lv_point_t": True, "lv_unused_t": False},
        struct_aliases={"lv_point_t": "lv_point"},
        obj_names=("lv_obj_t",),
        module_funcs=functions,
    )

    assert full.int_constants == ("LV_FIRST", "LV_SECOND")
    assert full.generated_globals == ("LV_GLOBAL",)
    assert full.enum_names == ("lv_state_t",)
    assert full.struct_names == ("lv_point_t",)
    assert full.struct_alias_names == ("lv_point_t",)
    assert full.object_names == ("lv_obj_t",)
    assert full.module_functions == functions

    phase_two = module_registration_plan(
        max_phase=2,
        int_constants=("LV_FIRST",),
        generated_globals=("LV_GLOBAL",),
        enums={"lv_state_t": {}},
        enum_referenced={},
        generated_structs={"lv_point_t": True},
        struct_aliases={"lv_point_t": "lv_point"},
        obj_names=("lv_obj_t",),
        module_funcs=functions,
    )
    assert phase_two.int_constants == ("LV_FIRST",)
    assert phase_two.enum_names == ("lv_state_t",)
    assert not phase_two.struct_names
    assert not phase_two.object_names
    assert not phase_two.module_functions
