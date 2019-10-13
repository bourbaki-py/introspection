# coding:utf-8
import pytest
from bourbaki.introspection.classes import classpath, parameterized_classpath
from bourbaki.introspection.callables import function_classpath
from typing import List, Tuple, Mapping, Callable, Generic, TypeVar
from pathlib import Path


def some_func():
    pass

some_func.__classpath__ = "{}.{}".format(__name__, some_func.__name__)


class some_class:
    __classpath__ = "{}.{}".format(__name__, "some_class")

    def some_method(self):
        pass

    some_method.__classpath__ = "{}.{}.{}".format(__name__, "some_class", some_method.__name__)


T = TypeVar("T")


class some_generic(Generic[T]):
    __classpath__ = "{}.{}".format(__name__, "some_generic")

    def some_generic_method(self):
        pass

    some_generic_method.__classpath__ = "{}.{}.{}".format(__name__, "some_generic", some_generic_method.__name__)


@pytest.mark.parametrize("t,path", [
    (int, "int"),
    (str, "str"),
    (List, "List"),
    (Mapping, "Mapping"),
    (some_class, some_class.__classpath__),
    (some_generic, some_generic.__classpath__),
    (Path, "pathlib.Path"),
])
def test_classpath(t, path):
    assert classpath(t) == path


@pytest.mark.parametrize("t,path", [
    (int, "int"),
    (str, "str"),
    (Path, "pathlib.Path"),
    (some_class, some_class.__classpath__),
    (some_generic, some_generic.__classpath__),
    (some_class.some_method, some_class.some_method.__classpath__),
    (some_generic.some_generic_method, some_generic.some_generic_method.__classpath__),
])
def test_func_classpath(t, path):
    assert function_classpath(t) == path


@pytest.mark.parametrize("t,path", [
    (int, "int"),
    (str, "str"),
    (Path, "pathlib.Path"),
    (List, "List"),
    (List[int], "List[int]"),
    (Callable[..., List], 'Callable[...,List]'),
    (Mapping, "Mapping"),
    (Mapping[Tuple[str, int], List[bool]], "Mapping[Tuple[str,int],List[bool]]"),
    (Callable[[int, str], float], 'Callable[[int,str],float]'),
    (Callable[[Mapping[Tuple[str, int], List[bool]]], some_generic],
         'Callable[[Mapping[Tuple[str,int],List[bool]]],{}]'.format(some_generic.__classpath__)),
    (some_class, some_class.__classpath__),
    (some_generic, some_generic.__classpath__),
    (some_generic[int], some_generic.__classpath__ + "[int]"),
    (some_generic[List[bool]], some_generic.__classpath__ + "[List[bool]]"),
    (some_generic[Mapping[Tuple[str, int], List[bool]]],
         some_generic.__classpath__ + "[Mapping[Tuple[str,int],List[bool]]]")
])
def test_parameterized_classpath(t, path):
    assert parameterized_classpath(t) == path
