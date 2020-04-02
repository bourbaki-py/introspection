# coding:utf-8
from typing import *
from typing import Pattern, Match, ChainMap, Counter, Collection, TypeVar, Generic
import types
import pytest
from numbers import Number, Integral

from bourbaki.introspection.typechecking import isinstance_generic

T_co = TypeVar('T', covariant=True)


class myfloat(float):
    pass


class mylist(List[T_co]):
    pass


def f(a: float, b: int) -> mylist[int]:
    pass


def g(a: myfloat, b: bool) -> Sequence[Number]:
    pass


class MyCallable(Generic[T_co]):
    def __call__(self, x: float, y: T_co) -> Collection[T_co]:
        pass


e = MyCallable[int]()


@pytest.mark.parametrize("f,t", [
    (f, Callable[[float, int], mylist[int]]),
    (f, Callable[[myfloat, int], mylist[int]]),
    (f, Callable[[myfloat, bool], mylist[int]]),
    (f, Callable[[float, int], List[int]]),
    (f, Callable[[float, int], Sequence[int]]),
    (f, Callable[[myfloat, bool], Sequence[Number]]),
    (f, Callable[[myfloat, bool], Any]),
    (f, types.FunctionType),
    # custom callable generic
    (e, Callable[[float, int], Collection[int]]),
    (e, Callable[[myfloat, int], Collection[int]]),
    (f, Callable[[myfloat, int], mylist[int]]),
    (f, Callable[[myfloat, bool], mylist[int]]),
    (f, Callable[[float, int], List[int]]),
    (f, Callable[[float, int], Sequence[int]]),
    (f, Callable[[myfloat, bool], Sequence[Number]]),
    (f, Callable[[myfloat, bool], Any]),
    # builtin
    (sorted, types.BuiltinFunctionType),
    (int, Callable[[str, int], int]),
    (int, Callable[[Number], int]),
    (sorted, Callable[[Set[int]], List]),
])
def test_callable_typechecker_pos(f, t):
    assert isinstance_generic(f, t)


@pytest.mark.parametrize("f,t", [
    (g, Callable[[float, int], mylist[int]]),
    (g, Callable[[myfloat, int], mylist[int]]),
    (g, Callable[[myfloat, bool], mylist[int]]),
    (g, Callable[[float, int], List[int]]),
    (g, Callable[[float, int], Sequence[int]]),
    (g, Callable[[myfloat, bool], Sequence[Integral]]),
    (g, types.BuiltinFunctionType),
    # custom callable generic
    (e, Callable[[float, int], Collection[bool]]),
    # builtin
    (int, Callable[[int, int], int]),
    (int, Callable[[List], int]),
    (sorted, Callable[[int], List[int]]),
])
def test_callable_typechecker_neg(f, t):
    assert not isinstance_generic(f, t)


@pytest.mark.parametrize("type_,t", [
    (int, Type[int]),
    (bool, Type[int]),
    (int, Type[Integral]),
    (complex, Type[Number]),
    (Tuple[float, bool], Type[Tuple[Number, Integral]]),
    (Tuple[float, int, complex], Type[Sequence[Number]]),
    (Callable[[float, int], mylist[int]], Type[Callable[[myfloat, bool], Sequence[Number]]]),
])
def test_type_typechecker_pos(type_, t):
    assert isinstance_generic(type_, t)
