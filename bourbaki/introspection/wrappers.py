#coding:utf-8
from inspect import signature, Parameter
from functools import wraps, update_wrapper, lru_cache
import dask
from .callables import bind, call_with, name_of

empty = Parameter.empty


class ArgPreparer:
    def __init__(self, dask_graph, null_value=None):
        if not isinstance(dask_graph, dict) or not all(isinstance(k, str) for k in dask_graph):
            raise ValueError("dask_graph must be a dictionary as accepted by "
                             "dask.get, whose keys are argument names in the "
                             "signature of the function being wrapped")
        self.graph = dask_graph
        self.null_value = null_value

    def __call__(self, f):
        @wraps(f)
        def new_f(*args, **kwargs):
            graph = self.graph.copy()
            null = self.null_value
            bound = bind(f, args, kwargs)
            bound_ = bound.arguments

            update_these = {k for k, v in bound_.items() if v is null and k in graph}
            graph.update(tup for tup in bound_.items() if tup[0] not in update_these)
            bound_.update(zip(update_these, dask.get(graph, list(update_these))))
            return call_with(f, bound)

        return new_f


def lru_cache_sig_preserving(*args, **kwargs):
    def dec(f):
        cached = lru_cache(*args, **kwargs)(f)
        cached.__signature__ = signature(f)
        update_wrapper(cached, f)
        return cached

    return dec


def cached_getter(method):
    attr = '_' + name_of(method)

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
