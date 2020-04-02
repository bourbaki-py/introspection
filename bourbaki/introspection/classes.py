# coding:utf-8
from typing import Union, Any
from tempfile import mktemp
from inspect import getmro
from itertools import repeat
from functools import singledispatch
from .types.compat import NEW_TYPING
from .types import get_generic_origin, get_generic_args, LazyType, ForwardRef


def classpath(t: type):
    org = get_generic_origin(t)
    if org is Union:
        return "Union"
    if org is Any:
        return "Any"

    if issubclass(org, LazyType):
        a = get_generic_args(t)[0]
        if isinstance(a, str):
            return a
        elif isinstance(a, ForwardRef):
            return a.__forward_arg__
        else:
            t = a
    if t.__module__ in ("builtins", "typing"):
        return get_qualname(t)
    return "{}.{}".format(t.__module__, get_qualname(t))


if NEW_TYPING:
    from typing import _GenericAlias

    # python3.7 new typing module
    classpath = singledispatch(classpath)

    def get_qualname(t: type):
        if t.__module__ == "typing" and isinstance(t, _GenericAlias):
            return t._name
        return getattr(t, "__qualname__", get_generic_origin(t).__qualname__)

    @classpath.register(_GenericAlias)
    def classpath_generic_alias(t: _GenericAlias):
        if t.__module__ == "typing":
            return t._name
        return "{}.{}".format(t.__module__, get_qualname(t))


else:

    def get_qualname(t: type):
        return getattr(t, "__qualname__", get_generic_origin(t).__qualname__)


def parameterized_classpath(t: type):
    def _inner(t):
        if t is Ellipsis:
            return "..."
        if isinstance(t, list):
            # for callables
            return "[{}]".format(",".join(map(_inner, t)))
        return parameterized_classpath(t)

    args = get_generic_args(t, evaluate=True)
    origin = get_generic_origin(t)
    if not args:
        return classpath(origin)
    return "{}[{}]".format(classpath(origin), ",".join(map(_inner, args)))


def most_specific_constructor(t: type, return_class=False):
    # first class in mro, preferring __new__ over __init__
    # note that this is different than getattr(t, "__new__", getattr(t, "__init__)),
    # since t.__new__ is usually higher up in the mro, e.g. object.__new__
    t = get_generic_origin(t)
    tups = [(c, "__new__" in c.__dict__, "__init__" in c.__dict__) for c in getmro(t)]
    cls, new, init = next(tup for tup in tups if (tup[1] or tup[2]))
    init = getattr(t, "__new__") if new else getattr(t, "__init__")

    if return_class:
        return cls, init
    return init


def all_subclasses(cls: type, include_self=True):
    def all_subclasses_(cls: type, memo=None):
        if memo is None:
            memo = set()
        for c in cls.__subclasses__():
            if c not in memo:
                yield c
                memo.add(c)
            yield from all_subclasses_(c, memo)

    if include_self:
        yield cls

    yield from all_subclasses_(cls)


def inheritances(cls):
    subs = cls.__subclasses__()
    if subs:
        yield from zip(repeat(cls), subs)
        for c in subs:
            yield from inheritances(c)


def inheritance_hierarchy(cls):  # pragma: no cover (for visualization only)
    try:
        from graphviz import Digraph as Dot
    except ImportError:
        raise ImportError("visualization of inheritance hierarchies requires graphviz")
    d = Dot("Inheritance hierarchy for {}".format(classpath(cls)))
    d.edges((classpath(c1), classpath(c2)) for c1, c2 in inheritances(cls))
    return d


def render_inheritance_hierarchy(
    cls, path=None
):  # pragma: no cover (for visualization only)
    d = inheritance_hierarchy(cls)
    if path is None:
        path = mktemp(suffix=classpath(cls) + ".gv")
    d.render(path, view=True, cleanup=True)
