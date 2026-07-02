"""CPython bookends: phase-2 enum types and PyInit_lvgl / module registration."""
from __future__ import print_function

import collections

from . import runtime
from .analyze import get_enum_member_name, get_enum_members, get_enum_value
from .emit_cpython_native import _resolved_py_func_name
from .helpers import export_name, get_enum_name, is_method_of, is_widget_scoped_only_enum, method_name_from_func_name, sanitize, simplify_identifier


def _member_c_value(value):
    if value.startswith("MP_ROM_INT(") and value.endswith(")"):
        return value[len("MP_ROM_INT(") : -1]
    if value.startswith("&mp_"):
        return value[len("&mp_") :]
    return value


def emit_phase2_enums_cpython():
    """Emit read-only enum namespace types (native CPython API)."""
    if runtime.get("_py_enums_emitted", False):
        return
    runtime.set_("_py_enums_emitted", True)
    enums = runtime.get("enums", {})
    obj_metadata = runtime.get("obj_metadata")
    enum_referenced = collections.OrderedDict()
    module_name = runtime.get("module_name", "lvgl")

    print(
        """
/*
 * CPython phase-2 enum namespace types
 */
"""
    )

    for enum_name in list(enums.keys()):
        members = enums[enum_name]
        if not members:
            continue
        obj_metadata[enum_name] = {"members": collections.OrderedDict()}
        obj_metadata[enum_name]["members"].update(
            {
                get_enum_member_name(enum_member_name): {"type": "enum_member"}
                for enum_member_name in get_enum_members(enum_name)
            }
        )
        obj_enums = [
            other for other in enums.keys() if is_method_of(other, enum_name)
        ]
        obj_metadata[enum_name]["members"].update(
            {
                method_name_from_func_name(other): {"type": "enum_type"}
                for other in obj_enums
            }
        )
        for other in obj_enums:
            if other in obj_metadata:
                obj_metadata[enum_name]["members"][
                    method_name_from_func_name(other)
                ].update(obj_metadata[other])
            if is_widget_scoped_only_enum(other):
                enum_referenced[other] = True
        safe = sanitize(enum_name)
        py_name = export_name(enum_name, "enum")

        print(
            """
static PyObject *py_lv_{safe}_getattro(PyObject *self, PyObject *name)
{{
    (void)self;
    if (!PyUnicode_Check(name)) {{
        PyErr_SetString(PyExc_TypeError, "attribute name must be string");
        return NULL;
    }}
    const char *attr = PyUnicode_AsUTF8(name);
    if (attr == NULL) {{
        return NULL;
    }}
""".format(safe=safe)
        )

        for member_name, member_value in members.items():
            cval = _member_c_value(member_value)
            py_member = export_name(member_name, "enum_member")
            if cval.startswith("LV_SYMBOL_"):
                print(
                    '    if (strcmp(attr, "{member}") == 0) return PyUnicode_FromString({cval});'.format(
                        member=py_member, cval=cval
                    )
                )
            else:
                print(
                    '    if (strcmp(attr, "{member}") == 0) return PyLong_FromLong({cval});'.format(
                        member=py_member, cval=cval
                    )
                )

        print(
            """
    PyErr_Format(PyExc_AttributeError, "'{module}.{py_name}' object has no attribute '%s'", attr);
    return NULL;
}}

static PyTypeObject py_lv_{safe}_type = {{
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "{module}.{py_name}",
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_getattro = py_lv_{safe}_getattro,
    .tp_doc = "LVGL {py_name} enum namespace",
}};
""".format(module=module_name, py_name=py_name, safe=safe)
        )

    runtime.set_("obj_metadata", obj_metadata)
    runtime.set_("enum_referenced", enum_referenced)


def finish_py_module(max_phase):
    """Emit PyInit_lvgl and module-level registration (native CPython API)."""
    int_constants = runtime.get("int_constants", [])
    generated_globals = runtime.get("generated_globals", [])
    enums = runtime.get("enums", {})
    enum_referenced = runtime.get("enum_referenced", collections.OrderedDict())
    generated_structs = runtime.get("generated_structs", {})
    struct_aliases = runtime.get("struct_aliases", collections.OrderedDict())
    cpython_struct_sizes = runtime.get("cpython_struct_sizes", {})
    obj_names = runtime.get("obj_names", [])
    module_funcs = runtime.get("module_funcs", [])

    print(
        """
/*
 * CPython module definition
 */

static int lvgl_mod_initialized = 0;

static PyObject *py_lvgl_init(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    lvpy_lock();
    if (!lvgl_mod_initialized) {
        lv_init();
        lvgl_mod_initialized = 1;
    }
    lvpy_unlock();
    Py_RETURN_NONE;
}

static PyObject *py_lvgl_deinit(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    lvpy_lock();
    if (lvgl_mod_initialized) {
        lv_deinit();
        lvgl_mod_initialized = 0;
    }
    lvpy_unlock();
    Py_RETURN_NONE;
}

static PyMethodDef lvgl_methods[] = {
    {"init", py_lvgl_init, METH_NOARGS, "Initialize LVGL"},
    {"deinit", py_lvgl_deinit, METH_NOARGS, "Deinitialize LVGL"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef lvgl_module_def = {
    PyModuleDef_HEAD_INIT,
    "lvgl",
    "LVGL bindings for CPython (generated)",
    -1,
    lvgl_methods
};
"""
    )

    print("PyMODINIT_FUNC PyInit_lvgl(void)")
    print("{")
    print("    PyObject *m = PyModule_Create(&lvgl_module_def);")
    print("    if (m == NULL) {")
    print("        return NULL;")
    print("    }")

    if max_phase >= 1:
        for int_constant in int_constants:
            name = export_name(int_constant, "constant")
            print(
                '    if (PyModule_AddIntConstant(m, "{name}", {value}) < 0) return NULL;'.format(
                    name=name, value=int_constant
                )
            )
        for global_name in generated_globals:
            if not global_name.startswith("LV_"):
                continue
            if global_name.startswith("LV_SYMBOL_"):
                continue
            py_name = simplify_identifier(global_name)
            if py_name.startswith("LV_"):
                py_name = py_name[3:]
            print(
                '    if (PyModule_AddStringConstant(m, "{name}", {value}) < 0) return NULL;'.format(
                    name=py_name, value=global_name
                )
            )

    if max_phase >= 2:
        for enum_name in enums.keys():
            if enum_name in enum_referenced:
                continue
            safe = sanitize(enum_name)
            py_name = export_name(enum_name, "enum")
            print(
                '    if (PyType_Ready(&py_lv_{safe}_type) < 0) return NULL;'.format(
                    safe=safe
                )
            )
            print(
                '    {{ PyObject *ns = PyType_GenericNew(&py_lv_{safe}_type, NULL, NULL); if (ns == NULL) return NULL; if (PyModule_AddObject(m, "{name}", ns) < 0) return NULL; }}'.format(
                    name=py_name, safe=safe
                )
            )

    if max_phase >= 3:
        print("    py_lv_runtime_init_types();")
        print("    if (PyType_Ready(&py_blob_type) < 0) return NULL;")
        print("    Py_INCREF((PyObject *)&py_blob_type);")
        print('    if (PyModule_AddObject(m, "Blob", (PyObject *)&py_blob_type) < 0) return NULL;')
        print("    if (PyType_Ready(&py_lv_base_struct_type) < 0) return NULL;")
        print("    Py_INCREF((PyObject *)&py_lv_base_struct_type);")
        print('    if (PyModule_AddObject(m, "Struct", (PyObject *)&py_lv_base_struct_type) < 0) return NULL;')
        print("    if (PyType_Ready(&py_C_Pointer_type) < 0) return NULL;")
        print("    Py_INCREF((PyObject *)&py_C_Pointer_type);")
        print('    if (PyModule_AddObject(m, "C_Pointer", (PyObject *)&py_C_Pointer_type) < 0) return NULL;')
        print("    if (PyLvReferenceError) {")
        print("        Py_INCREF(PyLvReferenceError);")
        print('        if (PyModule_AddObject(m, "LvReferenceError", PyLvReferenceError) < 0) return NULL;')
        print("    }")
        if generated_structs:
            for struct_name in generated_structs:
                if not generated_structs[struct_name]:
                    continue
                san = sanitize(struct_name)
                struct_tag = (
                    "struct "
                    if struct_name in runtime.get("structs_without_typedef", {})
                    else ""
                )
                py_name = export_name(struct_name, "struct")
                print(
                    '    if (PyType_Ready(&py_{san}_type) < 0) return NULL;'.format(
                        san=san
                    )
                )
                if struct_name in cpython_struct_sizes:
                    print(
                        '    lv_struct_register_size(&py_{san}_type, sizeof({tag}{name}));'.format(
                            san=san, tag=struct_tag, name=struct_name
                        )
                    )
                    print(
                        '    lv_struct_expose_size(&py_{san}_type);'.format(san=san)
                    )
                print(
                    '    Py_INCREF((PyObject *)&py_{san}_type);'.format(san=san)
                )
                print(
                    '    if (PyModule_AddObject(m, "{name}", (PyObject *)&py_{san}_type) < 0) return NULL;'.format(
                        name=py_name, san=san
                    )
                )
        if struct_aliases:
            for struct_name in struct_aliases:
                san = sanitize(struct_name)
                struct_tag = (
                    "struct "
                    if struct_name in runtime.get("structs_without_typedef", {})
                    else ""
                )
                py_name = export_name(struct_aliases[struct_name], "struct")
                print(
                    '    if (PyType_Ready(&py_{san}_type) < 0) return NULL;'.format(
                        san=san
                    )
                )
                if struct_name in cpython_struct_sizes:
                    print(
                        '    lv_struct_register_size(&py_{san}_type, sizeof({tag}{name}));'.format(
                            san=san, tag=struct_tag, name=struct_name
                        )
                    )
                    print(
                        '    lv_struct_expose_size(&py_{san}_type);'.format(san=san)
                    )
                print(
                    '    Py_INCREF((PyObject *)&py_{san}_type);'.format(san=san)
                )
                print(
                    '    if (PyModule_AddObject(m, "{name}", (PyObject *)&py_{san}_type) < 0) return NULL;'.format(
                        name=py_name, san=san
                    )
                )

    if max_phase >= 5 and obj_names:
        enums = runtime.get("enums", {})
        for obj_name in obj_names:
            san = sanitize(obj_name)
            print(
                '    if (PyType_Ready(&py_lv_{san}_type) < 0) return NULL;'.format(
                    san=san
                )
            )
            obj_enums = [
                enum_name
                for enum_name in enums.keys()
                if is_method_of(enum_name, obj_name)
            ]
            for enum_name in obj_enums:
                enum_safe = sanitize(enum_name)
                attr_name = export_name(method_name_from_func_name(enum_name), "enum")
                print(
                    '    {{ if (PyType_Ready(&py_lv_{enum_safe}_type) < 0) return NULL;'
                    ' PyObject *_enum_ns = (PyObject *)PyType_GenericNew(&py_lv_{enum_safe}_type, NULL, NULL);'
                    ' if (_enum_ns == NULL) return NULL;'
                    ' if (((PyTypeObject *)&py_lv_{san}_type)->tp_dict &&'
                    ' PyDict_SetItemString(((PyTypeObject *)&py_lv_{san}_type)->tp_dict, "{attr_name}", _enum_ns) < 0) {{ Py_DECREF(_enum_ns); return NULL; }}'
                    ' Py_DECREF(_enum_ns); }}'.format(
                        enum_safe=enum_safe,
                        san=san,
                        attr_name=attr_name,
                    )
                )
            print(
                '    Py_INCREF((PyObject *)&py_lv_{san}_type);'.format(san=san)
            )
            print(
                '    if (PyModule_AddObject(m, "{name}", (PyObject *)&py_lv_{san}_type) < 0) return NULL;'.format(
                    name=export_name(obj_name, "object"), san=san
                )
            )

    if max_phase >= 6 and module_funcs:
        generated_funcs = runtime.get("generated_funcs", {})
        for func in module_funcs:
            py_func = _resolved_py_func_name(func.name, generated_funcs)
            if not py_func:
                continue
            fname = sanitize(py_func)
            py_name = export_name(func.name, "function")
            print(
                '    {{ PyObject *fn = PyCFunction_New(&py_{fname}_def, NULL); if (fn == NULL) return NULL; if (PyModule_AddObject(m, "{py_name}", fn) < 0) return NULL; }}'.format(
                    fname=fname, py_name=py_name
                )
            )

    print("    if (lvpy_nesting_obj) {")
    print("        Py_INCREF(lvpy_nesting_obj);")
    print('        if (PyModule_AddObject(m, "_nesting", lvpy_nesting_obj) < 0) return NULL;')
    print("    }")
    print("    return m;")
    print("}")
