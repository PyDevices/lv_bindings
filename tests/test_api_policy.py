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
    assert structs["obj_t"].visibility == "public"


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


def test_tjpgd_exception_is_target_specific():
    ir = parse_source(
        "void lv_tjpgd_init(void); void lv_tjpgd_deinit(void);"
    )
    model = build_api_model(ir)
    functions = {function.c_name: function for function in model.functions}

    assert functions["lv_tjpgd_init"].available_on == ("micropython",)
    assert functions["lv_tjpgd_deinit"].available_on == ("micropython",)


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
    for record in policy.private_structs.values():
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
