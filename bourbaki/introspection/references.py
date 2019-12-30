# coding: utf-8
from typing import Any, Callable
from collections import OrderedDict
from collections.abc import Mapping
import sys
from itertools import chain


class Attr(str):
    def __str__(self):
        return "." + self

    def __call__(self, obj):
        return getattr(obj, self)


class AttrItemPath(tuple):
    """Subclass of tuple representing a chain of item/attribute accesses on an object.
    The result of applying this chain of lookups on and object o can be obtained by calling an instance on o.

    >>> o = [0, "foo", (1, dict(bar="baz"))]
    >>> path = AttrItemPath(2, 1, "bar")
    >>> path(o)
    "baz"
    """

    def __call__(self, obj):
        for n in self:
            if isinstance(n, Attr):
                obj = getattr(obj, n)
            else:
                obj = obj[n]
        return obj

    def __str__(self):
        return "".join(
            "[{}]".format(repr(n)) if not isinstance(n, Attr) else str(n) for n in self
        )

    __repr__ = __str__

    def __getitem__(self, item):
        sub = super().__getitem__(item)
        if isinstance(sub, tuple):
            return AttrItemPath(sub)
        return sub

    @staticmethod
    def get_from(obj):
        """Use as in e.g:
        ints = list(map(AttrItemPath.get_from(obj), find_refs(obj)))"""
        return call_on(obj)


def call_on(*args, **kwargs):
    def f_(f):
        return f(*args, **kwargs)

    return f_


def find_refs_by_type(
    obj,
    type_,
    prefix=(),
    memo=None,
    attrs=True,
    items=True,
    max_depth=5,
    yield_paths=True,
    yield_objects=False,
):
    return find_refs(
        obj,
        lambda x: isinstance(x, type_),
        prefix=prefix,
        memo=memo,
        max_depth=max_depth,
        attrs=attrs,
        items=items,
        yield_paths=yield_paths,
        yield_objects=yield_objects,
    )


def find_refs_by_id(
    obj,
    target_obj,
    prefix=(),
    memo=None,
    attrs=True,
    items=True,
    max_depth=5,
    yield_paths=True,
    yield_objects=False,
):
    return find_refs(
        obj,
        lambda x: x is target_obj,
        prefix=prefix,
        memo=memo,
        max_depth=max_depth,
        attrs=attrs,
        items=items,
        yield_paths=yield_paths,
        yield_objects=yield_objects,
    )


def find_refs_by_size(
    obj,
    min_size: int,
    size_func: Callable[[Any], int] = sys.getsizeof,
    prefix=(),
    memo=None,
    attrs=True,
    items=True,
    max_depth=5,
    yield_paths=True,
    yield_objects=False,
):
    return find_refs(
        obj,
        lambda x: size_func(x) >= min_size,
        prefix=prefix,
        memo=memo,
        max_depth=max_depth,
        attrs=attrs,
        items=items,
        yield_paths=yield_paths,
        yield_objects=yield_objects,
    )


def find_refs(
    obj,
    filter_=None,
    prefix=(),
    memo=None,
    attrs=True,
    items=True,
    max_depth=5,
    yield_paths=True,
    yield_objects=False,
):
    """Find attr/item lookup paths for all objects starting from obj whose referent satisfies the predicate"""
    if max_depth == 0:
        return

    if memo is None:
        memo = OrderedDict()

    if filter_ is None or filter_(obj):
        id_ = id(obj)
        path = AttrItemPath(prefix)

        if id_ not in memo:
            memo[id_] = path
        else:
            return

        if yield_paths:
            if yield_objects:
                yield (path, obj)
            else:
                yield path
        elif yield_objects:
            yield obj

    if items:
        if isinstance(obj, (list, tuple, set, frozenset)):
            items_ = enumerate(obj)
        elif isinstance(obj, Mapping):
            items_ = obj.items()
        else:
            items_ = ()
    else:
        items_ = ()

    if attrs:
        try:
            attrs_ = ((Attr(n), o) for n, o in obj.__dict__.items())
        except AttributeError:
            attrs_ = ()
    else:
        attrs_ = ()

    for n, o in chain(items_, attrs_):
        yield from find_refs(
            o,
            filter_,
            (*prefix, n),
            memo,
            attrs=attrs,
            items=items,
            max_depth=max_depth - 1,
            yield_paths=yield_paths,
            yield_objects=yield_objects,
        )
