"""Export naming styles (legacy vs pythonic) for emit and emit_pyi."""

from __future__ import annotations

_NAMING_STYLE = "legacy"

VALID_STYLES = frozenset({"legacy", "pythonic"})


def set_naming_style(style: str) -> None:
    global _NAMING_STYLE
    if style not in VALID_STYLES:
        raise ValueError("unsupported naming style: {!r}".format(style))
    _NAMING_STYLE = style


def get_naming_style() -> str:
    return _NAMING_STYLE


def _to_pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def _to_upper_snake(name: str) -> str:
    if not name:
        return name
    parts = name.split("_")
    if all(part.isupper() for part in parts if part):
        return name
    return name.upper()


def _legacy_base(name: str, kind: str) -> str:
    from .analyze import get_enum_member_name
    from . import helpers
    from .helpers import get_enum_name, sanitize

    def _simplify(name: str) -> str:
        if getattr(helpers, "lv_func_pattern", None) is None:
            return name
        return helpers.simplify_identifier(name)

    def _enum_name(name: str) -> str:
        if getattr(helpers, "lv_enum_name_pattern", None) is None:
            return sanitize(name)
        return sanitize(get_enum_name(name))

    if kind == "object":
        return sanitize(name)
    if kind == "enum":
        return _enum_name(name)
    if kind == "enum_member":
        return sanitize(get_enum_member_name(name))
    if kind == "function":
        return sanitize(_simplify(name))
    if kind == "struct":
        return sanitize(_simplify(name))
    if kind == "blob":
        return sanitize(_simplify(name))
    if kind == "constant":
        return _enum_name(name)
    return sanitize(name)


def _pythonic_transform(base: str, kind: str) -> str:
    if kind in ("object", "enum", "struct"):
        return _to_pascal_case(base)
    if kind in ("enum_member", "constant"):
        return _to_upper_snake(base)
    return base


def export_name(name: str, kind: str) -> str:
    """Return the Python-facing export identifier for ``name``."""
    base = _legacy_base(name, kind)
    if _NAMING_STYLE == "legacy":
        return base
    return _pythonic_transform(base, kind)
