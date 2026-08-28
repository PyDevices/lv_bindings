"""Emit the shared ``lvgl.pyi`` from the canonical API model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, TextIO

from .api_model import API_SCHEMA_VERSION, TARGETS
from .verify_api import validate_api_data

_PY_KEYWORDS = frozenset(
    {
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "case",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "match",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "type",
        "while",
        "with",
        "yield",
    }
)


def _identifier(name: str) -> str:
    if name in _PY_KEYWORDS:
        return "_" + name
    if name and name[0].isdigit():
        return "_" + name
    return name.replace(" ", "_").replace("*", "_ptr")


class CanonicalPyiEmitter:
    """Render one common or target-specific stub from ``api.json``."""

    def __init__(
        self,
        data: Mapping[str, Any],
        *,
        target: str = "all",
        lvgl_version: str,
        naming_style: str = "legacy",
    ) -> None:
        if data.get("schema_version") != API_SCHEMA_VERSION:
            raise ValueError("unsupported canonical API schema")
        if target not in TARGETS + ("all",):
            raise ValueError("unsupported stub target: %s" % target)
        self.data = data
        self.target = target
        self.lvgl_version = lvgl_version
        self.naming_style = naming_style
        self.lines: list[str] = []
        self.functions = tuple(data.get("functions", ()))
        self.objects = tuple(data.get("objects", ()))
        self.structs = tuple(data.get("structs", ()))
        self.enums = tuple(data.get("enums", ()))
        self.variables = tuple(data.get("variables", ()))
        self.constants = tuple(data.get("constants", ()))

    def _available(self, item: Mapping[str, Any]) -> bool:
        available = set(item.get("available_on", ()))
        if self.target == "all":
            return set(TARGETS) <= available
        return self.target in available

    def _public(self, item: Mapping[str, Any]) -> bool:
        return item.get("visibility") == "public" and self._available(item)

    def _view_type(self, item: Mapping[str, Any]) -> str:
        view = item.get("view")
        if not isinstance(view, Mapping):
            raise ValueError("canonical API item is missing a type view")
        python_type = view.get("python_type")
        if not isinstance(python_type, str) or not python_type:
            raise ValueError("canonical API type view has no Python type")
        return python_type

    def emit(self, out: TextIO) -> None:
        self.lines = []
        self._header()
        self._emit_helpers()
        self._emit_module_enums()
        self._emit_structs()
        self._emit_objects()
        self._emit_variables()
        self._emit_functions()
        self._emit_constants()
        out.write("\n".join(self.lines) + "\n")

    def _add(self, line: str = "", indent: int = 0) -> None:
        self.lines.append(("    " * indent) + line if line else "")

    def _header(self) -> None:
        self._add("# LVGL %s" % self.lvgl_version)
        self._add("# Naming style: %s" % self.naming_style)
        self._add('"""Type stubs for LVGL Python bindings (auto-generated)."""')
        self._add("from __future__ import annotations")
        self._add("from collections.abc import Callable")
        self._add("from typing import Any, ClassVar")
        self._add()

    def _emit_helpers(self) -> None:
        self._add("class LvReferenceError(Exception): ...")
        self._add()
        self._add("class C_Pointer:")
        self._add("ptr_val: Any", 1)
        self._add("str_val: str | None", 1)
        self._add("int_val: int", 1)
        self._add("uint_val: int", 1)
        self._add()
        self._add("class Blob:")
        self._add("def __dereference__(self) -> Any: ...", 1)
        self._add()
        self._add("class _Nesting:")
        self._add("value: int", 1)
        self._add()
        self._add("class Struct:")
        self._add("__SIZE__: ClassVar[int]", 1)
        self._add(
            "def __init__(self, fields: dict[str, Any] | None = None, /, **kwargs: Any) -> None: ...",
            1,
        )
        self._add("@classmethod", 1)
        self._add("def __cast__(cls, obj: Any) -> Any: ...", 1)
        self._add("@classmethod", 1)
        self._add("def __cast_instance__(cls, obj: Any) -> Any: ...", 1)
        self._add("@classmethod", 1)
        self._add("def __dereference__(cls, obj: Any) -> Any: ...", 1)
        self._add()

    def _module_enums(self) -> list[Mapping[str, Any]]:
        return sorted(
            (
                enum
                for enum in self.enums
                if self._public(enum) and enum.get("module_name")
            ),
            key=lambda enum: (enum["module_name"], enum.get("python_name", "")),
        )

    def _emit_module_enums(self) -> None:
        for enum in self._module_enums():
            self._emit_enum(enum["module_name"], enum)

    def _emit_enum(self, name: str, enum: Mapping[str, Any], indent: int = 0) -> None:
        self._add("class %s:" % _identifier(name), indent)
        member_type = enum.get("member_type", "int")
        members = enum.get("members", ())
        if not members:
            self._add("...", indent + 1)
        for member in members:
            member_name = _identifier(member["name"])
            self._add("%s: %s" % (member_name, member_type), indent + 1)
        if indent == 0:
            self._add()

    def _emit_structs(self) -> None:
        functions = [
            function
            for function in self.functions
            if function.get("role") == "struct_method"
            and function.get("visibility") == "public"
            and self._available(function)
        ]
        for struct in sorted(
            (struct for struct in self.structs if self._public(struct)),
            key=lambda item: item["python_name"],
        ):
            name = _identifier(struct["python_name"])
            self._add("class %s(Struct):" % name)
            emitted = False
            field_names = set()
            for field in struct.get("fields", ()):
                field_name = _identifier(field.get("name") or "field")
                if field_name in field_names:
                    raise ValueError("duplicate struct field %s.%s" % (name, field_name))
                field_names.add(field_name)
                self._add("%s: %s" % (field_name, self._view_type(field)), 1)
                emitted = True
            for function in sorted(
                (
                    function
                    for function in functions
                    if function.get("receiver") == struct["python_name"]
                ),
                key=lambda item: (item["python_name"], item["c_name"]),
            ):
                if _identifier(function["python_name"]) in field_names:
                    # The generated struct attr handler checks fields before
                    # falling back to its method dictionary.  A colliding
                    # method is therefore not callable through the Python
                    # object and must not be emitted as a duplicate member.
                    continue
                if function.get("static"):
                    self._add("@staticmethod", 1)
                    signature = self._signature(function, instance=False)
                else:
                    signature = self._signature(function, instance=True, skip_receiver=True)
                self._add("def %s" % signature, 1)
                emitted = True
            if not emitted:
                self._add("...", 1)
            self._add()

    def _nested_enums(self, object_name: str) -> list[tuple[str, Mapping[str, Any]]]:
        result = []
        for enum in self.enums:
            if not self._public(enum):
                continue
            for owner_info in enum.get("owners", ()):
                owner = owner_info["object"]
                nested_name = owner_info["name"]
                if owner == object_name:
                    result.append((nested_name, enum))
        return sorted(result, key=lambda item: item[0])

    def _emit_objects(self) -> None:
        functions = [
            function
            for function in self.functions
            if function.get("role") in {"constructor", "object_method"}
            and function.get("visibility") == "public"
            and self._available(function)
        ]
        object_names = {
            object_["python_name"]
            for object_ in self.objects
            if self._public(object_)
        }
        for object_ in sorted(
            (object_ for object_ in self.objects if self._public(object_)),
            key=lambda item: item["python_name"],
        ):
            object_name = object_["python_name"]
            parent = object_.get("parent")
            parent_type = (
                _identifier(parent)
                if parent in object_names
                else "Struct"
            )
            self._add("class %s(%s):" % (_identifier(object_name), parent_type))
            emitted = False
            for nested_name, enum in self._nested_enums(object_name):
                self._emit_enum(nested_name, enum, indent=1)
                emitted = True
            constructor = next(
                (
                    function
                    for function in functions
                    if function.get("role") == "constructor"
                    and function.get("receiver") == object_name
                ),
                None,
            )
            if constructor is not None:
                params = self._parameters(constructor, skip_receiver=False, constructor=True)
                params = "self" + (", " + params if params else "")
                self._add("def __init__(%s) -> None: ..." % params, 1)
                emitted = True
            for function in sorted(
                (
                    function
                    for function in functions
                    if function.get("role") == "object_method"
                    and function.get("receiver") == object_name
                ),
                key=lambda item: (item["python_name"], item["c_name"]),
            ):
                if function.get("static"):
                    self._add("@staticmethod", 1)
                    signature = self._signature(function, instance=False)
                else:
                    signature = self._signature(function, instance=True, skip_receiver=True)
                self._add("def %s" % signature, 1)
                emitted = True
            if not emitted:
                self._add("...", 1)
            self._add()

    def _emit_variables(self) -> None:
        for variable in sorted(
            (
                variable
                for variable in self.variables
                if self._available(variable)
                and (
                    variable.get("visibility") == "public"
                    and variable.get("c_name") != "_nesting"
                )
            ),
            key=lambda item: item.get("python_name") or item["c_name"],
        ):
            name = _identifier(variable.get("python_name") or variable["c_name"])
            self._add("%s: %s" % (name, self._view_type(variable)))
        if any(variable.get("c_name") == "_nesting" for variable in self.variables):
            self._add("_nesting: _Nesting")
        self._add()

    def _emit_functions(self) -> None:
        for function in sorted(
            (
                function
                for function in self.functions
                if function.get("role") == "module" and self._public(function)
            ),
            key=lambda item: (item["python_name"], item["c_name"]),
        ):
            self._add("def %s" % self._signature(function, instance=False))
        self._add()

    def _emit_constants(self) -> None:
        for constant in sorted(
            (constant for constant in self.constants if self._public(constant)),
            key=lambda item: item["python_name"],
        ):
            self._add("%s: int" % _identifier(constant["python_name"]))

    def _signature(
        self,
        function: Mapping[str, Any],
        *,
        instance: bool,
        skip_receiver: bool = False,
    ) -> str:
        params = self._parameters(function, skip_receiver=skip_receiver)
        if instance:
            params = "self" + (", " + params if params else "")
        return "%s(%s) -> %s: ..." % (
            _identifier(function["python_name"]),
            params,
            self._return_type(function),
        )

    def _parameters(
        self,
        function: Mapping[str, Any],
        *,
        skip_receiver: bool,
        constructor: bool = False,
    ) -> str:
        parameters = list(function.get("parameters", ()))
        if skip_receiver and not function.get("static"):
            parameters = parameters[1:]
        used = {"self"} if not constructor and not function.get("static") else set()
        result = []
        for index, parameter in enumerate(parameters):
            name = _identifier(parameter.get("name") or "arg")
            original = name
            suffix = 2
            while name in used:
                name = "%s%d" % (original, suffix)
                suffix += 1
            used.add(name)
            if parameter.get("type", {}).get("kind") == "ellipsis":
                result.append("*%s: Any" % name)
                continue
            default = ""
            if (
                constructor
                and index == 0
                and parameter.get("name") == "parent"
                and parameter.get("view", {}).get("category") == "object_pointer"
            ):
                parameter_type = self._view_type(parameter) + " | None"
                default = " = ..."
            else:
                parameter_type = self._view_type(parameter)
            result.append("%s: %s%s" % (name, parameter_type, default))
        if function.get("variadic"):
            result.append("*args: Any")
        return ", ".join(result)

    def _return_type(self, function: Mapping[str, Any]) -> str:
        view = function.get("return_view")
        if not isinstance(view, Mapping):
            raise ValueError("canonical API function is missing a return view")
        python_type = view.get("python_type")
        if not isinstance(python_type, str) or not python_type:
            raise ValueError("canonical API function has no return Python type")
        return python_type


def load_canonical_api(path: Path) -> Mapping[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema_version") != API_SCHEMA_VERSION:
        raise ValueError("unsupported canonical API schema")
    errors = validate_api_data(data)
    if errors:
        raise ValueError("invalid canonical API model: %s" % "; ".join(errors))
    return data
