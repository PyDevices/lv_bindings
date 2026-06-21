#!/usr/bin/env python3
"""Compare public lvgl module namespaces in generated bindings against MicroPython."""
from __future__ import print_function

import re
import sys
from pathlib import Path

WIDGET_SCOPED_MODULE_ENUMS = frozenset(
    [
        "OBJ_FLAG",
        "IMAGE_FLAGS",
        "IMAGE_SRC",
        "IMAGE_ALIGN",
        "IMAGE_COMPRESS",
        "BAR_MODE",
        "SLIDER_MODE",
        "ARC_MODE",
        "ROLLER_MODE",
        "KEYBOARD_MODE",
        "LABEL_LONG",
        "CHART_UPDATE_MODE",
        "CHART_AXIS",
        "CHART_TYPE",
        "IMAGEBUTTON_STATE",
        "OBJ_POINT_TRANSFORM_FLAG",
        "OBJ_TREE_WALK",
        "OBJ_CLASS_EDITABLE",
        "OBJ_CLASS_GROUP_DEF",
        "OBJ_CLASS_THEME_INHERITABLE",
        "BUTTONMATRIX_CTRL",
        "TABLE_CELL_CTRL",
        "MENU_HEADER",
        "MENU_ROOT_BACK_BUTTON",
        "SCALE_MODE",
    ]
)

WIDGET_ENUM_ATTRS = {
    "obj": ["FLAG"],
    "image": ["FLAGS"],
    "label": ["LONG"],
    "bar": ["MODE"],
}


def mp_module_names(text):
    m = re.search(
        r"(?:lvgl_globals_table|lvgl_module_globals_table)\[\] = \{(.*?)\n\};",
        text,
        re.S,
    )
    if not m:
        return set()
    return set(re.findall(r"MP_ROM_QSTR\(MP_QSTR_(\w+)\)", m.group(1)))


def py_module_names(text):
    names = set(
        re.findall(
            r'PyModule_Add(?:Object|StringConstant|IntConstant)\(m,\s*"([^"]+)"',
            text,
        )
    )
    return names


def mp_obj_enum_attrs(text, obj):
    m = re.search(
        rf"static const mp_rom_map_elem_t {obj}_locals_dict_table\[\] = \{{(.*?)\}};",
        text,
        re.S,
    )
    if not m:
        return set()
    attrs = set()
    for line in m.group(1).splitlines():
        if "_type_base" not in line:
            continue
        q = re.search(r"MP_ROM_QSTR\(MP_QSTR_(\w+)\)", line)
        if q:
            attrs.add(q.group(1))
    return attrs


def py_obj_enum_attrs(text, obj):
    block = re.search(r"PyInit_lvgl\(void\).*?return m;", text, re.S)
    if not block:
        return set()
    attrs = set()
    for m in re.finditer(
        rf'py_lv_{obj}_type\)->tp_dict,\s*"([^"]+)"',
        block.group(0),
    ):
        attrs.add(m.group(1))
    return attrs


def verify(target, text, mp_names):
    errors = []
    if target == "MicroPython":
        names = mp_module_names(text)
        for enum_name in WIDGET_SCOPED_MODULE_ENUMS:
            if enum_name in names:
                errors.append("module exposes widget-scoped enum %s" % enum_name)
        for obj, expected in WIDGET_ENUM_ATTRS.items():
            attrs = mp_obj_enum_attrs(text, obj)
            for attr in expected:
                if attr not in attrs:
                    errors.append("%s missing enum attr %s" % (obj, attr))
        return errors

    names = mp_module_names(text) if target == "CircuitPython" else py_module_names(text)
    for enum_name in WIDGET_SCOPED_MODULE_ENUMS:
        if enum_name in names:
            errors.append("module exposes widget-scoped enum %s" % enum_name)

    if target == "CPython":
        symbol_strings = [n for n in names if n.startswith("SYMBOL_")]
        if symbol_strings:
            errors.append(
                "module exposes SYMBOL_* string constants (%d found)" % len(symbol_strings)
            )
        required = {"C_Pointer", "LvReferenceError", "Blob", "Struct"}
        missing = required - names
        if missing:
            errors.append("module missing exports: %s" % ", ".join(sorted(missing)))
        if "SYMBOL" not in names:
            errors.append("module missing SYMBOL enum namespace")

    if target == "CircuitPython":
        if "LvReferenceError" not in names:
            errors.append("module missing LvReferenceError export")

    obj_enum_fn = mp_obj_enum_attrs if target != "CPython" else py_obj_enum_attrs
    for obj, expected in WIDGET_ENUM_ATTRS.items():
        attrs = obj_enum_fn(text, obj)
        for attr in expected:
            if attr not in attrs:
                errors.append("%s missing enum attr %s" % (obj, attr))

    extra_module_enums = [
        n
        for n in names
        if n in WIDGET_SCOPED_MODULE_ENUMS and n not in mp_names
    ]
    if extra_module_enums and target != "MicroPython":
        pass  # covered above

    return errors


def main(argv):
    generated = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "generated"
    files = {
        "MicroPython": generated / "lvmp.c",
        "CircuitPython": generated / "lvcp.c",
        "CPython": generated / "lvpy.c",
    }
    mp_text = files["MicroPython"].read_text()
    mp_names = mp_module_names(mp_text)

    failed = False
    for target, path in files.items():
        if not path.is_file():
            print("FAIL: missing %s" % path)
            failed = True
            continue
        errors = verify(target, path.read_text(), mp_names)
        if errors:
            failed = True
            print("FAIL %s:" % target)
            for err in errors:
                print("  - %s" % err)
        else:
            print("OK: %s namespace parity" % target)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
