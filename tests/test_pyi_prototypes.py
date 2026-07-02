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


def test_enrich_function_info_preserves_existing_args():
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
    assert enriched["args"] == existing


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
    assert [a["name"] for a in enriched["args"]] == ["color", "opa"]
    assert enriched["return_type"] == "int"


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
