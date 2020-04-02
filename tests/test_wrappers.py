# coding:utf-8
from typing import *
from functools import lru_cache
from inspect import signature
import pytest
from bourbaki.introspection.wrappers import (
    lru_cache_sig_preserving,
    cached_getter,
    const,
)


def func(
    a: int, b: List[str], *args: Tuple[str, bytes], foo: Mapping[int, str], bar: Any
) -> Callable[..., List[str]]:
    return a, b


cached_func = lru_cache(None)(func)

cached_func_same_sig = lru_cache_sig_preserving(None)(func)


class Foo:
    @property
    @cached_getter
    def bar(self):
        return "bar"


@pytest.mark.parametrize("value", [1, 2.3, (4, 5), [6, 7, 8], {9: 10}])
def test_const(value):
    f = const(value)
    assert f() == value
    assert type(f()) is type(value)
    assert repr(f) == str(f) == "{}({})".format(const.__name__, repr(value))


def test_lru_cache_is_cache():
    assert isinstance(cached_func_same_sig, type(cached_func))


def test_lru_cache_same_sig():
    sig1 = signature(func)
    sig2 = signature(cached_func_same_sig)

    assert sig1.parameters == sig2.parameters
    assert sig1.return_annotation == sig2.return_annotation


def test_cached_getter():
    foo = Foo()
    assert not hasattr(foo, "_bar")
    bar = foo.bar
    assert bar == "bar"
    assert hasattr(foo, "_bar")
    assert foo._bar == bar
