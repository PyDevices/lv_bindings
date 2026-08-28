"""Main CPython emit loop (PyObject* API); calls cpython_glue and cpython_native."""
from __future__ import print_function

import collections
import copy
import re
from os.path import commonprefix

from pycparser import c_ast, c_generator, c_parser

from .analyze import (
    MissingConversionException,
    get_base_struct_name,
    get_ctor,
    get_enum_member_name,
    get_enum_members,
    get_enum_value,
    get_first_arg_type,
    get_methods,
    get_struct_functions,
    has_ctor,
    is_static_member,
    is_struct_function,
    noncommon_part,
)
from .helpers import (
    collect_enum_referenced,
    ctor_name_from_obj_name,
    get_enum_name,
    is_global_callback,
    is_method_of,
    is_obj_ctor,
    is_struct,
    is_widget_scoped_only_enum,
    method_name_from_func_name,
    obj_name_from_ext_name,
    obj_name_from_func_name,
    sanitize,
    simplify_identifier,
    str_enum_to_str,
)
from .parse import (
    add_default_declname,
    convert_array_to_ptr,
    function_prototype,
    get_name,
    get_type,
    remove_arg_names,
    remove_declname,
    remove_explicit_struct,
    remove_quals,
)
from . import runtime
from .emit_backend import (
    callback_return_conversion_available,
    callback_return_lowering,
    function_return_lowering,
    require_target_lowering,
    resolve_emitter_headers,
    struct_pointer_helpers_source,
    target_banner,
)
from .runtime_exports import filter_module_funcs_for_target
from .util import eprint, memoize


def emit_c():
    global headers, generated_structs, generated_struct_functions, struct_aliases
    global callbacks_used_on_structs, generated_callbacks, generated_funcs
    global enum_referenced, generated_obj_names, generated_globals
    global module_funcs, functions_not_generated, enums

    headers = resolve_emitter_headers(args.input)

    _emit_target = "cpython"
    _emit_max_phase = require_target_lowering(_emit_target)
    _target_banner = target_banner(_emit_target, include=True)

    print(
        """
/*
 * Auto-Generated file, DO NOT EDIT!
 *
{target_banner} * Command line:
 * {cmd_line}
 *
 * Preprocessing command:
 * {pp_cmd}
 *
 * Generating Objects: {objs}
 */

/*
 * CPython includes
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdlib.h>
#include <string.h>
#include "lvpy_runtime.h"

/*
 * {module_name} includes
 */

{lv_headers}
""".format(
        module_name=module_name,
        target_banner=_target_banner,
        cmd_line=cmd_line,
            pp_cmd=pp_cmd,
            objs=", ".join(
                ["%s(%s)" % (objname, parent_obj_names[objname]) for objname in obj_names]
            ),
            lv_headers="\n".join('#include "%s"' % header for header in headers),
        )
    )

    #
    # Enable objects, if supported
    #

    if len(obj_names) > 0 and (_emit_max_phase is None or _emit_max_phase >= 5):
        print(
            """
#define LV_OBJ_T lv_obj_t
"""
        )

    # Helper functions live in lvpy_runtime.c.

    #
    # Add regular enums with integer values
    #

    enums = collections.OrderedDict()
    for enum_def in enum_defs:
        # Skip stdatomic.h memory_order, no bindings needed.
        if isinstance(enum_def, c_ast.TypeDecl) and enum_def.declname == "memory_order":
            continue

        # eprint("--> %s" % enum_def)
        while hasattr(enum_def.type, "name") and not enum_def.type.values:
            enum_def = next(
                e
                for e in enum_defs
                if hasattr(e.type, "name")
                and e.type.name == enum_def.type.name
                and e.type.values
            )
        member_names = [
            member.name
            for member in enum_def.type.values.enumerators
            if not member.name.startswith("_")
        ]
        enum_name = commonprefix(member_names)
        enum_name = "_".join(enum_name.split("_")[:-1])  # remove suffix
        enum = collections.OrderedDict()
        for member in enum_def.type.values.enumerators:
            if member.name.startswith("_"):
                continue
            member_name = (
                member.name[len(enum_name) + 1 :] if len(enum_name) > 0 else member.name
            )
            if member_name[0].isdigit():
                member_name = "_" + member_name
            if len(enum_name) > 0 and get_enum_name(enum_name) != "ENUM":
                enum[member_name] = "MP_ROM_INT(%s)" % member.name
            else:
                int_constants.append(member.name)
        if len(enum) > 0:
            if len(get_enum_name(enum_name)) > 0:
                prev_enum = enums.get(enum_name)
                if prev_enum:
                    prev_enum.update(enum)
                else:
                    enums[enum_name] = enum

    for enum in [
        enum for enum in enums if len(enums[enum]) == 1 and enum.startswith("ENUM")
    ]:
        int_constants.append("%s_%s" % (enum, next(iter(enums[enum]))))
        del enums[enum]

    # Add special string enums

    generated_globals = []

    print(
        """
/*
 * LVGL string constants
 */
"""
    )

    for enum_def in enum_defs:
        if not enum_def.type.values:
            continue
        member_names = [
            str_enum_to_str(member.name)
            for member in enum_def.type.values.enumerators
            if lv_str_enum_pattern.match(member.name)
        ]
        enum_name = commonprefix(member_names)
        enum_name = "_".join(enum_name.split("_")[:-1])  # remove suffix
        enum = collections.OrderedDict()
        if enum_name:
            for member in enum_def.type.values.enumerators:
                full_name = str_enum_to_str(member.name)
                member_name = full_name[len(enum_name) + 1 :]
                generated_globals.append(full_name)
                enum[member_name] = full_name
            if len(enum) > 0:
                if enum_name in enums:
                    enums[enum_name].update(enum)
                else:
                    enums[enum_name] = enum


    # eprint('--> enums: \n%s' % enums)

    runtime.set_("enums", enums)

    # eprint(',\n'.join(sorted('%s : %s' % (name, get_type(blobs[name])) for name in blobs)))

    #
    # Callbacks helper functions
    #


    def decl_to_callback(decl):
        # print('/* decl_to_callback %s */' % decl)
        if not hasattr(decl, "type"):
            return None
        if isinstance(decl.type, c_ast.PtrDecl) and isinstance(
            decl.type.type, c_ast.FuncDecl
        ):
            return (decl.name, decl.type.type)
            # print('/* callback: ADDED CALLBACK: %s\n%s */' % (gen.visit(decl.type.type), decl.type.type))
        elif isinstance(decl.type, c_ast.FuncDecl):
            return (decl.name, decl.type)
            # print('/* callback: ADDED CALLBACK: %s\n%s */' % (gen.visit(decl.type.type), decl.type.type))
        elif isinstance(decl.type, c_ast.TypeDecl) and hasattr(decl.type.type, "names"):
            func_typedef_name = decl.type.type.names[0]
            while func_typedef_name in synonym:
                # eprint('decl_to_callback: %s --> %s' % (func_typedef_name, synonym[func_typedef_name]))
                func_typedef_name = synonym[func_typedef_name]
            # print('/* --> callback: TYPEDEF CALLBACK: %s: %s */' % (decl.name if hasattr(decl, 'name') else None, func_typedef_name))
            if func_typedef_name in func_typedefs:
                return (decl.name, func_typedefs[func_typedef_name].type.type)
                # print('/* callback: ADDED CALLBACK: %s\n%s */' % (func_typedef_name, func_typedefs[func_typedef_name]))
        else:
            return None


    def get_user_data_accessors(containing_struct, containing_struct_name=None):
        if not containing_struct_name and containing_struct and containing_struct.name:
            containing_struct_name = containing_struct.name
        if not containing_struct_name:
            return None, None
        base_struct_name = get_base_struct_name(containing_struct_name)
        getter_name = base_struct_name + "_get_user_data"
        setter_name = base_struct_name + "_set_user_data"
        # print('/* struct functions = %s */' % [s.name + ':' + str(len(s.type.args.params)) for s in get_struct_functions(containing_struct_name)])
        # print('/* getter_name = %s */' % getter_name)
        struct_functions = get_struct_functions(containing_struct_name)
        getters = [
            s
            for s in struct_functions
            if s.name == getter_name and len(s.type.args.params) == 1
        ]
        setters = [
            s
            for s in struct_functions
            if s.name == setter_name and len(s.type.args.params) == 2
        ]
        if getters and setters:
            return getters[0], setters[0]
        else:
            return None, None


    def get_user_data(
        func, func_name=None, containing_struct=None, containing_struct_name=None
    ):
        args = func.args.params
        if not func_name:
            func_name = get_arg_name(func.type)
        # print('/* --> callback: func_name = %s, args = %s */' % (func_name, repr(args)))
        user_data_found = False
        user_data = "None"
        if len(args) > 0 and isinstance(args[0].type, c_ast.PtrDecl):
            # if isinstance(args[0].type.type.type, c_ast.Struct):
            #     struct_arg_type_name = args[0].type.type.type.name # PtrDecl.TypeDecl.Struct. Needed to omit 'struct' keyword.
            # else:
            #     struct_arg_type_name = get_type(args[0].type.type, remove_quals = True)
            struct_arg_type_name = get_type(args[0].type.type, remove_quals=True)
            # print('/* --> get_user_data: containing_struct_name = %s, struct_arg_type_name = %s */' % (containing_struct_name, struct_arg_type_name))
            if containing_struct_name and struct_arg_type_name != containing_struct_name:
                return None, None, None
            if not containing_struct:
                try_generate_type(args[0].type)
                if struct_arg_type_name in structs:
                    containing_struct = structs[struct_arg_type_name]
                    # print('/* --> containing_struct = %s */' % containing_struct)
                # if struct_arg_type_name in mp_to_lv:
                #     print('/* --> callback: %s First argument is %s */' % (gen.visit(func), struct_arg_type_name))
            if containing_struct:
                flatten_struct_decls = flatten_struct(containing_struct.decls)
                user_data = "user_data"
                user_data_found = user_data in [decl.name for decl in flatten_struct_decls]
                # print('/* --> callback: user_data=%s user_data_found=%s containing_struct=%s */' % (user_data, user_data_found, containing_struct))
                if not user_data_found and lvgl_json is not None:
                    containing_struct_j = next(
                        (
                            struct
                            for struct in lvgl_json["structures"]
                            if struct["name"] == struct_arg_type_name
                        ),
                        None,
                    )
                    if (
                        containing_struct_j is None
                        and struct_arg_type_name.startswith("lv_")
                        and None
                        is not next(
                            (
                                fwd_decl
                                for fwd_decl in lvgl_json["forward_decls"]
                                if fwd_decl["name"] == struct_arg_type_name
                            ),
                            None,
                        )
                    ):
                        struct_arg_type_name_with_underscore = "_" + struct_arg_type_name
                        containing_struct_j = next(
                            (
                                struct
                                for struct in lvgl_json["structures"]
                                if struct["name"] == struct_arg_type_name_with_underscore
                            ),
                            None,
                        )
                    if containing_struct_j is not None:
                        user_data_found = any(
                            user_data == field["name"]
                            for field in containing_struct_j["fields"]
                        )
        return (user_data if user_data_found else None), *get_user_data_accessors(
            containing_struct, containing_struct_name
        )


    #
    # Generate structs when needed
    #

    generated_structs = collections.OrderedDict()
    generated_struct_functions = collections.OrderedDict()
    generated_struct_method_funcs = collections.OrderedDict()
    struct_aliases = collections.OrderedDict()
    callbacks_used_on_structs = []
    runtime.set_("generated_structs", generated_structs)
    runtime.set_("generated_struct_functions", generated_struct_functions)
    runtime.set_("generated_struct_method_funcs", generated_struct_method_funcs)
    runtime.set_("struct_aliases", struct_aliases)
    runtime.set_("callbacks_used_on_structs", callbacks_used_on_structs)


    def flatten_struct(struct_decls):
        result = []
        if not struct_decls:
            return result
        for decl in struct_decls:
            if is_struct(decl.type):
                result.extend(flatten_struct(decl.type.decls))
            else:
                result.append(decl)
        return result


    def try_generate_struct(struct_name, struct):
        from .emit_cpython_native import try_generate_struct_cpython

        return try_generate_struct_cpython(struct_name, struct)


    def try_generate_array_type(type_ast):
        return None


    generated_funcptr_helpers = collections.OrderedDict()


    def get_arg_name(arg):
        if isinstance(arg, (c_ast.PtrDecl, c_ast.FuncDecl)):
            return get_arg_name(arg.type)
        if hasattr(arg, "declname"):
            return arg.declname
        if hasattr(arg, "name"):
            return arg.name
        return "unnamed_arg"


    def try_generate_type(type_ast):
        if isinstance(type_ast, str):
            raise SyntaxError("Internal error! try_generate_type argument is a string.")
        if isinstance(type_ast, c_ast.TypeDecl):
            return try_generate_type(type_ast.type)

        type_name = get_name(type_ast)
        if isinstance(type_ast, c_ast.Enum):
            mp_to_lv[type_name] = mp_to_lv["int"]
            mp_to_lv["%s *" % type_name] = mp_to_lv["int *"]
            lv_to_mp[type_name] = lv_to_mp["int"]
            lv_to_mp["%s *" % type_name] = lv_to_mp["int *"]
            lv_mp_type[type_name] = lv_mp_type["int"]
            lv_mp_type["%s *" % type_name] = lv_mp_type["int *"]
            return mp_to_lv[type_name]
        if type_name in mp_to_lv:
            return mp_to_lv[type_name]
        if isinstance(type_ast, c_ast.ArrayDecl) and try_generate_array_type(type_ast):
            return mp_to_lv[type_name]

        if isinstance(type_ast, (c_ast.PtrDecl, c_ast.ArrayDecl)):
            type_name = get_name(type_ast.type.type)
            ptr_type = get_type(type_ast, remove_quals=True)
            if type_name in structs:
                try_generate_struct(type_name, structs[type_name])
            if (
                isinstance(type_ast.type, c_ast.TypeDecl)
                and isinstance(type_ast.type.type, c_ast.Struct)
                and type_ast.type.type.name in structs
            ):
                try_generate_struct(type_name, structs[type_ast.type.type.name])
            if isinstance(type_ast.type, c_ast.FuncDecl):
                if isinstance(type_ast.type.type.type, c_ast.TypeDecl):
                    type_name = type_ast.type.type.type.declname
                if ptr_type in lv_to_mp_funcptr:
                    existing = lv_to_mp_funcptr[ptr_type]
                    lv_to_mp.setdefault(ptr_type, "mp_lv_%s" % existing)
                    mp_to_lv.setdefault(ptr_type, mp_to_lv["void *"])
                    lv_mp_type.setdefault(ptr_type, "function pointer")
                    return mp_to_lv[ptr_type]

                func_ptr_name = "funcptr_%s" % type_name
                suffix = 1
                while func_ptr_name in generated_funcptr_helpers:
                    func_ptr_name = "funcptr_%s_%d" % (type_name, suffix)
                    suffix += 1
                generated_funcptr_helpers[func_ptr_name] = True
                func = c_ast.Decl(
                    name=func_ptr_name,
                    quals=[],
                    align=[],
                    storage=[],
                    funcspec=[],
                    type=type_ast.type,
                    init=None,
                    bitsize=None,
                )
                try:
                    print("#define %s NULL\n" % func_ptr_name)
                    print(
                        "static inline PyObject *mp_lv_{f}(void *func){{ return "
                        "mp_lv_funcptr(NULL, func, NULL, \"\", NULL); }}\n".format(
                            f=func_ptr_name
                        )
                    )
                    lv_to_mp_funcptr[ptr_type] = func_ptr_name
                    lv_to_mp[ptr_type] = "mp_lv_%s" % func_ptr_name
                    lv_mp_type[ptr_type] = "function pointer"
                except MissingConversionException as exp:
                    gen_func_error(func, exp)
            mp_to_lv.setdefault(ptr_type, mp_to_lv["void *"])
            lv_to_mp.setdefault(ptr_type, lv_to_mp["void *"])
            lv_mp_type.setdefault(ptr_type, "void*")
            return mp_to_lv[ptr_type]

        if type_name in structs and try_generate_struct(type_name, structs[type_name]):
            return mp_to_lv[type_name]
        for new_type_ast in [x for x in typedefs if get_arg_name(x) == type_name]:
            new_type = get_type(new_type_ast, remove_quals=True)
            if (
                isinstance(new_type_ast, c_ast.TypeDecl)
                and isinstance(new_type_ast.type, c_ast.Struct)
                and not new_type_ast.type.decls
            ):
                explicit_struct_name = (
                    new_type_ast.type.name
                    if hasattr(new_type_ast.type, "name")
                    else new_type_ast.type.names[0]
                )
            else:
                explicit_struct_name = new_type
            if type_name == explicit_struct_name:
                continue
            if explicit_struct_name in structs:
                if try_generate_struct(new_type, structs[explicit_struct_name]):
                    if explicit_struct_name == new_type:
                        struct_aliases[new_type] = type_name
            if type_name != new_type and try_generate_type(new_type_ast):
                mp_to_lv[type_name] = mp_to_lv[new_type]
                type_ptr = "%s *" % type_name
                new_type_ptr = "%s *" % new_type
                if new_type_ptr in mp_to_lv:
                    mp_to_lv[type_ptr] = mp_to_lv[new_type_ptr]
                if new_type in lv_to_mp:
                    lv_to_mp[type_name] = lv_to_mp[new_type]
                    lv_mp_type[type_name] = lv_mp_type[new_type]
                    if new_type in lv_to_mp_funcptr:
                        lv_to_mp_funcptr[type_name] = lv_to_mp_funcptr[new_type]
                    if new_type in lv_to_mp_byref:
                        lv_to_mp_byref[type_name] = lv_to_mp_byref[new_type]
                    if new_type_ptr in lv_to_mp:
                        lv_to_mp[type_ptr] = lv_to_mp[new_type_ptr]
                    if new_type_ptr in lv_mp_type:
                        lv_mp_type[type_ptr] = lv_mp_type[new_type_ptr]
                return mp_to_lv[type_name]
        return None


    #
    # Emit C callback functions
    #

    generated_callbacks = collections.OrderedDict()
    generated_funcs = collections.OrderedDict()

    if _emit_max_phase is None or _emit_max_phase > 1:

        if _emit_max_phase is not None and _emit_max_phase >= 2:
            from .emit_cpython_glue import emit_phase2_enums_cpython

            emit_phase2_enums_cpython()

        if _emit_max_phase is None or _emit_max_phase >= 4:

            def gen_callback_func(func, func_name=None, user_data_argument=False):
                from .emit_cpython_native import gen_callback_func_cpython

                return gen_callback_func_cpython(func, func_name, user_data_argument)


            generated_funcs = collections.OrderedDict()


            def gen_mp_func(func, obj_name):
                from .emit_cpython_native import gen_py_func

                return gen_py_func(func, obj_name)


            def gen_func_error(method, exp):
                funcs = list(runtime.get("funcs"))
                print(
                    """
/*
 * Function NOT generated:
 * {problem}
 * {method}
 */
    """.format(
                        method=gen.visit(method) if isinstance(method, c_ast.Node) else method,
                        problem=exp,
                    )
                )
                try:
                    funcs.remove(method)
                except:
                    pass
                runtime.set_("funcs", funcs)


        #
        # Emit Mpy objects definitions
        #

        enum_referenced = collections.OrderedDict()


        def gen_obj(obj_name):
            from .emit_cpython_native import gen_py_obj

            return gen_py_obj(obj_name)


        #
        # Generate Enum objects
        #

        if _emit_max_phase is None:
            for enum_name in list(enums.keys()):
                gen_obj(enum_name)

        #
        # Generate all other objects. Generate parent objects first
        #

        if _emit_max_phase is None or _emit_max_phase >= 5:

            from .emit_cpython_native import bind_emit_helpers

            bind_emit_helpers(locals())

            generated_obj_names = collections.OrderedDict()
            for obj_name in obj_names:
                # eprint("--> %s [%s]" % (obj_name, ", ".join([name for name in generated_obj_names])))
                parent_obj_name = (
                    parent_obj_names[obj_name] if obj_name in parent_obj_names else None
                )

                while parent_obj_name != None and parent_obj_name not in generated_obj_names:
                    gen_obj(parent_obj_name)
                    generated_obj_names[parent_obj_name] = True
                    parent_obj_name = (
                        parent_obj_names[parent_obj_name]
                        if parent_obj_name in parent_obj_names
                        else None
                    )

                if obj_name not in generated_obj_names:
                    # eprint("--> gen obj %s" % obj_name)
                    gen_obj(obj_name)
                    generated_obj_names[obj_name] = True

            from .emit_cpython_native import bound_helper

            _gf = bound_helper("generated_funcs")
            if _gf is not None:
                generated_funcs = _gf
            runtime.set_("generated_funcs", generated_funcs)

    #
    # Generate structs which contain function members
    # First argument of a function could be it's parent struct
    # Need to make sure these structs are generated *before* struct-functions are
    # Otherwise we will not know of all the structs when generating struct-functions
    #


    def try_generate_structs_from_first_argument():
        for func in funcs:
            if func.name in generated_funcs:
                continue
            args = func.type.args.params if func.type.args else []
            if len(args) < 1:
                continue
            arg_type = get_type(args[0].type, remove_quals=True)
            if arg_type not in mp_to_lv or not mp_to_lv[arg_type]:
                try:
                    try_generate_type(args[0].type)
                except MissingConversionException as e:
                    print(
                        """
/*
 * {struct} not generated: {err}
 */
                """.format(struct=arg_type, err=e)
                    )


    #
    # Generate globals
    #

    # eprint("/* Generating globals */")


    def gen_func_error(method, exp):
        funcs = list(runtime.get("funcs"))
        print(
            """
/*
 * Function NOT generated:
 * {problem}
 * {method}
 */
    """.format(
                method=gen.visit(method) if isinstance(method, c_ast.Node) else method,
                problem=exp,
            )
        )
        try:
            funcs.remove(method)
        except:
            pass
        runtime.set_("funcs", funcs)

    def _emit_cpython_struct_methods(struct_list=None):
        from .emit_cpython_native import (
            emit_struct_methods_cpython,
            gen_py_func,
            _resolved_struct_method_py_func_name,
        )

        if struct_list is None:
            struct_names = list(generated_structs.keys())
        else:
            struct_names = struct_list
        for struct_name in struct_names:
            if not generated_structs.get(struct_name):
                continue
            if generated_struct_functions.get(struct_name):
                continue
            struct_funcs = list(get_struct_functions(struct_name))
            method_entries = []
            seen_method_names = set()
            for struct_func in struct_funcs:
                try:
                    emit_name = struct_func.name + "_struct_method"
                    if generated_struct_method_funcs.get(emit_name) is not True:
                        gen_py_func(struct_func, struct_name)
                    resolved = _resolved_struct_method_py_func_name(
                        struct_func.name, generated_struct_method_funcs
                    )
                    if not resolved:
                        continue
                    method_name = sanitize(
                        noncommon_part(struct_func.name, struct_name)
                    )
                    if method_name in seen_method_names:
                        continue
                    seen_method_names.add(method_name)
                    method_entries.append((resolved, method_name))
                except MissingConversionException as exp:
                    gen_func_error(struct_func, exp)
            emit_struct_methods_cpython(struct_name, method_entries)
            generated_struct_functions[struct_name] = True


    def _emit_struct_locals_dicts(include_methods=False, struct_list=None):
        return None


    def gen_global(global_name, global_type_ast):
        global_type = get_type(global_type_ast, remove_quals=True)
        if global_name == "_nesting":
            return
        try_generate_type(global_type_ast)
        cpython_global_types = runtime.get(
            "cpython_global_types", collections.OrderedDict()
        )
        cpython_global_types[global_name] = (
            global_type if generated_structs.get(global_type, False) else None
        )
        runtime.set_("cpython_global_types", cpython_global_types)
        generated_globals.append(global_name)


    for global_name in blobs:
        try:
            gen_global(global_name, blobs[global_name])
        except MissingConversionException as exp:
            gen_func_error(global_name, exp)

    if _emit_max_phase is None or _emit_max_phase >= 4:
        from .emit_cpython_native import bind_emit_helpers, bound_helper

        _gf = bound_helper("generated_funcs")
        if _gf is not None:
            generated_funcs = _gf
        bind_emit_helpers(locals())
        try_generate_structs_from_first_argument()
        _emit_struct_locals_dicts(include_methods=True)

    if _emit_max_phase is None or _emit_max_phase >= 6:
        #
        # Generate all module functions (not including method functions which were already generated)
        #

        print(
            """
/*
 *
 * Global Module Functions
 *
 */
"""
        )

        # eprint("/* Generating global module functions /*")
        from .emit_cpython_native import bound_helper

        _candidates = [
            generated_funcs,
            runtime.get("generated_funcs", {}),
            bound_helper("generated_funcs", {}),
        ]
        generated_funcs = max(_candidates, key=len)
        module_funcs = [func for func in funcs if func.name not in generated_funcs]
        module_funcs = filter_module_funcs_for_target(module_funcs, _emit_target)
        runtime.set_("_cpython_module_exports", list(module_funcs))
        for module_func in module_funcs[
            :
        ]:  # clone list because we are changing it in the loop.
            if module_func.name in generated_funcs:
                continue  # generated_funcs could change inside the loop so need to recheck.
            try:
                gen_mp_func(module_func, None)
                # A new function can create new struct with new function structs
                new_structs = [
                    s
                    for s in generated_structs
                    if generated_structs[s] and not generated_struct_functions.get(s)
                ]
                if new_structs:
                    _emit_struct_locals_dicts(include_methods=True, struct_list=new_structs)
            except MissingConversionException as exp:
                gen_func_error(module_func, exp)
                module_funcs.remove(module_func)

        _emit_cpython_struct_methods()

        functions_not_generated = [
            func.name for func in funcs if func.name not in generated_funcs
        ]
        if len(functions_not_generated) > 0:
            print(
                """
/*
 * Functions not generated:
 * {funcs}
 *
 */

""".format(funcs="\n * ".join(functions_not_generated))
            )

    if _emit_max_phase is None or _emit_max_phase >= 7:
        #
        # Generate callback functions (struct field callbacks)
        #

        # eprint("/* Generating callback functions */")
        for func_name, func, struct_name in callbacks_used_on_structs:
            try:
                # print('/* --> gen_callback_func %s */' % func_name)
                gen_callback_func(func, func_name="%s_%s" % (struct_name, func_name))
            except MissingConversionException as exp:
                gen_func_error(func, exp)

    # Emit the CPython module definition.
        from .emit_cpython_glue import finish_py_module
        runtime.set_("generated_funcs", generated_funcs)
        runtime.set_("module_funcs", module_funcs)
        runtime.set_("generated_structs", generated_structs)
        runtime.set_("struct_aliases", struct_aliases)
        runtime.set_("generated_globals", generated_globals)
        runtime.set_("int_constants", int_constants)
        runtime.set_("obj_names", obj_names)
        runtime.set_(
            "enum_referenced",
            collect_enum_referenced(runtime.get("enums", {}), obj_names),
        )
        print(
            """
py_lv_obj_type_t *py_lv_obj_types[] = {{
    {obj_types}NULL
}};
""".format(
                obj_types=",\n    ".join(
                    ["&py_lv_%s_mapping" % sanitize(o) for o in obj_names]
                )
                + (",\n    " if obj_names and (_emit_max_phase is None or _emit_max_phase >= 5) else "")
                if len(obj_names) > 0 and (_emit_max_phase is None or _emit_max_phase >= 5)
                else "",
            )
        )
        finish_py_module(_emit_max_phase or 7)
