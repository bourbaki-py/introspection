# coding:utf-8
import typing
import enum
from .inspection import is_top_type, is_named_tuple_class

STDLIB_MODULES = {
    "builtins",
    "collections",
    "typing",
    "abc",
    "numbers",
    "decimal",
    "re",
    "_sre",
    "os",
    "enum",
    "datetime",
    "time",
    "pathlib",
    "ipaddress",
    "urllib",
    "uuid",
}


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


class _InstanceCheckFromSubclassCheck(type):
    def __instancecheck__(self, instance):  # pragma: no cover
        return self.__subclasscheck__(type(instance))

    def __subclasscheck__(self, subclass):  # pragma: no cover
        raise NotImplementedError()


class NonCollectionMeta(_InstanceCheckFromSubclassCheck):
    def __subclasscheck__(self, subclass):
        return not issubclass(subclass, typing.Collection) or issubclass(subclass, str)


class NonCollection(metaclass=NonCollectionMeta):
    pass


class NonStrCollectionMeta(_InstanceCheckFromSubclassCheck):
    """This is a subtype of `coll_type` by implication of only admitting as concrete subtypes a subset
    of `coll_type`'s concretizations"""

    coll_type = typing.Collection
    non_subclasses = ()

    def __subclasscheck__(self, subclass):
        if subclass is self:
            return True

        if subclass is self.coll_type:
            return False

        if isinstance(subclass, type(self)):
            # if subclass shares the same metaclass as self,
            # and any explicit base of subclass is a subclass of self, then subclass _is_ a subtype
            return any(
                issubclass(base, self) for base in getattr(subclass, "__bases__", ())
            )

        if any(issubclass(base, subclass) for base in self.__bases__):
            # anything above this type's explicit bases is _not_ a subtype
            return False

        if issubclass(subclass, self.coll_type):
            # if subclass is a subclass of any of the explicit non_subclasses however, it is _not_ a subtype
            return not any(_issubclass_gen(subclass, self.non_subclasses))

        return False


class NonStrCollection(metaclass=NonStrCollectionMeta):
    non_subclasses = (str,)
    pass


class NonAnyStrCollection(NonStrCollection, metaclass=NonStrCollectionMeta):
    non_subclasses = (str, typing.ByteString)
    pass


class NonStrSequence(NonStrCollection):
    non_subclasses = (str,)
    coll_type = typing.Sequence


class NonAnyStrSequence(NonStrSequence, NonAnyStrCollection):
    non_subclasses = (str, typing.ByteString)
    coll_type = typing.Sequence


class BuiltinMeta(_InstanceCheckFromSubclassCheck):
    __module__ = "builtins"

    def __subclasscheck__(cls, subclass):
        return subclass.__module__ == "builtins" and not is_top_type(subclass)


class BuiltinAtomicMeta(BuiltinMeta):
    def __subclasscheck__(cls, subclass):
        return super().__subclasscheck__(subclass) and (
            subclass is str or not issubclass(subclass, typing.Collection)
        )


class Builtin(metaclass=BuiltinMeta):
    # for registration of a default method for all builtins
    pass


class BuiltinAtomic(metaclass=BuiltinAtomicMeta):
    """for registration of a default method for all builtins"""

    pass


class NonStdLibMeta(_InstanceCheckFromSubclassCheck):
    def __subclasscheck__(self, subclass):
        # don't allow subclasses of enum.Enum - gray area but they shouldn't generally have custom constuctors
        # ditto for NamedTuple classes
        return (
            subclass.__module__.split(".")[0] not in STDLIB_MODULES
            and not issubclass(subclass, enum.Enum)
            and not is_named_tuple_class(subclass)
        )


class NonStdLib(metaclass=NonStdLibMeta):
    """for registration of types outside of the standard library which may subclass ABCs such as Collection;
    we may want to treat them separately in some cases as they may not have the same constructors -
    an example is pandas.DataFrame"""

    pass


class NamedTupleABCMeta(_InstanceCheckFromSubclassCheck):
    def __subclasscheck__(self, subclass):
        return is_named_tuple_class(subclass)


class NamedTupleABC(tuple, metaclass=NamedTupleABCMeta):
    pass


# for use in creating custom metaclasses that behave like typing.Generic with __getitem__, but without having to deal
# with the intricacies of the typing module


class PseudoGenericMeta(type):
    __origin__ = None
    __args__ = None

    def __getitem__(self, item):
        raise NotImplementedError(
            "Subclasses of PseudoGenericMeta must implement __getitem__"
        )
