# coding:utf-8
from inspect import signature
from functools import lru_cache

py_name_re = r"[_a-zA-Z][_a-zA-Z0-9]*"

py_dot_name_re = r"{name}(?:\.{name})*".format(name=py_name_re)

# this could get call a lot but not on very many different functions; the memory use is worth it
signature = lru_cache(None)(signature)


def identity(x):
    return x


def name_of(f):
    if isinstance(f, str):
        return f
    n = getattr(f, "__name__", None)
    if n is None:
        w = getattr(f, "__wrapped__", None)
        if w is None:
            return str(f)
        n = name_of(w)
    return n


def nice_exc_args(exc):
    if isinstance(exc, Exception):
        args = exc.args
    else:
        args = exc
    if len(args) == 0:
        return ""
    elif len(args) == 1:
        return args[0]
    else:
        return args


def is_prefix(x1, x2):
    return x1 == x2[: len(x1)]


def is_suffix(x1, x2):
    return x1 == x2[len(x2) - len(x1) :]
