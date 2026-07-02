"""Unit tests for binding/pyi_prototypes.py (IR/.pyi enrichment only)."""

from __future__ import annotations

from pathlib import Path

import pytest

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


def test_emit_pyi_widget_method_uses_enriched_ir_arg_order():
    from binding.emit_pyi import PyiEmitter

    metadata = {
        "structs": ["event_t"],
        "objects": {"btn": {}},
        "enums": {},
        "functions": {},
        "struct_functions": {},
        "blobs": [],
        "int_constants": [],
    }
    metadata["objects"]["btn"] = {
        "members": {
            "add_event_cb": {
                "type": "function",
                "args": [
                    {
                        "type": "callback",
                        "name": "event_cb",
                        "function": {
                            "args": [{"type": "event_t", "name": "e"}],
                            "return_type": "NoneType",
                        },
                    },
                    {"type": "int", "name": "filter"},
                    {"type": "void*", "name": "user_data"},
                ],
                "return_type": "event_dsc_t",
            }
        }
    }
    emitter = PyiEmitter(metadata)
    sig = emitter._format_function(
        "add_event_cb",
        metadata["objects"]["btn"]["members"]["add_event_cb"],
        instance_method=True,
        receiver_obj="btn",
    )
    assert "event_cb: Callable[[event_t], None]" in sig
    assert sig.index("event_cb:") < sig.index("filter:")
    assert sig.index("filter:") < sig.index("user_data:")


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


def test_emit_pyi_skips_duplicate_c_pointer_stub():
    from binding.emit_pyi import PyiEmitter
    from io import StringIO

    metadata = {
        "structs": ["C_Pointer", "color_t"],
        "objects": {},
        "enums": {},
        "functions": {},
        "struct_functions": {},
        "struct_fields": {
            "color_t": [
                {"name": "red", "type": "int"},
            ],
        },
        "blobs": [],
        "int_constants": [],
    }
    emitter = PyiEmitter(metadata)
    out = StringIO()
    emitter.emit(out)
    text = out.getvalue()
    assert text.count("class C_Pointer:") == 1
    assert "class C_Pointer(Struct)" not in text
    assert "class color_t(Struct):" in text


def test_emit_pyi_maps_enum_typedefs_to_module_enums():
    from binding.emit_pyi import PyiEmitter

    metadata = {
        "structs": [],
        "objects": {
            "obj": {
                "members": {
                    "add_state": {
                        "type": "function",
                        "args": [{"type": "state_t", "name": "state"}],
                        "return_type": "NoneType",
                    },
                },
            },
        },
        "enums": {
            "STATE": {
                "members": {
                    "DEFAULT": {"type": "enum_member"},
                },
            },
        },
        "enum_typedefs": {"state_t": "STATE"},
        "functions": {},
        "struct_functions": {},
        "blobs": [],
        "int_constants": [],
    }
    emitter = PyiEmitter(metadata)
    sig = emitter._format_function(
        "add_state",
        metadata["objects"]["obj"]["members"]["add_state"],
        instance_method=True,
        receiver_obj="obj",
    )
    assert "state: STATE" in sig


def test_emit_pyi_resolves_xcb_typedef_to_callable():
    from binding.emit_pyi import PyiEmitter

    pp_callbacks = {
        "anim_exec_xcb_t": {
            "type": "callback",
            "function": {
                "args": [
                    {"type": "anim_t", "name": "a"},
                    {"type": "int", "name": "v"},
                ],
                "return_type": "NoneType",
            },
        },
    }
    metadata = {
        "structs": ["anim_t"],
        "objects": {},
        "enums": {},
        "functions": {},
        "struct_functions": {
            "anim_t": {
                "set_exec_cb": {
                    "type": "function",
                    "args": [{"type": "anim_exec_xcb_t", "name": "exec_cb"}],
                    "return_type": "NoneType",
                },
            },
        },
        "callback_typedefs": pp_callbacks,
        "blobs": [],
        "int_constants": [],
    }
    emitter = PyiEmitter(metadata)
    sig = emitter._format_function(
        "set_exec_cb",
        metadata["struct_functions"]["anim_t"]["set_exec_cb"],
        instance_method=True,
        receiver_struct="anim_t",
    )
    assert "exec_cb: Callable[[anim_t, int], None]" in sig


def test_emit_pyi_widget_inherits_obj_methods(tmp_path: Path):
    from binding.emit_pyi import PyiEmitter
    from io import StringIO

    metadata = {
        "structs": [],
        "objects": {
            "obj": {
                "members": {
                    "delete": {
                        "type": "function",
                        "args": [],
                        "return_type": "NoneType",
                    },
                    "align": {
                        "type": "function",
                        "args": [{"type": "int", "name": "align"}],
                        "return_type": "NoneType",
                    },
                }
            },
            "button": {
                "members": {
                    "delete": {
                        "type": "function",
                        "args": [],
                        "return_type": "NoneType",
                    },
                    "set_label": {
                        "type": "function",
                        "args": [{"type": "str", "name": "text"}],
                        "return_type": "NoneType",
                    },
                }
            },
        },
        "enums": {},
        "functions": {},
        "struct_functions": {},
        "blobs": [],
        "int_constants": [],
    }
    emitter = PyiEmitter(metadata)
    out = StringIO()
    emitter.emit(out)
    text = out.getvalue()
    assert "class button(obj):" in text
    assert "def set_label(text: str) -> None" in text
    assert text.count("class button(obj):") == 1
    button_block = text.split("class button(obj):", 1)[1].split("\nclass ", 1)[0]
    assert "def delete(" not in button_block
    assert "def align(" not in button_block


def test_emit_pyi_struct_method_uses_enriched_ir_arg_order():
    from binding.emit_pyi import PyiEmitter

    metadata = {
        "structs": ["display_t", "event_t"],
        "objects": {},
        "enums": {},
        "functions": {},
        "struct_functions": {
            "display_t": {
                "add_event_cb": {
                    "type": "function",
                    "args": [
                        {
                            "type": "callback",
                            "name": "event_cb",
                            "function": {
                                "args": [{"type": "event_t", "name": "e"}],
                                "return_type": "NoneType",
                            },
                        },
                        {"type": "int", "name": "filter"},
                        {"type": "void*", "name": "user_data"},
                    ],
                    "return_type": "NoneType",
                },
            },
        },
        "blobs": [],
        "int_constants": [],
    }
    emitter = PyiEmitter(metadata)
    sig = emitter._format_function(
        "add_event_cb",
        metadata["struct_functions"]["display_t"]["add_event_cb"],
        instance_method=True,
        receiver_struct="display_t",
    )
    assert "event_cb: Callable[[event_t], None]" in sig
    assert sig.index("event_cb:") < sig.index("filter:")
    assert sig.index("filter:") < sig.index("user_data:")


def test_emit_pyi_maps_style_selector_t_composite():
    from binding.emit_pyi import PyiEmitter

    metadata = {
        "structs": ["style_t"],
        "objects": {
            "obj": {
                "members": {
                    "add_style": {
                        "type": "function",
                        "args": [
                            {"type": "style_t", "name": "style"},
                            {"type": "style_selector_t", "name": "selector"},
                        ],
                        "return_type": "NoneType",
                    },
                },
            },
        },
        "enums": {
            "PART": {"members": {"MAIN": {"type": "enum_member"}}},
            "STATE": {"members": {"DEFAULT": {"type": "enum_member"}}},
        },
        "functions": {},
        "struct_functions": {},
        "blobs": [],
        "int_constants": [],
    }
    emitter = PyiEmitter(metadata)
    sig = emitter._format_function(
        "add_style",
        metadata["objects"]["obj"]["members"]["add_style"],
        instance_method=True,
        receiver_obj="obj",
    )
    assert "selector: int | PART | STATE" in sig


def test_emit_pyi_maps_obj_flag_t_to_module_enum():
    from binding.emit_pyi import PyiEmitter
    from io import StringIO

    metadata = {
        "structs": [],
        "objects": {
            "obj": {
                "members": {
                    "FLAG": {
                        "type": "enum_type",
                        "members": {
                            "HIDDEN": {"type": "enum_member"},
                            "CLICKABLE": {"type": "enum_member"},
                        },
                    },
                    "add_flag": {
                        "type": "function",
                        "args": [{"type": "obj_flag_t", "name": "f"}],
                        "return_type": "NoneType",
                    },
                },
            },
        },
        "enums": {},
        "functions": {},
        "struct_functions": {},
        "blobs": [],
        "int_constants": [],
    }
    emitter = PyiEmitter(metadata)
    out = StringIO()
    emitter.emit(out)
    text = out.getvalue()
    assert "class OBJ_FLAG:" in text
    assert "    HIDDEN: int" in text
    assert "    CLICKABLE: int" in text
    sig = emitter._format_function(
        "add_flag",
        metadata["objects"]["obj"]["members"]["add_flag"],
        instance_method=True,
        receiver_obj="obj",
    )
    assert "f: OBJ_FLAG | int" in sig


def test_emit_pyi_suppresses_empty_indev_subtype_stubs():
    from binding.emit_pyi import PyiEmitter
    from io import StringIO

    metadata = {
        "structs": ["indev_pointer_t", "indev_keypad_t", "indev_t"],
        "objects": {},
        "enums": {},
        "functions": {},
        "struct_functions": {},
        "blobs": [],
        "int_constants": [],
    }
    emitter = PyiEmitter(metadata)
    out = StringIO()
    emitter.emit(out)
    text = out.getvalue()
    assert "class indev_pointer_t(Struct)" not in text
    assert "class indev_keypad_t(Struct)" not in text
    assert "# indev_pointer_t: use indev_t instead." in text
    assert "# indev_keypad_t: use indev_t instead." in text
    assert "class indev_t(Struct)" in text


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


def test_emit_pyi_driver_callback_signatures():
    from binding.emit_pyi import PyiEmitter

    callback_typedefs = {
        "tick_get_cb_t": {
            "type": "callback",
            "function": {"args": [], "return_type": "int"},
        },
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
        "group_focus_cb_t": {
            "type": "callback",
            "function": {
                "args": [{"type": "group_t", "name": "group"}],
                "return_type": "NoneType",
            },
        },
        "group_edge_cb_t": {
            "type": "callback",
            "function": {
                "args": [
                    {"type": "group_t", "name": "group"},
                    {"type": "bool", "name": "edge"},
                ],
                "return_type": "NoneType",
            },
        },
        "screen_create_cb_t": {
            "type": "callback",
            "function": {"args": [], "return_type": "obj_t"},
        },
    }
    metadata = {
        "structs": ["indev_t", "indev_data_t", "group_t"],
        "objects": {"obj": {}},
        "enums": {"EVENT": {"members": {}}, "SCREEN_LOAD_ANIM": {"members": {}}},
        "enum_typedefs": {
            "event_code_t": "EVENT",
            "screen_load_anim_t": "SCREEN_LOAD_ANIM",
        },
        "functions": {
            "tick_get_cb": {
                "type": "function",
                "args": [],
                "return_type": "tick_get_cb_t",
            },
            "tick_set_cb": {
                "type": "function",
                "args": [
                    {
                        "type": "callback",
                        "name": "cb",
                        "function": {"args": [], "return_type": "int"},
                    }
                ],
                "return_type": "NoneType",
            },
        },
        "struct_functions": {
            "indev_t": {
                "get_read_cb": {
                    "type": "function",
                    "args": [],
                    "return_type": "indev_read_cb_t",
                },
            },
            "group_t": {
                "get_focus_cb": {
                    "type": "function",
                    "args": [],
                    "return_type": "group_focus_cb_t",
                },
                "get_edge_cb": {
                    "type": "function",
                    "args": [],
                    "return_type": "group_edge_cb_t",
                },
            },
        },
        "callback_typedefs": callback_typedefs,
        "blobs": [],
        "int_constants": [],
    }
    metadata["objects"]["obj"] = {
        "members": {
            "add_screen_create_event": {
                "type": "function",
                "args": [
                    {"type": "event_code_t", "name": "trigger"},
                    {
                        "type": "callback",
                        "name": "screen_create_cb",
                        "function": {"args": [], "return_type": "obj_t"},
                    },
                    {"type": "screen_load_anim_t", "name": "anim_type"},
                    {"type": "int", "name": "duration"},
                    {"type": "int", "name": "delay"},
                ],
                "return_type": "NoneType",
            },
        },
    }
    emitter = PyiEmitter(metadata)

    assert (
        emitter._format_function(
            "tick_get_cb",
            metadata["functions"]["tick_get_cb"],
            instance_method=False,
        )
        == "tick_get_cb() -> Callable[[], int]: ..."
    )
    assert (
        emitter._format_function(
            "tick_set_cb",
            metadata["functions"]["tick_set_cb"],
            instance_method=False,
        )
        == "tick_set_cb(cb: Callable[[], int]) -> None: ..."
    )
    assert (
        emitter._format_function(
            "get_read_cb",
            metadata["struct_functions"]["indev_t"]["get_read_cb"],
            instance_method=True,
            receiver_struct="indev_t",
        )
        == "get_read_cb() -> Callable[[indev_t, indev_data_t], None]: ..."
    )
    assert (
        emitter._format_function(
            "get_focus_cb",
            metadata["struct_functions"]["group_t"]["get_focus_cb"],
            instance_method=True,
            receiver_struct="group_t",
        )
        == "get_focus_cb() -> Callable[[group_t], None]: ..."
    )
    assert (
        emitter._format_function(
            "get_edge_cb",
            metadata["struct_functions"]["group_t"]["get_edge_cb"],
            instance_method=True,
            receiver_struct="group_t",
        )
        == "get_edge_cb() -> Callable[[group_t, bool], None]: ..."
    )
    screen_sig = emitter._format_function(
        "add_screen_create_event",
        metadata["objects"]["obj"]["members"]["add_screen_create_event"],
        instance_method=True,
        receiver_obj="obj",
    )
    assert "screen_create_cb: Callable[[], obj]" in screen_sig
