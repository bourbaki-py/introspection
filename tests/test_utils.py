import functools

import pytest

from bourbaki.introspection.utils import name_of


def foo():
    pass


@functools.wraps(foo)
def bar():
    return foo()


class Foo:
    x = 1


fooinstance = Foo()


@pytest.mark.parametrize(
    "obj,name",
    [
        ("foo", "foo"),
        (foo, "foo"),
        (bar, "foo"),
        (Foo, "Foo"),
        (Foo.x, "1"),
        (fooinstance, str(fooinstance)),
    ],
)
def test_name_of(obj, name):
    assert name_of(obj) == name
