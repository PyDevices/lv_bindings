"""Target-neutral public API model built from the declaration IR.

This module describes the API independently of any C runtime or binding
backend.  Conversion details and target exceptions are intentionally separate
so the three backends can lower the same model.
"""

from __future__ import annotations

import json
import hashlib
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


def api_hash_for_dict(data: Mapping[str, Any]) -> str:
    """Hash API content without trusting or including its stored hash field."""

    content = dict(data)
    content.pop("api_hash", None)
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    visibility: str = "public"
    policy_reason: Optional[str] = None
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
            "visibility": self.visibility,
        }
        if self.policy_reason is not None:
            result["policy_reason"] = self.policy_reason
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
    visibility: str = "public"
    policy_reason: Optional[str] = None
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
            "visibility": self.visibility,
        }
        if self.policy_reason is not None:
            result["policy_reason"] = self.policy_reason
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
    visibility: str = "public"
    policy_reason: Optional[str] = None
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
            "visibility": self.visibility,
        }
        if self.policy_reason is not None:
            result["policy_reason"] = self.policy_reason
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiTypedef:
    name: str
    type: CType
    c_name: Optional[str] = None
    callback: bool = False
    available_on: Tuple[str, ...] = TARGETS
    visibility: str = "public"
    policy_reason: Optional[str] = None
    location: Optional[SourceLocation] = field(default=None)

    def to_dict(self) -> Mapping[str, Any]:
        result = {
            "name": self.name,
            "c_name": self.c_name or self.name,
            "type": _type_to_dict(self.type),
            "callback": self.callback,
            "available_on": list(self.available_on),
            "visibility": self.visibility,
        }
        if self.policy_reason is not None:
            result["policy_reason"] = self.policy_reason
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiVariable:
    c_name: str
    type: CType
    python_name: Optional[str] = None
    storage: Tuple[str, ...] = ()
    available_on: Tuple[str, ...] = TARGETS
    visibility: str = "public"
    policy_reason: Optional[str] = None
    location: Optional[SourceLocation] = field(default=None)

    def to_dict(self) -> Mapping[str, Any]:
        result = {
            "c_name": self.c_name,
            "python_name": self.python_name or self.c_name,
            "type": _type_to_dict(self.type),
            "storage": list(self.storage),
            "available_on": list(self.available_on),
            "visibility": self.visibility,
        }
        if self.policy_reason is not None:
            result["policy_reason"] = self.policy_reason
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiConstant:
    c_name: str
    python_name: str
    value: Optional[str]
    available_on: Tuple[str, ...] = TARGETS
    visibility: str = "public"
    policy_reason: Optional[str] = None
    location: Optional[SourceLocation] = field(default=None)

    def to_dict(self) -> Mapping[str, Any]:
        result = {
            "c_name": self.c_name,
            "python_name": self.python_name,
            "value": self.value,
            "available_on": list(self.available_on),
            "visibility": self.visibility,
        }
        if self.policy_reason is not None:
            result["policy_reason"] = self.policy_reason
        if self.location is not None:
            result["location"] = _location_to_dict(self.location)
        return result


@dataclass(frozen=True)
class ApiObject:
    python_name: str
    c_type: str
    constructor: Optional[str]
    methods: Tuple[str, ...]
    parent: Optional[str] = None
    available_on: Tuple[str, ...] = TARGETS
    visibility: str = "public"
    policy_reason: Optional[str] = None

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "python_name": self.python_name,
            "c_type": self.c_type,
            "constructor": self.constructor,
            "methods": list(self.methods),
            "parent": self.parent,
            "available_on": list(self.available_on),
            "visibility": self.visibility,
            **(
                {"policy_reason": self.policy_reason}
                if self.policy_reason is not None
                else {}
            ),
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
    constants: Tuple[ApiConstant, ...] = ()
    schema_version: int = 1

    def _content_dict(self) -> Mapping[str, Any]:
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
            "constants": [
                item.to_dict()
                for item in sorted(self.constants, key=lambda x: x.python_name)
            ],
        }

    @property
    def api_hash(self) -> str:
        return api_hash_for_dict(self._content_dict())

    def validation_errors(self) -> Tuple[str, ...]:
        """Return semantic model errors that do not require a target backend."""

        errors = []
        seen = {}

        def add(scope: str, name: str, source: str) -> None:
            key = (scope, name)
            previous = seen.get(key)
            if previous is not None:
                errors.append(
                    "duplicate export %s.%s (%s and %s)"
                    % (scope, name, previous, source)
                )
            else:
                seen[key] = source

        for function in self.functions:
            if function.visibility != "public":
                continue
            scope = (
                "module"
                if function.role == "module"
                else "constructor.%s" % function.receiver
                if function.role == "constructor"
                else "%s.%s" % (function.role, function.receiver or "<missing>")
            )
            add(scope, function.python_name, function.c_name)
            if not set(function.available_on) <= set(TARGETS):
                errors.append("unknown target on function %s" % function.c_name)
            if not function.available_on:
                errors.append("public function has no targets: %s" % function.c_name)

        for obj in self.objects:
            if obj.visibility == "public":
                add("module", obj.python_name, "object " + obj.python_name)
                if len(obj.methods) != len(set(obj.methods)):
                    errors.append("duplicate object methods: %s" % obj.python_name)
        for struct in self.structs:
            if struct.visibility == "public":
                add("module", struct.python_name, "struct " + struct.python_name)
        for enum in self.enums:
            if enum.visibility == "public":
                add("module", enum.python_name, "enum " + enum.python_name)
                members = [name for name, _value in enum.members]
                if len(members) != len(set(members)):
                    errors.append("duplicate enum members: %s" % enum.python_name)
        type_names = {
            item.python_name
            for item in self.structs + self.enums
            if item.visibility == "public"
        }
        for typedef in self.typedefs:
            if typedef.visibility == "public":
                # A typedef that names a concrete struct/enum is the C alias
                # for that same Python type, not a second module export.
                if typedef.name in type_names and typedef.type.kind in {
                    "struct",
                    "union",
                    "enum",
                }:
                    continue
                add("module", typedef.name, "typedef " + typedef.c_name)
        for variable in self.variables:
            if variable.visibility == "public":
                add("module", variable.python_name or variable.c_name, "variable " + variable.c_name)
        for constant in self.constants:
            if constant.visibility == "public":
                add("module", constant.python_name, "constant " + constant.c_name)
        return tuple(errors)

    def to_dict(self) -> Mapping[str, Any]:
        result = dict(self._content_dict())
        result["api_hash"] = self.api_hash
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


def _strip_prefix(name: str, module_prefix: str) -> str:
    prefix = module_prefix + "_"
    return name[len(prefix) :] if name.startswith(prefix) else name


def _python_type_name(name: str, module_prefix: str) -> str:
    """Return the legacy Python spelling for an LVGL typedef/tag name."""

    name = name.removeprefix("_" + module_prefix + "_")
    return name.removeprefix(module_prefix + "_")


def _python_enum_name(name: Optional[str], module_prefix: str) -> str:
    if not name:
        return "<anonymous>"
    return _python_type_name(name, module_prefix).removesuffix("_t").upper()


def _python_enum_member_name(name: str, enum_name: str, module_prefix: str) -> str:
    for prefix in (
        "ENUM_" + module_prefix.upper() + "_" + enum_name + "_",
        module_prefix.upper() + "_" + enum_name + "_",
    ):
        if name.startswith(prefix):
            return name[len(prefix) :]
    if name.startswith("ENUM_" + module_prefix.upper() + "_"):
        return name[len("ENUM_" + module_prefix.upper() + "_") :]
    return name


def _same_struct(index: DeclarationIndex, left: Optional[str], right: Optional[str]) -> bool:
    if left is None or right is None:
        return left == right
    return index._struct_identity(left) == index._struct_identity(right)


def _public_struct_name(struct: CStruct) -> str:
    if struct.typedef_names:
        # The preprocessor can expose both a private implementation alias and
        # its public spelling.  Prefer the stable public spelling and make the
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
    policy=None,
) -> ApiModel:
    """Build a deterministic API model with explicit visibility policy."""
    if policy is None:
        from .api_policy import ApiPolicy

        policy = ApiPolicy.default(module_prefix=module_prefix)
    index = DeclarationIndex.from_ir(declarations, module_prefix=module_prefix)

    struct_names = {
        id(struct): _public_struct_name(struct) for struct in declarations.structs
    }
    struct_python_names = {
        id(struct): _python_type_name(struct_names[id(struct)], module_prefix)
        for struct in declarations.structs
    }
    struct_receivers = {}
    for struct in declarations.structs:
        receiver = struct_names[id(struct)]
        for function in index.struct_functions(receiver):
            struct_receivers.setdefault(
                function.name, struct_python_names[id(struct)]
            )

    constructors = {}
    for function in declarations.functions:
        decision = policy.function(function.name)
        plain = _strip_prefix(function.name, module_prefix)
        if (
            decision.visibility != "public"
            or not plain.endswith("_create")
            or not function.parameters
        ):
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
        decision = policy.function(function.name)
        plain = _strip_prefix(function.name, module_prefix)
        role = "module"
        receiver = None
        static = False
        if function.name in constructors.values():
            role = "constructor"
            receiver = next(
                name for name, c_name in constructors.items() if c_name == function.name
            )
        elif decision.visibility == "public":
            matching_objects = sorted(
                (
                    object_name
                    for object_name in constructors
                    if plain.startswith(object_name + "_")
                ),
                key=len,
                reverse=True,
            )
            if matching_objects:
                role = "object_method"
                receiver = matching_objects[0]
                object_methods[receiver].append(
                    plain[len(receiver) + 1 :]
                )
        if role == "module" and function.name in struct_receivers:
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
                static=(
                    role == "object_method"
                    and not _same_struct(
                        index,
                        index.first_argument_type_name(function.name),
                        base_obj_type,
                    )
                ),
                variadic=function.variadic,
                storage=function.storage,
                function_specifiers=function.function_specifiers,
                available_on=decision.available_on,
                visibility=decision.visibility,
                policy_reason=decision.reason,
                location=function.location,
            )
        )

    objects = tuple(
        ApiObject(
            python_name=name,
            c_type=module_prefix + "_" + name + "_t",
            constructor=constructors[name],
            methods=tuple(sorted(object_methods[name])),
            parent=None if name == "obj" else "obj",
            available_on=tuple(
                target
                for target in TARGETS
                if all(
                    target in function.available_on
                    for function in functions
                    if function.receiver == name
                )
            ),
        )
        for name in sorted(constructors)
    )

    function_by_name = {function.c_name: function for function in functions}
    structs = tuple(
        ApiStruct(
            c_name=struct.name,
            python_name=struct_python_names[id(struct)],
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
            visibility=(decision := policy.struct(
                (struct.name,) + tuple(struct.typedef_names)
            )).visibility,
            policy_reason=decision.reason,
            location=struct.location,
        )
        for struct in sorted(
            declarations.structs,
            key=lambda item: (_public_struct_name(item), item.name or ""),
        )
    )
    enums = []
    for enum in sorted(
        declarations.enums,
        key=lambda item: (
            item.typedef_names[0]
            if item.typedef_names
            else item.name or "<anonymous>",
            item.name or "",
        ),
    ):
        if not enum.name and not enum.typedef_names:
            continue
        enum_name = _python_enum_name(
            enum.typedef_names[0] if enum.typedef_names else enum.name,
            module_prefix,
        )
        decision = policy.enum((enum.name,) + tuple(enum.typedef_names))
        enums.append(
            ApiEnum(
                c_name=enum.name,
                python_name=enum_name,
                members=tuple(
                    (
                        _python_enum_member_name(member, enum_name, module_prefix),
                        value,
                    )
                    for member, value in (
                        enum.values or tuple((member, None) for member in enum.members)
                    )
                ),
                typedef_names=enum.typedef_names,
                complete=enum.complete,
                visibility=decision.visibility,
                policy_reason=decision.reason,
                location=enum.location,
            )
        )
    typedefs = tuple(
        ApiTypedef(
            name=_python_type_name(typedef.name, module_prefix),
            c_name=typedef.name,
            type=typedef.type,
            callback=typedef.name in declarations.callback_typedefs,
            visibility=(decision := policy.typedef(typedef.name)).visibility,
            policy_reason=decision.reason,
            location=typedef.location,
        )
        for typedef in declarations.typedefs
    )
    variables = tuple(
        ApiVariable(
            c_name=variable.name,
            type=variable.type,
            python_name=_strip_prefix(variable.name, module_prefix),
            storage=variable.storage,
            visibility=(decision := policy.variable(variable.name)).visibility,
            policy_reason=decision.reason,
            location=variable.location,
        )
        for variable in declarations.variables
        if not variable.name.startswith("_")
    )
    constants = []
    anonymous_groups = {}
    enum_prefix = "ENUM_" + module_prefix.upper() + "_"
    for enum in declarations.enums:
        for name, value in enum.values:
            if not name.startswith(enum_prefix):
                continue
            suffix = name[len(enum_prefix) :]
            group = suffix.rsplit("_", 1)[0] if "_" in suffix else suffix
            anonymous_groups.setdefault(group, []).append((enum, name, value))
    for group, members in sorted(anonymous_groups.items()):
        if len(members) > 1:
            enums.append(
                ApiEnum(
                    c_name=None,
                    python_name=group,
                    members=tuple(
                        (
                            _python_enum_member_name(name, group, module_prefix),
                            value,
                        )
                        for _enum, name, value in members
                    ),
                    complete=True,
                    location=members[0][0].location,
                )
            )
        else:
            enum, name, value = members[0]
            constants.append(
                ApiConstant(
                    c_name=name,
                    python_name=name[len(enum_prefix) :],
                    value=value,
                    location=enum.location,
                )
            )
    return ApiModel(
        module_prefix=module_prefix,
        functions=tuple(functions),
        objects=objects,
        structs=structs,
        enums=tuple(enums),
        typedefs=typedefs,
        variables=variables,
        constants=tuple(constants),
    )


def write_api_model(model: ApiModel, path: Any) -> None:
    """Write deterministic JSON for review, hashing, and downstream checks."""
    with open(path, "w", encoding="utf-8") as output:
        output.write(model.to_json())
