"""Symbols omitted from generated C per target; IR/.pyi may still list them."""

from __future__ import print_function

# C function names (parser names, not simplified Python names)
RUNTIME_SKIP_MODULE_FUNCS = {
    "circuitpython": frozenset(
        {
            "lv_tjpgd_init",
            "lv_tjpgd_deinit",
        }
    ),
    "cpython": frozenset(
        {
            "lv_tjpgd_init",
            "lv_tjpgd_deinit",
            "mp_lv_init_gc",
            "mp_lv_deinit_gc",
        }
    ),
}


def skip_module_func(func_name, target):
    return func_name in RUNTIME_SKIP_MODULE_FUNCS.get(target, frozenset())


def filter_module_funcs_for_target(module_funcs, target):
    if target not in RUNTIME_SKIP_MODULE_FUNCS:
        return module_funcs
    return [func for func in module_funcs if not skip_module_func(func.name, target)]
