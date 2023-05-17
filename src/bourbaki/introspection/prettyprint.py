# coding:utf-8
from typing import Mapping, Union
from collections.abc import Mapping as _Mapping
from numbers import Number
from multipledispatch import dispatch

NoneType = type(None)
DEFAULT_PY_INDENT = "    "
MAX_PY_WIDTH = 80


def has_identifier_keys(obj: Mapping):
    return all(isinstance(k, str) and k.isidentifier() for k in obj.keys())


def get_memoized_ref(obj, memo, prefix):
    path = memo.get(id(obj))
    if path and prefix[: len(path)] != path:
        return fmt_refpath(path)
    elif prefix:
        memo[id(obj)] = prefix


def fmt_refpath(path):
    name = path[0]
    if len(path) == 1:
        return name
    objs = iter(path)
    next(objs)
    return "{}{}".format(name, "".join(map("[{}]".format, map(repr, path[1:]))))


@dispatch(object)
def fmt_pyobj(obj, indent: str = "", prefix=(), top_level=False, memo=None):
    # base case
    if memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref

    return "{}{}".format(indent, repr(obj))


@dispatch(_Mapping)
def fmt_pyobj(obj: Mapping, indent: str = "", prefix=(), top_level=False, memo=None):
    if memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref

    if not len(obj):
        if top_level:
            return ""
        else:
            return "{}"

    if has_identifier_keys(obj):
        if top_level:
            main_template = "{}\n{}"
            joiner = "\n"
        else:
            main_template = "dict(\n{},\n{})"
            joiner = ",\n"
        repr_ = str
        template = "{}{}={}"
    else:
        main_template = "{{\n{},\n{}}}"
        template = "{}{}: {}"
        repr_ = repr
        joiner = ",\n"

    next_indent = indent if top_level else indent + DEFAULT_PY_INDENT

    return main_template.format(
        joiner.join(
            template.format(
                next_indent,
                repr_(k),
                fmt_pyobj(v, indent=next_indent, prefix=prefix + (k,), memo=memo),
            )
            for k, v in obj.items()
        ),
        indent,
    )


@dispatch(tuple)
def fmt_pyobj(obj: tuple, indent: str = "", prefix=(), top_level=False, memo=None):
    if memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref
    if not obj:
        return "()"
    return fmt_pyobj(obj, "(\n{},\n{})", prefix, indent=indent, memo=memo)


@dispatch(list)
def fmt_pyobj(obj: list, indent: str = "", prefix=(), top_level=False, memo=None):
    if memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref
    if not obj:
        return "[]"
    return fmt_pyobj(obj, "[\n{},\n{}]", prefix, indent=indent, memo=memo)


@dispatch(set)
def fmt_pyobj(obj: set, indent: str = "", prefix=(), top_level=False, memo=None):
    if memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref
    if not obj:
        return "set()"
    return fmt_pyobj(obj, "{{\n{},\n{}}}", indent=indent, memo=memo)


@dispatch(frozenset)
def fmt_pyobj(obj: set, indent: str = "", prefix=(), top_level=False, memo=None):
    if memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref
    if not obj:
        return "frozenset()"
    return fmt_pyobj(obj, "frozenset([\n{},\n{}])", indent=indent, memo=memo)


@dispatch((tuple, list), str, (tuple,))
def fmt_pyobj(
    obj: Union[tuple, list, set, frozenset],
    brackets: str,
    prefix=(),
    indent: str = "",
    memo=None,
):
    next_indent = indent + DEFAULT_PY_INDENT
    return brackets.format(
        ",\n".join(
            "{}{}".format(
                next_indent,
                fmt_pyobj(o, indent=next_indent, prefix=prefix + (i,), memo=memo),
            )
            for i, o in enumerate(obj)
        ),
        indent,
    )


@dispatch((set, frozenset), str)
def fmt_pyobj(
    obj: Union[tuple, list, set, frozenset], brackets: str, indent: str = "", memo=None
):
    next_indent = indent + DEFAULT_PY_INDENT
    return brackets.format(
        ",\n".join(
            "{}{}".format(
                next_indent, fmt_pyobj(o, indent=next_indent, prefix=(), memo=memo)
            )
            for i, o in enumerate(obj)
        ),
        indent,
    )


@dispatch(str)
def fmt_pyobj(obj: str, indent: str = "", prefix=(), top_level=False, memo=None):
    if memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref
    indent_ = (
        indent + " " * (len(prefix[-1]) + 1)
        if (prefix and isinstance(prefix[-1], str))
        else indent
    )
    return " \\\n{}".format(indent_).join(
        map(repr, pretty_str_split(obj, width=MAX_PY_WIDTH - len(indent_)))
    )


@dispatch(int)
def fmt_pyobj(obj: int, indent: str = "", prefix=(), top_level=False, memo=None):
    if obj > 256 and memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref
    return repr(obj)


@dispatch(NoneType)
def fmt_pyobj(obj: NoneType, indent: str = "", prefix=(), top_level=False, memo=None):
    return "None"


@dispatch((Number, bytes, bytearray))
def fmt_pyobj(obj: Number, indent: str = "", prefix=(), top_level=False, memo=None):
    if memo is not None:
        ref = get_memoized_ref(obj, memo, prefix)
        if ref:
            return ref
    return repr(obj)


def pretty_str_split(s: str, width: int = MAX_PY_WIDTH):
    tail = s
    if tail == "":
        yield tail
    while tail != "":
        try:
            ix = width - tail[(width - 1) :: -1].index(" ")
        except ValueError:
            ix = width
        yield tail[:ix]
        tail = tail[ix:]
