"""Target-neutral public API model built from the declaration IR.

This module describes the API independently of any C runtime or binding
backend.  Conversion details and target exceptions are intentionally separate
so the three backends can lower the same model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

from .ir import (
    CEnum,
    CField,
    CFunction,
    CParameter,
    CStruct,
    CTypedef,
    CType,
    CVariable,
    DeclarationIndex,
    DeclarationIR,
    SourceLocation,
)


TARGETS = ("micropython", "circuitpython", "cpython")


def _type_to_dict(type_: CType) -> Mapping[str, Any]:
    result = {"kind": type_.kind}
    if type_.name is not None:
        result["name"] = type_.name
    if type_.qualifiers:
        result["qualifiers"] = list(type_.qualifiers)
    if type_.target is not None:
        result["target"] = _type_to_dict(type_.target)
    if type_.element is not None:
        result["element"] = _type_to_dict(type_.element)
    if type_.dimensions:
        result["dimensions"] = list(type_.dimensions)
    if type_.return_type is not None:
        result["return_type"] = _type_to_dict(type_.return_type)
    if type_.parameters:
        result["parameters"] = [_parameter_to_dict(parameter) for parameter in type_.parameters]
    if type_.variadic:
        result["variadic"] = True
    return result


def _parameter_to_dict(parameter: CParameter) -> Mapping[str, Any]:
    result = {"name": parameter.name, "type": _type_to_dict(parameter.type)}
    if parameter.location.file is not None:
        result["location"] = {
            "file": parameter.location.file,
            "line": parameter.location.line,
            "column": parameter.location.column,
        }
    return result


def _field_to_dict(field_: CField) -> Mapping[str, Any]:
    result = {"name": field_.name, "type": _type_to_dict(field_.type)}
    if field_.bit_width is not None:
        result["bit_width"] = field_.bit_width
    return result


def _location_to_dict(location: SourceLocation) -> Mapping[str, Any]:
    return {
        "file": location.file,
        "line": location.line,
        "column": location.column,
    }


@dataclass(frozen=True)
class ApiFunction:
    c_name: str
    python_name: str
    role: str
    parameters: Tuple[CParameter, ...]
    return_type: CType
    receiver: Optional[str] = None
    static: bool = False
    variadic: bool = False
    storage: Tuple[str, ...] = ()
    function_specifiers: Tuple[str, ...] = ()
    available_on: Tuple[str, ...] = TARGETS
    location: Optional[SourceLocation] = field(default=None)

    def to_dict(self) -> Mapping[str, Any]:
        result = {
            "c_name": self.c_name,
            "python_name": self.python_name,
            "role": self.role,
            "parameters": [_parameter_to_dict(parameter) for parameter in self.parameters],
            "return_type": _type_to_dict(self.return_type),
            "static": self.static,
            "variadic": self.variadic,
            "storage": list(self.storage),
            "function_specifiers": list(self.function_specifiers),
            "available_on": list(self.available_on),
        }
        if self.receiver is not None:
            result["receiver"] = self.receiver
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiStruct:
    c_name: Optional[str]
    python_name: str
    kind: str
    fields: Tuple[CField, ...]
    typedef_names: Tuple[str, ...] = ()
    complete: bool = False
    available_on: Tuple[str, ...] = TARGETS
    methods: Tuple[str, ...] = ()
    location: Optional[SourceLocation] = field(default=None)

    def to_dict(self) -> Mapping[str, Any]:
        result = {
            "c_name": self.c_name,
            "python_name": self.python_name,
            "kind": self.kind,
            "fields": [_field_to_dict(field_) for field_ in self.fields],
            "typedef_names": list(self.typedef_names),
            "complete": self.complete,
            "available_on": list(self.available_on),
            "methods": list(self.methods),
        }
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiEnum:
    c_name: Optional[str]
    python_name: str
    members: Tuple[Tuple[str, Optional[str]], ...]
    typedef_names: Tuple[str, ...] = ()
    complete: bool = False
    available_on: Tuple[str, ...] = TARGETS
    location: Optional[SourceLocation] = field(default=None)

    def to_dict(self) -> Mapping[str, Any]:
        result = {
            "c_name": self.c_name,
            "python_name": self.python_name,
            "members": [
                {"name": name, "value": value} for name, value in self.members
            ],
            "typedef_names": list(self.typedef_names),
            "complete": self.complete,
            "available_on": list(self.available_on),
        }
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiTypedef:
    name: str
    type: CType
    callback: bool = False
    available_on: Tuple[str, ...] = TARGETS
    location: Optional[SourceLocation] = field(default=None)

    def to_dict(self) -> Mapping[str, Any]:
        result = {
            "name": self.name,
            "type": _type_to_dict(self.type),
            "callback": self.callback,
            "available_on": list(self.available_on),
        }
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiVariable:
    c_name: str
    type: CType
    storage: Tuple[str, ...] = ()
    available_on: Tuple[str, ...] = TARGETS
    location: Optional[SourceLocation] = field(default=None)

    def to_dict(self) -> Mapping[str, Any]:
        result = {
            "c_name": self.c_name,
            "type": _type_to_dict(self.type),
            "storage": list(self.storage),
            "available_on": list(self.available_on),
        }
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiObject:
    python_name: str
    constructor: Optional[str]
    methods: Tuple[str, ...]
    available_on: Tuple[str, ...] = TARGETS

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "python_name": self.python_name,
            "constructor": self.constructor,
            "methods": list(self.methods),
            "available_on": list(self.available_on),
        }


@dataclass(frozen=True)
class ApiModel:
    module_prefix: str
    functions: Tuple[ApiFunction, ...]
    objects: Tuple[ApiObject, ...]
    structs: Tuple[ApiStruct, ...]
    enums: Tuple[ApiEnum, ...]
    typedefs: Tuple[ApiTypedef, ...]
    variables: Tuple[ApiVariable, ...]
    schema_version: int = 1

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "module_prefix": self.module_prefix,
            "functions": [
                item.to_dict() for item in sorted(self.functions, key=lambda x: x.c_name)
            ],
            "objects": [
                item.to_dict() for item in sorted(self.objects, key=lambda x: x.python_name)
            ],
            "structs": [
                item.to_dict()
                for item in sorted(
                    self.structs, key=lambda x: (x.python_name, x.c_name or "")
                )
            ],
            "enums": [
                item.to_dict()
                for item in sorted(
                    self.enums, key=lambda x: (x.python_name, x.c_name or "")
                )
            ],
            "typedefs": [
                item.to_dict() for item in sorted(self.typedefs, key=lambda x: x.name)
            ],
            "variables": [
                item.to_dict() for item in sorted(self.variables, key=lambda x: x.c_name)
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


def _strip_prefix(name: str, module_prefix: str) -> str:
    prefix = module_prefix + "_"
    return name[len(prefix) :] if name.startswith(prefix) else name


def _same_struct(index: DeclarationIndex, left: Optional[str], right: Optional[str]) -> bool:
    if left is None or right is None:
        return left == right
    return index._struct_identity(left) == index._struct_identity(right)


def _public_struct_name(struct: CStruct) -> str:
    if struct.typedef_names:
        # The preprocessor can expose both a private implementation alias and
        # its public spelling.  Prefer the stable public spelling and make the
        # choice independent of declaration order.
        return sorted(
            struct.typedef_names,
            key=lambda name: (name.startswith("_"), name),
        )[0]
    if struct.name:
        return struct.name
    return "<anonymous>"


def _method_name(function_name: str, receiver: str, module_prefix: str) -> str:
    plain = _strip_prefix(function_name, module_prefix)
    stems = [receiver]
    if receiver.endswith("_t"):
        stems.append(receiver[:-2])
    for stem in stems:
        if plain.startswith(stem + "_"):
            return plain[len(stem) + 1 :]
    return plain


def build_api_model(
    declarations: DeclarationIR,
    *,
    module_prefix: str = "lv",
    base_obj_type: str = "lv_obj_t",
) -> ApiModel:
    """Build a deterministic API model without target-specific policy."""
    index = DeclarationIndex.from_ir(declarations, module_prefix=module_prefix)

    struct_names = {
        id(struct): _public_struct_name(struct) for struct in declarations.structs
    }
    struct_receivers = {}
    for struct in declarations.structs:
        receiver = struct_names[id(struct)]
        for function in index.struct_functions(receiver):
            struct_receivers.setdefault(function.name, receiver)

    constructors = {}
    for function in declarations.functions:
        plain = _strip_prefix(function.name, module_prefix)
        if not plain.endswith("_create") or not function.parameters:
            continue
        if _same_struct(
            index,
            index.first_argument_type_name(function.name),
            base_obj_type,
        ):
            constructors[plain[: -len("_create")]] = function.name

    functions = []
    object_methods = {name: [] for name in constructors}
    for function in declarations.functions:
        if function.name.startswith("_"):
            continue
        plain = _strip_prefix(function.name, module_prefix)
        role = "module"
        receiver = None
        static = False
        object_name = next(
            (
                object_name
                for object_name in constructors
                if plain.startswith(object_name + "_")
                and _same_struct(
                    index,
                    index.first_argument_type_name(function.name),
                    base_obj_type,
                )
            ),
            None,
        )
        if object_name is not None:
            role = "constructor" if plain == object_name + "_create" else "object_method"
            receiver = object_name
            if role == "object_method":
                object_methods[object_name].append(plain[len(object_name) + 1 :])
        elif function.name in struct_receivers:
            role = "struct_method"
            receiver = struct_receivers[function.name]
        functions.append(
            ApiFunction(
                c_name=function.name,
                python_name=(
                    "create"
                    if role == "constructor"
                    else _method_name(function.name, receiver, module_prefix)
                    if receiver is not None
                    else plain
                ),
                role=role,
                receiver=receiver,
                parameters=function.parameters,
                return_type=function.return_type,
                static=("static" in function.storage),
                variadic=function.variadic,
                storage=function.storage,
                function_specifiers=function.function_specifiers,
                location=function.location,
            )
        )

    objects = tuple(
        ApiObject(
            python_name=name,
            constructor=constructors[name],
            methods=tuple(sorted(object_methods[name])),
        )
        for name in sorted(constructors)
    )

    function_by_name = {function.c_name: function for function in functions}
    structs = tuple(
        ApiStruct(
            c_name=struct.name,
            python_name=struct_names[id(struct)],
            kind=struct.kind,
            fields=struct.fields,
            typedef_names=struct.typedef_names,
            complete=struct.complete,
            methods=tuple(
                sorted(
                    function_by_name[function.name].python_name
                    for function in index.struct_functions(struct_names[id(struct)])
                    if function.name in function_by_name
                )
            ),
            location=struct.location,
        )
        for struct in sorted(
            declarations.structs,
            key=lambda item: (_public_struct_name(item), item.name or ""),
        )
    )
    enums = tuple(
        ApiEnum(
            c_name=enum.name,
            python_name=enum.typedef_names[0] if enum.typedef_names else enum.name or "<anonymous>",
            members=enum.values
            or tuple((member, None) for member in enum.members),
            typedef_names=enum.typedef_names,
            complete=enum.complete,
            location=enum.location,
        )
        for enum in sorted(
            declarations.enums,
            key=lambda item: (
                item.typedef_names[0]
                if item.typedef_names
                else item.name or "<anonymous>",
                item.name or "",
            ),
        )
    )
    typedefs = tuple(
        ApiTypedef(
            name=typedef.name,
            type=typedef.type,
            callback=typedef.name in declarations.callback_typedefs,
            location=typedef.location,
        )
        for typedef in declarations.typedefs
    )
    variables = tuple(
        ApiVariable(
            c_name=variable.name,
            type=variable.type,
            storage=variable.storage,
            location=variable.location,
        )
        for variable in declarations.variables
        if not variable.name.startswith("_")
    )
    return ApiModel(
        module_prefix=module_prefix,
        functions=tuple(functions),
        objects=objects,
        structs=structs,
        enums=enums,
        typedefs=typedefs,
        variables=variables,
    )


def write_api_model(model: ApiModel, path: Any) -> None:
    """Write deterministic JSON for review, hashing, and downstream checks."""
    with open(path, "w", encoding="utf-8") as output:
        output.write(model.to_json())
