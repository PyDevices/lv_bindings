from binding.api_model import api_hash_for_dict, build_api_model
from binding.ir import parse_source


def test_api_model_classifies_common_declarations_without_target_policy():
    declarations = parse_source(
        "typedef struct _lv_obj_t lv_obj_t; "
        "typedef struct widget { int value; } widget_t; "
        "typedef void (*changed_cb_t)(widget_t *widget); "
        "lv_obj_t *lv_widget_create(lv_obj_t *parent); "
        "void lv_widget_set_value(lv_obj_t *widget, int value); "
        "int lv_widget_static(int value); "
        "int lv_count(int limit); "
        "enum mode { MODE_OFF = 0, MODE_ON = 1 };",
        filename="api.h",
    )

    model = build_api_model(declarations, module_prefix="lv", base_obj_type="lv_obj_t")

    functions = {function.c_name: function for function in model.functions}
    assert functions["lv_widget_create"].role == "constructor"
    assert functions["lv_widget_set_value"].role == "object_method"
    assert functions["lv_widget_set_value"].python_name == "set_value"
    assert functions["lv_widget_static"].role == "object_method"
    assert functions["lv_widget_static"].static is True
    assert functions["lv_count"].role == "module"
    assert functions["lv_count"].available_on == (
        "micropython",
        "circuitpython",
        "cpython",
    )
    assert functions["lv_count"].static is False
    assert model.objects[0].methods == ("set_value", "static")
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
    assert model.validation_errors() == ()
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


def test_api_model_records_module_and_widget_enum_ownership():
    declarations = parse_source(
        "typedef struct _lv_obj_t lv_obj_t; "
        "lv_obj_t *lv_obj_create(lv_obj_t *parent); "
        "lv_obj_t *lv_bar_create(lv_obj_t *parent); "
        "typedef enum { LV_BAR_MODE_NORMAL = 0, LV_BAR_MODE_RANGE = 1 } lv_bar_mode_t; "
        "typedef enum { LV_EVENT_NONE = 0, LV_EVENT_CLICKED = 1 } lv_event_code_t; "
        "typedef enum { LV_OBJ_FLAG_HIDDEN = 1, LV_OBJ_FLAG_CLICKABLE = 2 } lv_obj_flag_t;",
        filename="enum-ownership.h",
    )

    model = build_api_model(declarations)
    enums = {enum.typedef_names[0]: enum for enum in model.enums if enum.typedef_names}

    assert enums["lv_bar_mode_t"].module_name is None
    assert enums["lv_bar_mode_t"].owners == (("bar", "MODE"),)
    assert [member[0] for member in enums["lv_bar_mode_t"].members] == [
        "NORMAL",
        "RANGE",
    ]
    assert enums["lv_event_code_t"].module_name == "EVENT"
    assert enums["lv_event_code_t"].owners == ()
    assert enums["lv_obj_flag_t"].module_name == "OBJ_FLAG"
    assert enums["lv_obj_flag_t"].owners == (("obj", "FLAG"),)


def test_api_model_uses_typedef_and_member_stems_for_singleton_enums():
    declarations = parse_source(
        "typedef enum { LV_ANIMIMG_PART_MAIN } lv_animimg_part_t;",
        filename="singleton-enum.h",
    )

    model = build_api_model(declarations)
    enum = next(item for item in model.enums if item.typedef_names)

    assert enum.module_name == "ANIM_IMAGE_PART"
    assert enum.members == (("MAIN", None),)


def test_api_model_exposes_string_symbol_namespace_with_string_members():
    declarations = parse_source(
        "enum _lv_str_symbol_id_t { LV_STR_SYMBOL_OK, LV_STR_SYMBOL_CANCEL };",
        filename="symbols.h",
    )

    model = build_api_model(declarations)
    symbol = next(
        enum
        for enum in model.enums
        if enum.python_name == "SYMBOL" and enum.visibility == "public"
    )

    assert symbol.python_name == "SYMBOL"
    assert symbol.visibility == "public"
    assert symbol.member_type == "str"
    assert symbol.members == (("OK", None), ("CANCEL", None))


def test_api_model_records_target_neutral_python_type_views():
    declarations = parse_source(
        "typedef struct _lv_obj_t lv_obj_t; "
        "typedef unsigned char uint8_t; "
        "typedef struct point { int x; } point_t; "
        "typedef enum { LV_MODE_OFF = 0, LV_MODE_ON = 1 } lv_mode_t; "
        "typedef void (*event_cb_t)(int value); "
        "lv_obj_t *lv_obj_create(lv_obj_t *parent); "
        "lv_obj_t *lv_widget_create(lv_obj_t *parent); "
        "void lv_unsupported(long double value); "
        "void lv_widget_set(lv_obj_t *widget, event_cb_t callback, "
        "const char *text, uint8_t *samples, point_t *point, "
        "lv_mode_t mode, void *user_data);",
        filename="type-views.h",
    )

    model = build_api_model(declarations)
    functions = {function.c_name: function for function in model.functions}
    setter = functions["lv_widget_set"]

    assert setter.return_view.python_type == "None"
    assert [view.category for view in setter.parameter_views] == [
        "object_pointer",
        "callback",
        "string",
        "typed_buffer",
        "struct_pointer",
        "enum",
        "opaque_pointer",
    ]
    assert [view.python_type for view in setter.parameter_views] == [
        "obj",
        "Callable[[int], None]",
        "str",
        "Any",
        "point_t",
        "MODE | int",
        "Any",
    ]
    callback = next(item for item in model.typedefs if item.name == "event_cb_t")
    assert callback.type_view.python_type == "Callable[[int], None]"
    obj_typedef = next(item for item in model.typedefs if item.name == "obj_t")
    assert obj_typedef.type_view.python_type == "obj"
    assert obj_typedef.type_view.category == "object"
    point = next(item for item in model.structs if item.python_name == "point_t")
    assert point.field_views[0].python_type == "int"
    unsupported = functions["lv_unsupported"].parameter_views[0]
    assert unsupported.python_type == "Any"
    assert unsupported.category == "unknown"
    assert unsupported.conversion == "unsupported"


def test_api_model_does_not_reference_private_structs_in_public_views():
    declarations = parse_source(
        "typedef struct _lv_global_t { int state; } lv_global_t; "
        "lv_global_t *lv_global_default(void);",
        filename="private-type.h",
    )

    model = build_api_model(declarations)
    global_struct = next(item for item in model.structs if item.python_name == "global_t")
    function = next(item for item in model.functions if item.c_name == "lv_global_default")

    assert global_struct.visibility == "private"
    assert function.return_view.python_type == "Any"
    assert function.return_view.category == "struct_pointer"


def test_api_model_detects_duplicate_exports():
    from dataclasses import replace

    declarations = parse_source("void lv_dup(int);")

    model = build_api_model(declarations)
    duplicate = replace(model, functions=model.functions + (model.functions[0],))

    assert any(
        "duplicate export module.dup" in error
        for error in duplicate.validation_errors()
    )
