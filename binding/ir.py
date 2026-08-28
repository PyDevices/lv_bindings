"""Target-neutral C declaration intermediate representation.

The IR deliberately contains declarations only.  Target runtime policy,
argument conversion, public-export decisions, and C emission belong to later
pipeline stages.  This module has no dependency on any binding target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple

from pycparser import c_ast, c_generator, c_parser


@dataclass(frozen=True)
class SourceLocation:
    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    @classmethod
    def from_coord(cls, coord: Any) -> "SourceLocation":
        if coord is None:
            return cls()
        return cls(
            file=getattr(coord, "file", None),
            line=getattr(coord, "line", None),
            column=getattr(coord, "column", None),
        )


@dataclass(frozen=True)
class CType:
    """A normalized C type expression."""

    kind: str
    name: Optional[str] = None
    qualifiers: Tuple[str, ...] = ()
    target: Optional["CType"] = None
    element: Optional["CType"] = None
    dimensions: Tuple[str, ...] = ()
    return_type: Optional["CType"] = None
    parameters: Tuple["CParameter", ...] = ()
    variadic: bool = False

    def canonical(self) -> str:
        qualifiers = " ".join(self.qualifiers)
        prefix = (qualifiers + " ") if qualifiers else ""
        if self.kind in {"primitive", "identifier"}:
            return prefix + (self.name or "<anonymous>")
        if self.kind in {"struct", "union", "enum"}:
            return prefix + self.kind + " " + (self.name or "<anonymous>")
        if self.kind == "pointer":
            return self.target.canonical() + " *" if self.target else "void *"
        if self.kind == "array":
            suffix = "".join("[" + dimension + "]" for dimension in self.dimensions)
            return (self.element.canonical() if self.element else "<unknown>") + suffix
        if self.kind == "function":
            args = ", ".join(parameter.type.canonical() for parameter in self.parameters)
            if self.variadic:
                args = (args + ", ") if args else ""
                args += "..."
            return "{} ({})".format(
                self.return_type.canonical() if self.return_type else "void",
                args,
            )
        if self.kind == "ellipsis":
            return "..."
        return prefix + (self.name or "<unknown>")


@dataclass(frozen=True)
class CParameter:
    name: Optional[str]
    type: CType
    location: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class CField:
    name: Optional[str]
    type: CType
    location: SourceLocation = field(default_factory=SourceLocation)
    bit_width: Optional[str] = None


@dataclass(frozen=True)
class CFunction:
    name: str
    return_type: CType
    parameters: Tuple[CParameter, ...]
    variadic: bool = False
    storage: Tuple[str, ...] = ()
    is_definition: bool = False
    location: SourceLocation = field(default_factory=SourceLocation)

    @property
    def signature(self) -> str:
        args = ", ".join(parameter.type.canonical() for parameter in self.parameters)
        if self.variadic:
            args = (args + ", ") if args else ""
            args += "..."
        return "{} {}({})".format(self.return_type.canonical(), self.name, args)


@dataclass(frozen=True)
class CStruct:
    name: Optional[str]
    kind: str
    fields: Tuple[CField, ...] = ()
    typedef_names: Tuple[str, ...] = ()
    complete: bool = False
    location: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class CEnum:
    name: Optional[str]
    members: Tuple[str, ...] = ()
    typedef_names: Tuple[str, ...] = ()
    complete: bool = False
    location: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class CTypedef:
    name: str
    type: CType
    location: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class CVariable:
    name: str
    type: CType
    storage: Tuple[str, ...] = ()
    location: SourceLocation = field(default_factory=SourceLocation)


@dataclass(frozen=True)
class DeclarationIR:
    """All declarations from one preprocessed translation unit."""

    functions: Tuple[CFunction, ...] = ()
    structs: Tuple[CStruct, ...] = ()
    enums: Tuple[CEnum, ...] = ()
    typedefs: Tuple[CTypedef, ...] = ()
    variables: Tuple[CVariable, ...] = ()

    @property
    def functions_by_name(self) -> Mapping[str, CFunction]:
        return {function.name: function for function in self.functions}

    @property
    def typedefs_by_name(self) -> Mapping[str, CTypedef]:
        return {typedef.name: typedef for typedef in self.typedefs}

    @property
    def callback_typedefs(self) -> Mapping[str, CType]:
        return {
            typedef.name: typedef.type
            for typedef in self.typedefs
            if typedef.type.kind == "pointer"
            and typedef.type.target is not None
            and typedef.type.target.kind == "function"
        }


class _Converter:
    def __init__(self) -> None:
        self.generator = c_generator.CGenerator()

    def location(self, node: Any) -> SourceLocation:
        return SourceLocation.from_coord(getattr(node, "coord", None))

    def expression(self, node: Any) -> str:
        if node is None:
            return ""
        return self.generator.visit(node)

    def type(self, node: Any) -> CType:
        if isinstance(node, c_ast.TypeDecl):
            result = self.type(node.type)
            if node.quals:
                result = CType(
                    kind=result.kind,
                    name=result.name,
                    qualifiers=tuple(node.quals) + result.qualifiers,
                    target=result.target,
                    element=result.element,
                    dimensions=result.dimensions,
                    return_type=result.return_type,
                    parameters=result.parameters,
                    variadic=result.variadic,
                )
            return result
        if isinstance(node, c_ast.IdentifierType):
            names = tuple(node.names)
            primitive_names = {
                "_Bool",
                "bool",
                "char",
                "double",
                "float",
                "int",
                "long",
                "short",
                "signed",
                "unsigned",
                "void",
            }
            kind = "primitive" if set(names) <= primitive_names else "identifier"
            return CType(kind=kind, name=" ".join(names))
        if isinstance(node, c_ast.PtrDecl):
            return CType(
                kind="pointer",
                qualifiers=tuple(node.quals or ()),
                target=self.type(node.type),
            )
        if isinstance(node, c_ast.ArrayDecl):
            dimension = self.expression(node.dim)
            return CType(
                kind="array",
                element=self.type(node.type),
                dimensions=(dimension,),
            )
        if isinstance(node, c_ast.FuncDecl):
            parameters, variadic = self.parameters(node.args)
            return CType(
                kind="function",
                return_type=self.type(node.type),
                parameters=parameters,
                variadic=variadic,
            )
        if isinstance(node, c_ast.Struct):
            return CType(kind="struct", name=node.name)
        if isinstance(node, c_ast.Union):
            return CType(kind="union", name=node.name)
        if isinstance(node, c_ast.Enum):
            return CType(kind="enum", name=node.name)
        if isinstance(node, c_ast.EllipsisParam):
            return CType(kind="ellipsis", name="...")
        if isinstance(node, c_ast.Typename):
            return self.type(node.type)
        return CType(kind="unknown", name=self.generator.visit(node))

    def parameter(self, node: Any) -> CParameter:
        if isinstance(node, c_ast.EllipsisParam):
            return CParameter(name=None, type=CType(kind="ellipsis", name="..."))
        return CParameter(
            name=getattr(node, "name", None),
            type=self.type(node.type),
            location=self.location(node),
        )

    def parameters(self, node: Any) -> Tuple[Tuple[CParameter, ...], bool]:
        if node is None or not node.params:
            return (), False
        parameters = tuple(self.parameter(parameter) for parameter in node.params)
        return parameters, any(parameter.type.kind == "ellipsis" for parameter in parameters)

    def fields(self, node: Any) -> Tuple[CField, ...]:
        if not node.decls:
            return ()
        result = []
        for declaration in node.decls:
            result.append(
                CField(
                    name=declaration.name,
                    type=self.type(declaration.type),
                    location=self.location(declaration),
                    bit_width=self.expression(declaration.bitsize)
                    if declaration.bitsize is not None
                    else None,
                )
            )
        return tuple(result)

    def struct(self, node: Any, typedef_names: Sequence[str] = ()) -> CStruct:
        kind = "union" if isinstance(node, c_ast.Union) else "struct"
        return CStruct(
            name=node.name,
            kind=kind,
            fields=self.fields(node),
            typedef_names=tuple(typedef_names),
            complete=node.decls is not None,
            location=self.location(node),
        )

    def enum(self, node: c_ast.Enum, typedef_names: Sequence[str] = ()) -> CEnum:
        members = ()
        if node.values is not None:
            members = tuple(
                enumerator.name for enumerator in (node.values.enumerators or ())
            )
        return CEnum(
            name=node.name,
            members=members,
            typedef_names=tuple(typedef_names),
            complete=node.values is not None,
            location=self.location(node),
        )


def _function_from_decl(converter: _Converter, declaration: Any, is_definition=False):
    function_type = declaration.type
    parameters, variadic = converter.parameters(function_type.args)
    return CFunction(
        name=declaration.name,
        return_type=converter.type(function_type.type),
        parameters=parameters,
        variadic=variadic,
        storage=tuple(declaration.storage or ()),
        is_definition=is_definition,
        location=converter.location(declaration),
    )


def parse_ast(ast: c_ast.FileAST) -> DeclarationIR:
    """Convert a pycparser AST to target-neutral declarations."""

    converter = _Converter()
    functions = []
    structs = []
    enums = []
    typedefs = []
    variables = []
    struct_keys = set()
    enum_keys = set()

    def add_struct(node, typedef_names=()):
        key = (id(node), tuple(typedef_names))
        if key not in struct_keys:
            struct_keys.add(key)
            structs.append(converter.struct(node, typedef_names))

    def add_enum(node, typedef_names=()):
        key = (id(node), tuple(typedef_names))
        if key not in enum_keys:
            enum_keys.add(key)
            enums.append(converter.enum(node, typedef_names))

    def typedef_composite(node):
        """Return a composite directly named by a typedef, if present."""

        if isinstance(node, c_ast.TypeDecl) and isinstance(
            node.type, (c_ast.Struct, c_ast.Union, c_ast.Enum)
        ):
            return node.type
        return None

    for external in ast.ext:
        if isinstance(external, c_ast.FuncDef):
            functions.append(_function_from_decl(converter, external.decl, True))
            continue
        if isinstance(external, c_ast.Typedef):
            typedefs.append(
                CTypedef(
                    name=external.name,
                    type=converter.type(external.type),
                    location=converter.location(external),
                )
            )
            composite = typedef_composite(external.type)
            if isinstance(composite, (c_ast.Struct, c_ast.Union)):
                add_struct(composite, (external.name,))
            elif isinstance(composite, c_ast.Enum):
                add_enum(composite, (external.name,))
            continue
        if not isinstance(external, c_ast.Decl):
            continue
        if isinstance(external.type, c_ast.FuncDecl):
            functions.append(_function_from_decl(converter, external))
        elif isinstance(external.type, (c_ast.Struct, c_ast.Union)):
            add_struct(external.type)
            if external.name:
                variables.append(
                    CVariable(
                        name=external.name,
                        type=converter.type(external.type),
                        storage=tuple(external.storage or ()),
                        location=converter.location(external),
                    )
                )
        elif isinstance(external.type, c_ast.Enum):
            add_enum(external.type)
        elif external.name:
            variables.append(
                CVariable(
                    name=external.name,
                    type=converter.type(external.type),
                    storage=tuple(external.storage or ()),
                    location=converter.location(external),
                )
            )

    return DeclarationIR(
        functions=tuple(functions),
        structs=tuple(structs),
        enums=tuple(enums),
        typedefs=tuple(typedefs),
        variables=tuple(variables),
    )


def parse_source(source: str, filename: str = "<none>", parser=None) -> DeclarationIR:
    """Parse C source and return a target-neutral declaration IR."""

    parser = parser or c_parser.CParser()
    return parse_ast(parser.parse(source, filename=filename))
