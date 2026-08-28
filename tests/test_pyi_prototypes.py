"""Unit tests for binding/pyi_prototypes.py (IR/.pyi enrichment only)."""

from __future__ import annotations

from pathlib import Path

from binding.pyi_prototypes import (
    enrich_function_info,
    enrich_ir_metadata,
    enrich_struct_function_info,
    lookup_pp_proto,
    normalize_return_type,
    parse_param,
    parse_pp_prototypes,
    split_params,
    strip_receiver_args,
    struct_method_c_name,
)


def test_split_params_empty_and_void():
    assert split_params("") == []
    assert split_params("void") == []
    assert split_params("  void  ") == []


def test_split_params_nested_parens():
    params = "int x, void (*cb)(lv_event_t * e), int filter"
    assert split_params(params) == [
        "int x",
        "void (*cb)(lv_event_t * e)",
        "int filter",
    ]


def test_parse_param_basic_and_callback():
    assert parse_param("int hor_res") == ("int", "hor_res")
    assert parse_param("lv_display_t * disp") == ("display_t", "disp")
    assert parse_param("uint8_t * px_map") == ("Any", "px_map")
    assert parse_param("void (*event_cb)(lv_event_t * e)") == ("callback", "cb")


def test_normalize_return_type():
    assert normalize_return_type("void") == "NoneType"
    assert normalize_return_type("int32_t") == "int"
    assert normalize_return_type("lv_display_t *") == "display_t"
    assert normalize_return_type("const char *") == "Any"


def test_parse_pp_prototypes_inline(tmp_path: Path):
    pp = tmp_path / "sample.pp"
    pp.write_text(
        "lv_display_t * lv_display_create(int32_t hor_res, int32_t ver_res);\n"
        "void lv_color_to_32(lv_color_t color, lv_opa_t opa);\n",
        encoding="utf-8",
    )
    index = parse_pp_prototypes(pp)
    assert "lv_display_create" in index
    create = index["lv_display_create"]
    assert create["return_type"] == "display_t"
    assert [a["name"] for a in create["args"]] == ["hor_res", "ver_res"]
    assert [a["type"] for a in create["args"]] == ["int", "int"]


def test_enrich_function_info_backfills_empty_args():
    pp_index = {
        "lv_display_create": {
            "type": "function",
            "args": [
                {"type": "int", "name": "hor_res"},
                {"type": "int", "name": "ver_res"},
            ],
            "return_type": "display_t",
        }
    }
    info = {"type": "function", "args": [], "return_type": None}
    enriched = enrich_function_info("display_create", info, pp_index)
    assert enriched["args"] == pp_index["lv_display_create"]["args"]
    assert enriched["return_type"] == "display_t"


def test_enrich_function_info_aligns_module_args_to_pp():
    existing = [{"type": "int", "name": "ms"}]
    pp_index = {
        "lv_tick_inc": {
            "type": "function",
            "args": [{"type": "int", "name": "period"}],
            "return_type": "NoneType",
        }
    }
    info = {"type": "function", "args": existing, "return_type": "NoneType"}
    enriched = enrich_function_info("tick_inc", info, pp_index)
    assert enriched["args"] == pp_index["lv_tick_inc"]["args"]


def test_struct_method_c_name():
    assert struct_method_c_name("color_t", "to_32") == "lv_color_to_32"
    assert struct_method_c_name("display_t", "delete") == "lv_display_del"


def test_enrich_struct_function_info_from_pp(tmp_path: Path):
    pp = tmp_path / "sample.pp"
    pp.write_text(
        "uint32_t lv_color_to_32(lv_color_t color, lv_opa_t opa);\n",
        encoding="utf-8",
    )
    pp_index = parse_pp_prototypes(pp)
    info = {"type": "function", "args": [], "return_type": None}
    enriched = enrich_struct_function_info("color_t", "to_32", info, pp_index)
    assert [a["name"] for a in enriched["args"]] == ["opa"]
    assert enriched["return_type"] == "int"


def test_strip_receiver_args_struct_eq_keeps_second_operand():
    args = [
        {"type": "color_t", "name": "c1"},
        {"type": "color_t", "name": "c2"},
    ]
    stripped = strip_receiver_args(args, receiver_struct="color_t")
    assert [a["name"] for a in stripped] == ["c2"]


def test_strip_receiver_args_obj_parent_is_not_receiver():
    args = [{"type": "lv_obj_t*", "name": "parent"}]
    stripped = strip_receiver_args(args, receiver_obj="obj")
    assert stripped == args


def test_enrich_function_info_align_to_keeps_base():
    pp_index = {
        "lv_obj_align_to": {
            "type": "function",
            "args": [
                {"type": "obj", "name": "obj"},
                {"type": "obj", "name": "base"},
                {"type": "align_t", "name": "align"},
                {"type": "int", "name": "x_ofs"},
                {"type": "int", "name": "y_ofs"},
            ],
            "return_type": "NoneType",
        }
    }
    info = {
        "type": "function",
        "args": [
            {"type": "lv_obj_t*", "name": "base"},
            {"type": "int", "name": "align"},
            {"type": "int", "name": "x_ofs"},
            {"type": "int", "name": "y_ofs"},
            {"type": "lv_obj_t*", "name": "obj"},
        ],
        "return_type": "NoneType",
    }
    enriched = enrich_function_info("align_to", info, pp_index, obj_name="obj")
    assert [a["name"] for a in enriched["args"]] == [
        "base",
        "align",
        "x_ofs",
        "y_ofs",
    ]


def test_enrich_ir_metadata_module_and_struct():
    pp_index = {
        "lv_display_create": {
            "type": "function",
            "args": [
                {"type": "int", "name": "hor_res"},
                {"type": "int", "name": "ver_res"},
            ],
            "return_type": "display_t",
        },
        "lv_color_to_32": {
            "type": "function",
            "args": [
                {"type": "color_t", "name": "color"},
                {"type": "int", "name": "opa"},
            ],
            "return_type": "int",
        },
    }
    metadata = {
        "functions": {
            "display_create": {"type": "function", "args": [], "return_type": None},
        },
        "objects": {},
        "struct_functions": {
            "color_t": {
                "to_32": {"type": "function", "args": [], "return_type": None},
            },
        },
    }
    enriched = enrich_ir_metadata(metadata, pp_index)
    assert enriched["functions"]["display_create"]["args"]
    assert enriched["struct_functions"]["color_t"]["to_32"]["args"]


def test_lookup_pp_proto_struct_method():
    pp_index = {
        "lv_display_add_event_cb": {
            "type": "function",
            "args": [
                {"type": "display_t", "name": "disp"},
                {"type": "callback", "name": "event_cb"},
                {"type": "int", "name": "filter"},
                {"type": "void*", "name": "user_data"},
            ],
            "return_type": "NoneType",
        }
    }
    proto = lookup_pp_proto(pp_index, "add_event_cb", struct_name="display_t")
    assert proto is not None
    assert [a["name"] for a in proto["args"]] == [
        "disp",
        "event_cb",
        "filter",
        "user_data",
    ]


def test_enrich_struct_function_info_reorders_and_keeps_callback_typing():
    pp_index = {
        "lv_display_add_event_cb": {
            "type": "function",
            "args": [
                {"type": "display_t", "name": "disp"},
                {"type": "event_cb_t", "name": "event_cb"},
                {"type": "event_code_t", "name": "filter"},
                {"type": "void*", "name": "user_data"},
            ],
            "return_type": "NoneType",
        }
    }
    info = {
        "type": "function",
        "args": [
            {"type": "void*", "name": "user_data"},
            {
                "type": "callback",
                "name": "event_cb",
                "function": {
                    "args": [{"type": "event_t", "name": "e"}],
                    "return_type": None,
                },
            },
            {"type": "int", "name": "filter"},
            {"type": "display_t", "name": "disp"},
        ],
        "return_type": "NoneType",
    }
    enriched = enrich_struct_function_info(
        "display_t", "add_event_cb", info, pp_index
    )
    names = [arg["name"] for arg in enriched["args"]]
    assert names == ["event_cb", "filter", "user_data"]
    event_cb = enriched["args"][0]
    assert event_cb["type"] == "callback"
    assert event_cb["function"]["args"] == [{"type": "event_t", "name": "e"}]


def test_lookup_pp_proto_falls_back_to_obj_method():
    pp_index = {
        "lv_obj_add_event_cb": {
            "type": "function",
            "args": [
                {"type": "obj", "name": "obj"},
                {"type": "event_cb_t", "name": "event_cb"},
                {"type": "int", "name": "filter"},
                {"type": "void*", "name": "user_data"},
            ],
            "return_type": "event_dsc_t",
        }
    }
    proto = lookup_pp_proto(pp_index, "add_event_cb", obj_name="btn")
    assert proto is not None
    assert [a["name"] for a in proto["args"]] == [
        "obj",
        "event_cb",
        "filter",
        "user_data",
    ]


def test_enrich_function_info_reorders_widget_method_args():
    pp_index = {
        "lv_obj_add_event_cb": {
            "type": "function",
            "args": [
                {"type": "obj", "name": "obj"},
                {"type": "event_cb_t", "name": "event_cb"},
                {"type": "event_code_t", "name": "filter"},
                {"type": "void*", "name": "user_data"},
            ],
            "return_type": "event_dsc_t",
        }
    }
    info = {
        "type": "function",
        "args": [
            {"type": "void*", "name": "user_data"},
            {
                "type": "callback",
                "name": "event_cb",
                "function": {
                    "args": [{"type": "event_t", "name": "e"}],
                    "return_type": None,
                },
            },
            {"type": "int", "name": "filter"},
            {"type": "lv_obj_t*", "name": "obj"},
        ],
        "return_type": "event_dsc_t",
    }
    enriched = enrich_function_info(
        "add_event_cb", info, pp_index, obj_name="btn"
    )
    names = [arg["name"] for arg in enriched["args"]]
    assert names == ["event_cb", "filter", "user_data"]
    assert enriched["args"][0]["type"] == "callback"


def test_enrich_function_info_swap_strips_obj1(tmp_path: Path):
    pp_index = {
        "lv_obj_swap": {
            "type": "function",
            "args": [
                {"type": "obj_t", "name": "obj1"},
                {"type": "obj_t", "name": "obj2"},
            ],
            "return_type": "NoneType",
        }
    }
    info = {
        "type": "function",
        "args": [
            {"type": "obj_t", "name": "obj1"},
            {"type": "obj_t", "name": "obj2"},
            {"type": "lv_obj_t*", "name": "parent"},
        ],
        "return_type": "NoneType",
    }
    enriched = enrich_function_info("swap", info, pp_index, obj_name="obj")
    assert [a["name"] for a in enriched["args"]] == ["obj2"]


def test_enrich_module_function_aligns_pp_types():
    pp_index = {
        "lv_screen_load_anim": {
            "type": "function",
            "args": [
                {"type": "obj", "name": "scr"},
                {"type": "screen_load_anim_t", "name": "anim_type"},
                {"type": "int", "name": "time"},
                {"type": "int", "name": "delay"},
                {"type": "bool", "name": "auto_del"},
            ],
            "return_type": "NoneType",
        }
    }
    info = {
        "type": "function",
        "args": [
            {"type": "lv_obj_t*", "name": "scr"},
            {"type": "int", "name": "anim_type"},
            {"type": "int", "name": "time"},
            {"type": "int", "name": "delay"},
            {"type": "bool", "name": "auto_del"},
        ],
        "return_type": "NoneType",
    }
    enriched = enrich_function_info("screen_load_anim", info, pp_index)
    assert enriched["args"][1]["type"] == "screen_load_anim_t"


def test_parse_pp_callback_and_struct_fields(tmp_path: Path):
    from binding.pyi_prototypes import (
        build_callback_typedef_map,
        parse_pp_callback_typedefs,
        parse_pp_struct_fields,
    )

    pp = tmp_path / "sample.pp"
    pp.write_text(
        "typedef void (*lv_anim_custom_exec_cb_t)(lv_anim_t * a, int32_t v);\n"
        "typedef void (*lv_anim_exec_xcb_t)(void *, int32_t v);\n"
        "typedef struct {\n"
        "    uint8_t blue;\n"
        "    uint8_t green;\n"
        "    uint8_t red;\n"
        "} lv_color_t;\n",
        encoding="utf-8",
    )
    callbacks = parse_pp_callback_typedefs(pp)
    assert "anim_custom_exec_cb_t" in callbacks
    assert callbacks["anim_custom_exec_cb_t"]["function"]["args"][0]["type"] == "anim_t"
    xcb = callbacks["anim_exec_xcb_t"]["function"]["args"][0]
    assert xcb["type"] == "anim_t"
    fields = parse_pp_struct_fields(pp)
    assert fields["color_t"] == [
        {"name": "blue", "type": "int"},
        {"name": "green", "type": "int"},
        {"name": "red", "type": "int"},
    ]
    merged = build_callback_typedef_map(pp)
    assert "anim_exec_xcb_t" in merged


def test_build_enum_typedef_map_from_pp(tmp_path: Path):
    from binding.pyi_prototypes import build_enum_typedef_map

    pp = tmp_path / "sample.pp"
    pp.write_text(
        "typedef enum {\n"
        "    LV_SCREEN_LOAD_ANIM_NONE,\n"
        "} lv_screen_load_anim_t;\n"
        "typedef enum {\n"
        "    LV_EVENT_ALL,\n"
        "} lv_event_code_t;\n"
        "typedef enum {\n"
        "    LV_PART_MAIN,\n"
        "} lv_part_t;\n",
        encoding="utf-8",
    )
    enum_names = ["SCREEN_LOAD_ANIM", "EVENT", "PART"]
    mapping = build_enum_typedef_map(enum_names, pp)
    assert mapping["screen_load_anim_t"] == "SCREEN_LOAD_ANIM"
    assert mapping["event_code_t"] == "EVENT"
    assert mapping["part_t"] == "PART"


def test_enrich_return_type_from_pp_replaces_function_pointer():
    from binding.pyi_prototypes import enrich_return_type_from_pp

    assert enrich_return_type_from_pp("function pointer", "tick_get_cb_t") == "tick_get_cb_t"
    assert enrich_return_type_from_pp("display_t", "tick_get_cb_t") == "display_t"
    assert enrich_return_type_from_pp(None, "indev_read_cb_t") == "indev_read_cb_t"


def test_enrich_struct_getter_callbacks_from_pp(tmp_path: Path):
    from binding.pyi_prototypes import build_callback_typedef_map

    pp = tmp_path / "callbacks.pp"
    pp.write_text(
        "typedef void (*lv_indev_read_cb_t)(lv_indev_t * indev, lv_indev_data_t * data);\n"
        "typedef void (*lv_group_focus_cb_t)(lv_group_t * group);\n"
        "typedef void (*lv_group_edge_cb_t)(lv_group_t * group, bool edge);\n"
        "lv_indev_read_cb_t lv_indev_get_read_cb(lv_indev_t * indev);\n"
        "lv_group_focus_cb_t lv_group_get_focus_cb(const lv_group_t * group);\n"
        "lv_group_edge_cb_t lv_group_get_edge_cb(const lv_group_t * group);\n",
        encoding="utf-8",
    )
    pp_index = parse_pp_prototypes(pp)
    callback_typedefs = build_callback_typedef_map(pp)

    for struct, method, expected in [
        ("indev_t", "get_read_cb", "indev_read_cb_t"),
        ("group_t", "get_focus_cb", "group_focus_cb_t"),
        ("group_t", "get_edge_cb", "group_edge_cb_t"),
    ]:
        info = {"type": "function", "args": [], "return_type": "function pointer"}
        enriched = enrich_struct_function_info(
            struct,
            method,
            info,
            pp_index,
            callback_typedefs=callback_typedefs,
        )
        assert enriched["return_type"] == expected


def test_enrich_module_tick_get_cb_from_pp(tmp_path: Path):
    from binding.pyi_prototypes import build_callback_typedef_map

    pp = tmp_path / "tick.pp"
    pp.write_text(
        "typedef uint32_t (*lv_tick_get_cb_t)(void);\n"
        "lv_tick_get_cb_t lv_tick_get_cb(void);\n",
        encoding="utf-8",
    )
    pp_index = parse_pp_prototypes(pp)
    callback_typedefs = build_callback_typedef_map(pp)
    info = {"type": "function", "args": [], "return_type": "function pointer"}
    enriched = enrich_function_info(
        "tick_get_cb",
        info,
        pp_index,
        callback_typedefs=callback_typedefs,
    )
    assert enriched["return_type"] == "tick_get_cb_t"


def test_merge_pp_arg_prefers_typedef_over_stale_ir_callback():
    from binding.pyi_prototypes import merge_pp_arg

    callback_typedefs = {
        "indev_read_cb_t": {
            "type": "callback",
            "function": {
                "args": [
                    {"type": "indev_t", "name": "indev"},
                    {"type": "indev_data_t", "name": "data"},
                ],
                "return_type": "NoneType",
            },
        },
    }
    pp_arg = {"type": "indev_read_cb_t", "name": "read_cb"}
    ir_arg = {
        "type": "callback",
        "name": "read_cb",
        "function": {"args": [], "return_type": "void"},
    }
    merged = merge_pp_arg(pp_arg, ir_arg, callback_typedefs=callback_typedefs)
    assert merged["function"]["args"] == callback_typedefs["indev_read_cb_t"]["function"]["args"]


def test_is_static_struct_method():
    from binding.pyi_prototypes import is_static_struct_method

    pp_index = {
        "lv_style_is_const": {
            "type": "function",
            "args": [{"type": "style_t", "name": "style"}],
            "return_type": "bool",
        },
    }
    info = {
        "type": "function",
        "args": [{"type": "style_t", "name": "style"}],
        "return_type": "bool",
    }
    assert is_static_struct_method("style_t", "is_const", info, pp_index)
    assert not is_static_struct_method(
        "style_t",
        "copy",
        {"type": "function", "args": [{"type": "style_t", "name": "src"}], "return_type": "NoneType"},
        pp_index,
    )
    assert is_static_struct_method(
        "point_precise_t",
        "from_precise",
        {
            "type": "function",
            "args": [{"type": "point_precise_t", "name": "p"}],
            "return_type": "point_t",
        },
        pp_index,
    )
