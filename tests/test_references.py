from sys import getsizeof

import pytest

from bourbaki.introspection.references import (
    find_refs_by_id,
    find_refs_by_size,
    find_refs_by_type,
)

l = ["foo", "bar", 1, 2, tuple(range(10))]


class Foo:
    l = l
    x = 123.0


class Bar:
    __slots__ = ["x", "y"]

    def __init__(self, x):
        self.x = x


@pytest.mark.parametrize(
    "obj,type_,value",
    [
        (l, int, 1),
        (l, str, "foo"),
        (l, tuple, tuple(range(10))),
        (Foo, list, l),
        (Foo, float, 123.0),
        (Bar(l), list, l),
    ],
)
def test_find_refs_by_type(obj, type_, value):
    refs = find_refs_by_type(obj, type_)
    path = next(refs)
    assert path(obj) == value


@pytest.mark.parametrize("obj,size,value", [(l, getsizeof(tuple(range(10))), l[-1])])
def test_find_refs_by_size(obj, size, value):
    refs = find_refs_by_size(obj, size, attrs=False)
    path = next(refs)
    assert path(obj) == value


@pytest.mark.parametrize(
    "obj,target,value",
    [(l, l[-1], l[-1]), (Foo, l, Foo.l), (Foo, Foo.x, Foo.x), (Bar(l), l, l)],
)
def test_find_refs_by_id(obj, target, value):
    refs = find_refs_by_id(obj, target)
    path = next(refs)
    assert path(obj) == value
