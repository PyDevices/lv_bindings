from binding.ir import parse_source


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
    assert ir.typedefs_by_name["event_cb_t"].type.canonical() == (
        "void (point_t *, int) *"
    )
    assert "event_cb_t" in ir.callback_typedefs
    assert ir.variables[0].name == "global_value"
    assert ir.functions_by_name["point_sum"].signature == (
        "int point_sum(point_t *, int)"
    )
    assert ir.functions_by_name["point_sum"].location == ir.functions[0].location


def test_parse_source_preserves_arrays_and_variadic_functions():
    ir = parse_source(
        "typedef int values_t[4]; int format(const char *fmt, ...);",
        filename="arrays.h",
    )

    assert ir.typedefs_by_name["values_t"].type.canonical() == "int[4]"
    function = ir.functions_by_name["format"]
    assert function.variadic
    assert function.parameters[0].type.canonical() == "const char *"
