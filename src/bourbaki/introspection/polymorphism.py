# coding:utf-8
from typing import Mapping, Callable, Hashable, Any, Optional
from inspect import Parameter
import collections.abc
from functools import lru_cache
from multipledispatch import Dispatcher
from types import MethodType

Empty = Parameter.empty


class UnregisteredType(TypeError, NotImplementedError):
    pass


class UnregisteredGeneric(UnregisteredType):
    def __str__(self):
        dispatcher, type_ = self.args
        return "Generic type {} has not been registered for dispatcher {}".format(
            type_, dispatcher
        )


class UnregisteredConcreteType(UnregisteredType):
    def __str__(self):
        dispatcher, type_ = self.args
        return "Type {} has not been registered for dispatcher {}".format(
            type_, dispatcher
        )


class TypeLevelDispatch(Dispatcher):
    """A multiply-dispatched function that acts on type objects directly rather that value inhabitants"""

    def __call__(self, *types):
        f = self._cache.get(types)
        if f is None:
            f = super().dispatch(*types)
            self._cache[types] = f
        return f(*types)


class MultipleDispatchMethod(Dispatcher):
    __slots__ = Dispatcher.__slots__

    def __get__(self, obj, cls):
        f = self.bind_class(cls)
        if obj is None:
            return f
        return MethodType(f, obj)

    def add(self, signature, func):
        name = func if isinstance(func, str) else func.__name__
        super().add(signature, name)

    @lru_cache(None)
    def bind_class(self, cls):
        new = Dispatcher(self.name, self.doc)
        for ts, name in self.funcs.items():
            new.add((object, *ts), getattr(cls, name))
        return new


Predicate = Callable[[Any], bool]


class SingleValueDispatch:
    def __init__(self, name):
        self.name = self.__name__ = name
        self.funcs = []

    def register(self, predicate: Predicate):
        def dec(f: Callable):
            self._insert(predicate, f)
            return f

        return dec

    def register_fork(
        self, value_mapping: Optional[Mapping[Hashable, Callable]] = None
    ):
        if not isinstance(value_mapping, collections.abc.Mapping):  # pragma: no cover
            raise TypeError(
                "value_mapping must be a Mapping instance; got {}".format(
                    type(value_mapping)
                )
            )

        def dec(predicate: Predicate):
            self._insert(predicate, None, value_mapping)
            return predicate

        return dec

    def _insert(
        self,
        predicate,
        f: Optional[Predicate] = None,
        value_mapping: Optional[Mapping[Hashable, Predicate]] = None,
    ):
        if not callable(predicate):  # pragma: no cover
            raise TypeError("Predicates must be callable; got {}".format(predicate))

        self.funcs.append((predicate, value_mapping, f))

    def __call__(self, arg, *args, **kwargs):
        for predicate, mapping, f in reversed(self.funcs):
            key = predicate(arg)
            if mapping is None:
                if key:
                    return f(arg, *args, **kwargs)
                continue
            else:
                f = mapping.get(key)
                if f is None:
                    continue
                return f(arg, *args, **kwargs)
        raise ValueError("No predicates in {} matched value {}".format(self, arg))

    def __str__(self):
        return "{}({})".format(type(self).__name__, repr(self.__name__))
