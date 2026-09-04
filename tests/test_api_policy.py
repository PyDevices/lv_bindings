from pathlib import Path

from binding.api_model import build_api_model
from binding.api_policy import ApiPolicy, validate_policy_against_declarations
from binding.ir import parse_source


POLICY_PATH = Path(__file__).parents[1] / "binding" / "api_policy.json"


def test_private_runtime_helpers_are_not_public():
    ir = parse_source(
        "void mp_lv_init_gc(void); void mp_lv_deinit_gc(void); "
        "void *mp_lv_get_roots(void); void lv_init(void);"
    )
    model = build_api_model(ir)
    functions = {function.c_name: function for function in model.functions}

    for name in ("mp_lv_init_gc", "mp_lv_deinit_gc", "mp_lv_get_roots"):
        assert functions[name].visibility == "private"
    assert functions["lv_init"].visibility == "public"


def test_private_global_struct_is_not_public():
    ir = parse_source(
        "typedef struct _lv_global_t { int state; } lv_global_t; "
        "typedef struct _lv_obj_t lv_obj_t;"
    )
    model = build_api_model(ir)
    structs = {struct.python_name: struct for struct in model.structs}

    assert structs["global_t"].visibility == "private"
    assert structs["obj_t"].visibility == "private"
    assert structs["obj_t"].policy_reason == "not reachable from a public binding boundary"


def test_private_global_accessor_is_not_public():
    ir = parse_source(
        "typedef struct _lv_global_t lv_global_t; "
        "lv_global_t *lv_global_default(void);"
    )
    function = next(
        item for item in build_api_model(ir).functions
        if item.c_name == "lv_global_default"
    )
    assert function.visibility == "private"


def test_unsupported_functions_require_explicit_waivers():
    policy = ApiPolicy.from_file(POLICY_PATH)
    assert set(policy.unsupported_functions) == {
        "lv_animimg_get_src",
        "lv_arclabel_set_text_fmt",
        "lv_buttonmatrix_get_map",
        "lv_keyboard_get_map_array",
        "lv_label_set_text_fmt",
        "lv_label_set_text_vfmt",
        "lv_msgbox_add_text_fmt",
        "lv_spangroup_set_span_text_fmt",
        "lv_table_set_cell_value_fmt",
        "lv_subject_snprintf",
        "lv_span_set_text_fmt",
        "lv_snprintf",
        "lv_vsnprintf",
        "lv_text_set_text_vfmt",
    }
    for record in policy.unsupported_functions.values():
        assert record.reason and record.test


def test_internal_callback_hooks_are_not_public():
    ir = parse_source(
        "typedef unsigned int uint32_t; "
        "extern int (*lv_text_encoded_next)(const char *, uint32_t *);"
    )
    model = build_api_model(ir)
    variable = next(
        item for item in model.variables if item.c_name == "lv_text_encoded_next"
    )
    assert variable.visibility == "private"


def test_private_object_storage_structs_are_not_public():
    policy = ApiPolicy.from_file(POLICY_PATH)
    assert {"lv_obj_spec_attr_t", "lv_obj_style_t"} <= set(policy.private_structs)


def test_symbol_identifier_enum_is_private():
    ir = parse_source(
        "typedef enum _lv_str_symbol_id_t { LV_STR_SYMBOL_ID_OK } _lv_str_symbol_id_t;"
    )
    enum = build_api_model(ir).enums[0]
    assert enum.visibility == "private"


def test_tjpgd_exception_is_target_specific():
    # LV_USE_TJPGD is 0 on MicroPython and CircuitPython (jpegio owns the JPEG
    # decoder there); only CPython keeps LVGL's built-in TJPGD.
    ir = parse_source(
        "void lv_tjpgd_init(void); void lv_tjpgd_deinit(void);"
    )
    model = build_api_model(ir)
    functions = {function.c_name: function for function in model.functions}

    assert functions["lv_tjpgd_init"].available_on == ("cpython",)
    assert functions["lv_tjpgd_deinit"].available_on == ("cpython",)


def test_policy_file_is_complete_for_the_current_translation_unit():
    source = Path(__file__).parents[1] / "generated" / "lvgl.pp"
    from binding.ir import parse_source

    declarations = parse_source(source.read_text(encoding="utf-8"))
    policy = ApiPolicy.from_file(POLICY_PATH)
    validate_policy_against_declarations(policy, declarations)


def test_policy_records_have_reason_and_test_references():
    policy = ApiPolicy.from_file(POLICY_PATH)

    assert policy.private_functions
    assert policy.private_structs
    assert policy.target_exceptions
    for record in policy.private_functions.values():
        assert record.reason and record.test
    for record in policy.unsupported_functions.values():
        assert record.reason and record.test
    for record in policy.private_structs.values():
        assert record.reason and record.test
    for record in policy.private_enums.values():
        assert record.reason and record.test
    for record in policy.private_variables.values():
        assert record.reason and record.test
    for record in policy.target_exceptions.values():
        assert record.reason and record.test


def test_generated_api_model_hash_is_valid():
    import json

    from binding.verify_api import validate_api_data

    data = json.loads(
        (Path(__file__).parents[1] / "generated" / "api.json").read_text(
            encoding="utf-8"
        )
    )
    assert validate_api_data(data) == []
