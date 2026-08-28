from binding.api_model import api_hash_for_dict, build_api_model
from binding.ir import parse_source


def test_api_model_classifies_common_declarations_without_target_policy():
    declarations = parse_source(
        "typedef struct _lv_obj_t lv_obj_t; "
        "typedef struct widget { int value; } widget_t; "
        "typedef void (*changed_cb_t)(widget_t *widget); "
        "lv_obj_t *lv_widget_create(lv_obj_t *parent); "
        "void lv_widget_set_value(lv_obj_t *widget, int value); "
        "int lv_widget_count(int limit); "
        "enum mode { MODE_OFF = 0, MODE_ON = 1 };",
        filename="api.h",
    )

    model = build_api_model(declarations, module_prefix="lv", base_obj_type="lv_obj_t")

    functions = {function.c_name: function for function in model.functions}
    assert functions["lv_widget_create"].role == "constructor"
    assert functions["lv_widget_set_value"].role == "object_method"
    assert functions["lv_widget_set_value"].python_name == "set_value"
    assert functions["lv_widget_count"].role == "module"
    assert functions["lv_widget_count"].available_on == (
        "micropython",
        "circuitpython",
        "cpython",
    )
    assert functions["lv_widget_count"].static is False
    assert model.objects[0].methods == ("set_value",)
    assert model.objects[0].parent == "obj"
    assert model.objects[0].c_type == "lv_widget_t"
    structs = {struct.c_name: struct for struct in model.structs}
    assert structs["widget"].python_name == "widget_t"
    assert model.enums[0].members == (("MODE_OFF", "0"), ("MODE_ON", "1"))
    assert "widget_t" in {typedef.name for typedef in model.typedefs}


def test_api_model_json_is_deterministic_and_includes_callbacks():
    declarations = parse_source(
        "typedef void (*changed_cb_t)(int value, ...);",
        filename="callback.h",
    )
    model = build_api_model(declarations)
    rendered = model.to_json()

    assert rendered == model.to_json()
    assert len(model.api_hash) == 64
    assert '"api_hash": "{}"'.format(model.api_hash) in rendered
    assert api_hash_for_dict(model.to_dict()) == model.api_hash
    assert '"callback": true' in rendered
    assert '"variadic": true' in rendered


def test_api_model_groups_preprocessor_enum_families_and_constants():
    declarations = parse_source(
        "enum { ENUM_LV_MODE_OFF = 0 }; "
        "enum { ENUM_LV_MODE_ON = 1 }; "
        "enum { ENUM_LV_LIMIT = 4 };"
    )

    model = build_api_model(declarations)

    enums = {enum.python_name: enum for enum in model.enums}
    assert enums["MODE"].members == (("OFF", "0"), ("ON", "1"))
    constants = {constant.python_name: constant for constant in model.constants}
    assert constants["LIMIT"].value == "4"
