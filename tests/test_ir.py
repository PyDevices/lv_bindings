from binding.ir import DeclarationIndex, parse_source


def test_parse_source_captures_target_neutral_declarations():
    source = """\
typedef struct point {
    int x;
    const unsigned y: 3;
} point_t;
typedef void (*event_cb_t)(point_t *point, int code);
enum mode { MODE_OFF, MODE_ON = 2 };
extern int global_value;
static inline int point_sum(point_t *point, int extra);
"""

    ir = parse_source(source, filename="fixture.h")

    assert ir.structs[0].name == "point"
    assert ir.structs[0].typedef_names == ("point_t",)
    assert [field.name for field in ir.structs[0].fields] == ["x", "y"]
    assert ir.structs[0].fields[1].bit_width == "3"
    assert ir.structs[0].fields[1].type.canonical() == "const unsigned"

    assert ir.enums[0].members == ("MODE_OFF", "MODE_ON")
    assert ir.enums[0].values == (("MODE_OFF", None), ("MODE_ON", "2"))
    assert ir.typedefs_by_name["event_cb_t"].type.canonical() == (
        "void (point_t *, int) *"
    )
    assert "event_cb_t" in ir.callback_typedefs
    assert ir.variables[0].name == "global_value"
    assert ir.functions_by_name["point_sum"].signature == (
        "int point_sum(point_t *, int)"
    )
    assert ir.functions_by_name["point_sum"].location == ir.functions[0].location
    assert ir.functions_by_name["point_sum"].storage == ("static",)
    assert ir.functions_by_name["point_sum"].function_specifiers == ("inline",)


def test_parse_source_preserves_arrays_and_variadic_functions():
    ir = parse_source(
        "typedef int values_t[4]; int format(const char *fmt, ...);",
        filename="arrays.h",
    )

    assert ir.typedefs_by_name["values_t"].type.canonical() == "int[4]"
    function = ir.functions_by_name["format"]
    assert function.variadic
    assert function.signature == "int format(const char *, ...)"
    assert function.parameters[0].type.canonical() == "const char *"


def test_parse_source_normalizes_void_parameter_lists():
    ir = parse_source("void no_args(void); typedef void (*callback_t)(void);")

    assert ir.functions_by_name["no_args"].parameters == ()
    callback = ir.typedefs_by_name["callback_t"].type.target
    assert callback is not None
    assert callback.parameters == ()
    assert callback.canonical() == "void ()"


def test_parse_source_preserves_pointer_qualifiers():
    ir = parse_source("int read(char *const buffer);", filename="qualifiers.h")

    assert ir.functions_by_name["read"].parameters[0].type.canonical() == (
        "char * const"
    )


def test_declaration_index_resolves_aliases_and_struct_methods():
    ir = parse_source(
        "typedef struct widget { int value; } widget_t; "
        "int widget_set_value(widget_t *widget, int value); "
        "int helper(widget_t *widget);",
        filename="index.h",
    )

    index = DeclarationIndex.from_ir(ir)

    assert index.first_argument_type_name("widget_set_value") == "widget_t"
    assert [function.name for function in index.struct_functions("widget_t")] == [
        "widget_set_value"
    ]
    assert index.structs_by_name["widget_t"].name == "widget"


def test_parse_ast_merges_forward_declarations_and_aliases():
    ir = parse_source(
        "struct node; typedef struct node node_t; struct node { int value; }; "
        "enum state; typedef enum state state_t; enum state { STATE_READY = 4 };",
        filename="forward.h",
    )

    assert [(struct.name, struct.typedef_names, struct.complete) for struct in ir.structs] == [
        ("node", ("node_t",), True)
    ]
    assert ir.structs[0].fields[0].name == "value"
    assert [(enum.name, enum.typedef_names, enum.values) for enum in ir.enums] == [
        ("state", ("state_t",), (("STATE_READY", "4"),))
    ]


def test_parse_source_keeps_anonymous_struct_identity():
    ir = parse_source(
        "typedef struct { int x; } point_t; typedef struct { int y; } other_t;",
        filename="anonymous.h",
    )

    assert [struct.name for struct in ir.structs] == [None, None]
    assert [struct.typedef_names for struct in ir.structs] == [("point_t",), ("other_t",)]


def test_parse_source_captures_anonymous_union_and_nested_record_types():
    ir = parse_source(
        "typedef union { int code; float value; } result_t; "
        "typedef struct container { struct { int x; } point; } container_t;",
        filename="anonymous_union.h",
    )

    assert ir.structs[0].kind == "union"
    assert ir.structs[0].name is None
    assert ir.structs[0].typedef_names == ("result_t",)
    point_type = ir.structs[1].fields[0].type
    assert point_type.kind == "struct"
    assert point_type.name is None
