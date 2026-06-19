"""Runtime-specific type conversion tables for LVGL binding generation."""

from __future__ import print_function


def build_conversion_tables(module_prefix, base_obj_type, target="micropython"):
    if target == "cpython":
        return _build_cpython_tables(module_prefix, base_obj_type)
    return _build_micropython_tables(module_prefix, base_obj_type)


def _build_micropython_tables(module_prefix, base_obj_type):
    to_lv = {
        "mp_obj_t": "(mp_obj_t)",
        "va_list": None,
        "void *": "mp_to_ptr",
        "const uint8_t *": "mp_to_ptr",
        "const void *": "mp_to_ptr",
        "bool": "mp_obj_is_true",
        "char *": "(char*)convert_from_str",
        "char **": "mp_write_ptr_C_Pointer",
        "const char *": "convert_from_str",
        "const char **": "mp_write_ptr_C_Pointer",
        "%s_obj_t *" % module_prefix: "mp_to_lv",
        "uint8_t": "(uint8_t)mp_obj_get_int",
        "uint16_t": "(uint16_t)mp_obj_get_int",
        "uint32_t": "(uint32_t)mp_obj_get_int",
        "uint64_t": "(uint64_t)mp_obj_get_ull",
        "unsigned": "(unsigned)mp_obj_get_int",
        "unsigned int": "(unsigned int)mp_obj_get_int",
        "unsigned char": "(unsigned char)mp_obj_get_int",
        "unsigned short": "(unsigned short)mp_obj_get_int",
        "unsigned long": "(unsigned long)mp_obj_get_int",
        "unsigned long int": "(unsigned long int)mp_obj_get_int",
        "unsigned long long": "(unsigned long long)mp_obj_get_ull",
        "unsigned long long int": "(unsigned long long int)mp_obj_get_ull",
        "int8_t": "(int8_t)mp_obj_get_int",
        "int16_t": "(int16_t)mp_obj_get_int",
        "int32_t": "(int32_t)mp_obj_get_int",
        "int64_t": "(int64_t)mp_obj_get_ull",
        "size_t": "(size_t)mp_obj_get_int",
        "int": "(int)mp_obj_get_int",
        "char": "(char)mp_obj_get_int",
        "short": "(short)mp_obj_get_int",
        "long": "(long)mp_obj_get_int",
        "long int": "(long int)mp_obj_get_int",
        "long long": "(long long)mp_obj_get_ull",
        "long long int": "(long long int)mp_obj_get_ull",
        "float": "(float)mp_obj_get_float",
    }
    from_lv = {
        "mp_obj_t": "(mp_obj_t)",
        "va_list": None,
        "void *": "ptr_to_mp",
        "const uint8_t *": "ptr_to_mp",
        "const void *": "ptr_to_mp",
        "bool": "convert_to_bool",
        "char *": "convert_to_str",
        "char **": "mp_read_ptr_C_Pointer",
        "const char *": "convert_to_str",
        "const char **": "mp_read_ptr_C_Pointer",
        "%s_obj_t *" % module_prefix: "lv_to_mp",
        "uint8_t": "mp_obj_new_int_from_uint",
        "uint16_t": "mp_obj_new_int_from_uint",
        "uint32_t": "mp_obj_new_int_from_uint",
        "uint64_t": "mp_obj_new_int_from_ull",
        "unsigned": "mp_obj_new_int_from_uint",
        "unsigned int": "mp_obj_new_int_from_uint",
        "unsigned char": "mp_obj_new_int_from_uint",
        "unsigned short": "mp_obj_new_int_from_uint",
        "unsigned long": "mp_obj_new_int_from_uint",
        "unsigned long int": "mp_obj_new_int_from_uint",
        "unsigned long long": "mp_obj_new_int_from_ull",
        "unsigned long long int": "mp_obj_new_int_from_ull",
        "int8_t": "mp_obj_new_int",
        "int16_t": "mp_obj_new_int",
        "int32_t": "mp_obj_new_int",
        "int64_t": "mp_obj_new_int_from_ll",
        "size_t": "mp_obj_new_int_from_uint",
        "int": "mp_obj_new_int",
        "char": "mp_obj_new_int",
        "short": "mp_obj_new_int",
        "long": "mp_obj_new_int",
        "long int": "mp_obj_new_int",
        "long long": "mp_obj_new_int_from_ll",
        "long long int": "mp_obj_new_int_from_ll",
        "float": "mp_obj_new_float_from_f",
    }
    py_type = _build_type_table(module_prefix, base_obj_type)
    return to_lv, from_lv, py_type


def _build_cpython_tables(module_prefix, base_obj_type):
    # Generated lvpy.c uses the same convertor names as MicroPython; lvpy_runtime implements them.
    return _build_micropython_tables(module_prefix, base_obj_type)


def _build_type_table(module_prefix, base_obj_type):
    return {
        "mp_obj_t": "%s*" % base_obj_type,
        "va_list": None,
        "void *": "void*",
        "const uint8_t *": "void*",
        "const void *": "void*",
        "bool": "bool",
        "char *": "char*",
        "char **": "char**",
        "const char *": "char*",
        "const char **": "char**",
        "%s_obj_t *" % module_prefix: "%s*" % base_obj_type,
        "uint8_t": "int",
        "uint16_t": "int",
        "uint32_t": "int",
        "uint64_t": "int",
        "unsigned": "int",
        "unsigned int": "int",
        "unsigned char": "int",
        "unsigned short": "int",
        "unsigned long": "int",
        "unsigned long int": "int",
        "unsigned long long": "int",
        "unsigned long long int": "int",
        "int8_t": "int",
        "int16_t": "int",
        "int32_t": "int",
        "int64_t": "int",
        "size_t": "int",
        "int": "int",
        "char": "int",
        "short": "int",
        "long": "int",
        "long int": "int",
        "long long": "int",
        "long long int": "int",
        "void": None,
        "float": "float",
    }
