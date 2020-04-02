# coding:utf-8

from bourbaki.introspection.callables import is_staticmethod, is_classmethod, is_method


class Foo:
    def __init__(self, *args):
        pass

    @classmethod
    def classmethod(cls):
        pass

    @staticmethod
    def staticmethod(*args):
        pass


def test_is_staticmethod():
    assert is_staticmethod(Foo, "staticmethod")
    assert not is_staticmethod(Foo, "__init__")
    assert not is_staticmethod(Foo, "classmethod")


def test_is_classmethod():
    assert is_classmethod(Foo, "classmethod")
    assert not is_classmethod(Foo, "__init__")
    assert not is_classmethod(Foo, "staticmethod")


def test_is_method():
    assert is_method(Foo, "__init__")
    assert not is_method(Foo, "classmethod")
    assert not is_method(Foo, "staticmethod")
