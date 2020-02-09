# coding:utf-8
from inspect import signature, Parameter
from functools import update_wrapper, lru_cache
from .callables import name_of

empty = Parameter.empty


def lru_cache_sig_preserving(*args, **kwargs):
    def dec(f):
        cached = lru_cache(*args, **kwargs)(f)
        cached.__signature__ = signature(f)
        update_wrapper(cached, f)
        return cached

    return dec


def cached_getter(method):
    attr = "_" + name_of(method)

    def getter(self):
        val = getattr(self, attr, empty)
        if val is empty:
            val = method(self)
            setattr(self, attr, val)
        return val

    return getter


class const:
    """A callable that returns `value` no matter what its inputs"""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "{}({})".format(type(self).__name__, repr(self.value))

    def __repr__(self):
        return str(self)

    def __call__(self, *args, **kwargs):
        return self.value
