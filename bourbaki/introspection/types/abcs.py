# coding:utf-8
import typing
import enum
from .inspection import is_top_type

STDLIB_MODULES = {"builtins", "collections", "typing", "abc", "numbers", "decimal", "re", "_sre", "os",
                  "enum", "datetime", "time", "pathlib", "ipaddress", "urllib", "uuid"}


def _issubclass_gen(sub, clss):
    # necessitated by typing module types not being comparable to builtin types with issubclass, only to each other
    for cls in clss:
        try:
            yield issubclass(sub, cls)
        except TypeError:
            pass


# Generic subscriptable with string references to types via classpath for prevention of expensive imports

CLS = typing.TypeVar("CLS")


class LazyType(typing.Generic[CLS]):
    pass


# convenience type aliases for registering functions

class NonCollectionMeta(type):
    def __subclasscheck__(self, subclass):
        return not issubclass(subclass, typing.Collection) or issubclass(subclass, str)


class NonCollection(metaclass=NonCollectionMeta):
    pass


class NonStrCollectionMeta(type):
    coll_type = typing.Collection
    non_subclasses = ()

    def __instancecheck__(self, instance):
        return self.__subclasscheck__(type(instance))

    def __subclasscheck__(self, subclass):
        if subclass is self:
            return True
        return issubclass(subclass, self.coll_type) and not any(_issubclass_gen(subclass, self.non_subclasses))


class NonStrCollection(metaclass=NonStrCollectionMeta):
    non_subclasses = (str,)
    pass


class NonAnyStrCollection(metaclass=NonStrCollectionMeta):
    non_subclasses = (str, bytes, typing.ByteString)
    pass


class NonStrSequence(NonStrCollection):
    non_subclasses = (str,)
    coll_type = typing.Sequence


class NonAnyStrSequence(NonAnyStrCollection):
    non_subclasses = (str, bytes, typing.ByteString)
    coll_type = typing.Sequence


class BuiltinMeta(type):
    __module__ = "builtins"

    def __subclasscheck__(cls, subclass):
        return subclass.__module__ == "builtins" and not is_top_type(subclass)


class BuiltinAtomicMeta(BuiltinMeta):
    def __subclasscheck__(cls, subclass):
        return super().__subclasscheck__(subclass) and (subclass is str
                                                        or not issubclass(subclass, typing.Collection))


class Builtin(metaclass=BuiltinMeta):
    # for registration of a default method for all builtins
    pass


class BuiltinAtomic(metaclass=BuiltinAtomicMeta):
    # for registration of a default method for all builtins
    pass


class NonStdLibMeta(type):
    def __subclasscheck__(self, subclass):
        # don't allow subclasses of enum.Enum - gray area but they shouldn't generally have custom constuctors
        return subclass.__module__.split(".")[0] not in STDLIB_MODULES and not issubclass(subclass, enum.Enum)


class NonStdLib(metaclass=NonStdLibMeta):
    # for registration of types outside of the standard library which may subclass ABCs such as Collection;
    # we may want to treat them separately in some cases as they may not have the same constructors -
    # an example is pandas.DataFrame
    pass