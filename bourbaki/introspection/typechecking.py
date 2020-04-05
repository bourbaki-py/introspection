# coding:utf-8
import typing
from inspect import signature, Parameter
import operator
from functools import partial, lru_cache
from warnings import warn
from .builtin_signatures import builtin_callable_types
from .utils import name_of
from .imports import import_type
from .types import (
    LazyType,
    is_top_type,
    to_concrete_type,
    constraint_type,
    issubclass_generic,
    reconstruct_generic,
    deconstruct_generic,
    get_generic_args,
    typetypes,
    base_newtype_of,
    concretize_typevars,
)
from .generic_dispatch import GenericTypeLevelSingleDispatch, const
from .generic_dispatch_helpers import (
    UnionWrapper,
    TupleWrapper,
    CollectionWrapper,
    MappingWrapper,
    LazyWrapper,
    PicklableWithType,
)


type_checker = GenericTypeLevelSingleDispatch(
    "type_checker", isolated_bases=[typing.Union, typing.Generic]
)


@lru_cache(None)
def type_checker_for(type_):
    return type_checker(base_newtype_of(type_))


def isinstance_generic(obj, type_):
    return type_checker_for(type_)(obj)


def _isinstance(type_, obj):
    return isinstance(obj, type_)


class _GenericTypeCheckerMixin:
    getter = type_checker


class _GenericContainerTypeCheckerMixin(_GenericTypeCheckerMixin):
    reduce = all
    helper_cls = CollectionWrapper
    generic_type = object

    def __new__(cls, org, *args):
        if not args:
            return isinstance_of(org)

        new = object.__new__(cls)
        cls.__init__(new, org, *args)
        return new

    def __call__(self, value):
        return isinstance(value, self.generic_type) and self.helper_cls.__call__(
            self, value
        )


class _GenericUnionTypeCheckerMixin(_GenericTypeCheckerMixin):
    reduce = any


@type_checker.register_all(typing.Any, str, typing.ByteString)
def isinstance_of(type_, *args):
    if args:
        # generic that hasn't been explicitly registered
        warn(
            "got type args {a} for unregistered type {t}; can only check that a value is an instance of {t}. "
            "To perform a more specific check, decorate a function with "
            "introspection.typechecking.type_checker.register({t}), to accept positional args for {t} and the type "
            "variables of {t}, and return a callable taking a value and returning a bool".format(
                t=type_, a=args
            )
        )
    if is_top_type(type_):
        return const(True)
    type_ = to_concrete_type(type_)
    return partial(_isinstance, type_)


@type_checker.register(typing.Callable)
class CallableTypeChecker:
    def __init__(self, callable_, signature_=..., return_=object):
        self.callable_ = callable_
        self.signature_ = signature_
        self.return_ = return_

    def __call__(self, func):
        if not isinstance(func, self.callable_):
            return False

        return_, signature_, empty = self.return_, self.signature_, Parameter.empty

        if (is_top_type(return_) or return_ is empty) and signature_ is Ellipsis:
            # anything will do; don't trouble with the signature
            return True

        try:
            runtime_type = builtin_callable_types.get(func)
        except TypeError:
            # unhashable
            runtime_type = None

        if runtime_type is None:
            try:
                runtime_type = func.__orig_class__
            except AttributeError:
                try:
                    sig = signature(func)
                except ValueError:
                    warn(
                        "Can't check that {} is {}; call to inspect.signature() failed - most likely an extension or builtin; "
                        "returning True".format(
                            func,
                            "{}[{}, {}]".format(
                                name_of(self.callable_), signature_, return_
                            ),
                        )
                    )
                    return True

                if isinstance(func, type) and sig.return_annotation is empty:
                    # types generally return instances of themselves on calling
                    sig = sig.replace(return_annotation=func)

                if signature_ is Ellipsis:
                    # our signature is unspecified so we don't care about this signature, only the return types
                    # give the benefit of the doubt if the return wasn't annotated
                    if sig.return_annotation is empty:
                        return True
                    else:
                        return issubclass_generic(sig.return_annotation, return_)

                this_sig = []
                freeze = False
                for p in sig.parameters.values():
                    if freeze:
                        # no required args past the ones specified
                        if p.default is empty and p.kind not in (
                            Parameter.VAR_POSITIONAL,
                            Parameter.VAR_KEYWORD,
                        ):
                            return False
                    else:
                        t = object if p.annotation is empty else p.annotation
                        if p.kind in (
                            Parameter.POSITIONAL_ONLY,
                            Parameter.POSITIONAL_OR_KEYWORD,
                        ):
                            this_sig.append(t)
                        elif p.kind is Parameter.VAR_POSITIONAL:
                            this_sig.extend([t] * (len(signature_) - len(this_sig)))
                        else:
                            break
                        freeze = len(this_sig) == len(signature_)

                this_return = sig.return_annotation
                if this_return is empty:
                    this_return = object

                runtime_type = (typing.Callable, *this_sig, this_return)

        test_type = (self.callable_, *signature_, return_)
        if isinstance(runtime_type, list):
            # builtin signatures - can't use Union
            return any(
                issubclass_generic(concretize_typevars(t), test_type)
                for t in runtime_type
            )
        else:
            return issubclass_generic(concretize_typevars(runtime_type), test_type)

    @property
    def n_args(self):
        return None if self.signature_ is Ellipsis else len(self.signature_)

    def __getstate__(self):
        state = self.__dict__.copy()
        state["return_"] = deconstruct_generic(state["return_"])
        sig = state["signature_"]
        state["signature_"] = (
            list(map(deconstruct_generic, sig))
            if isinstance(sig, (list, tuple))
            else deconstruct_generic(sig)
        )

    def __setstate__(self, state):
        state["return_"] = reconstruct_generic(state["return_"])
        sig = state["signature_"]
        state["signature_"] = (
            list(map(reconstruct_generic, sig))
            if isinstance(sig, (list, tuple))
            else reconstruct_generic(sig)
        )
        self.__dict__.update(state)


@type_checker.register(typing.Generic)
class GenericTypeChecker(PicklableWithType):
    def __init__(self, type_, *args):
        self.origin = type_
        super().__init__(type_, *args)

    def __call__(self, value):
        try:
            value_cls = value.__orig_class__
        except AttributeError:
            value_cls = type(value)
            this_cls = self.origin
        else:
            this_cls = self.type_

        return issubclass_generic(value_cls, this_cls)


@type_checker.register(typing.Type)
class TypeTypeChecker:
    def __init__(self, type_type, tvar=None):
        self.type_type = type_type
        if tvar is None:
            self.bound = object
        elif isinstance(tvar, typing.TypeVar):
            self.bound = constraint_type(tvar)
        else:
            # literal type
            self.bound = tvar

    def __call__(self, arg):
        bound = self.bound
        if issubclass_generic(bound, LazyType):
            ref = get_generic_args(bound)[0]
            bound = import_type(ref)
        return isinstance(arg, (type, *typetypes)) and issubclass_generic(arg, bound)

    def __getstate__(self):
        state = self.__dict__.copy()
        state["bound"] = deconstruct_generic(state.pop("bound"))

    def __setstate__(self, state):
        state["bound"] = reconstruct_generic(state.pop("bound"))
        self.__dict__.update(state)


@type_checker.register(typing.Collection)
class CollectionTypeChecker(_GenericContainerTypeCheckerMixin, CollectionWrapper):
    helper_cls = CollectionWrapper


@type_checker.register(typing.Mapping)
class MappingTypeChecker(_GenericContainerTypeCheckerMixin, MappingWrapper):
    helper_cls = MappingWrapper
    keyval_op = staticmethod(operator.and_)


@type_checker.register(typing.Tuple)
class TupleTypeChecker(_GenericContainerTypeCheckerMixin, TupleWrapper):
    _collection_cls = CollectionTypeChecker
    require_same_len = False
    helper_cls = TupleWrapper

    def __new__(cls, tup_type, *args):
        if not args:
            return isinstance_of(tup_type)
        return TupleWrapper.__new__(cls, tup_type, *args)

    def __call__(self, value):
        try:
            len_ = len(value)
        except TypeError:
            return super().__call__(value)
        else:
            return len(self.funcs) == len_ and super().__call__(value)


@type_checker.register(typing.Union)
class UnionTypeChecker(_GenericUnionTypeCheckerMixin, UnionWrapper):
    pass


@type_checker.register(LazyType)
class LazyTypeChecker(_GenericTypeCheckerMixin, LazyWrapper):
    pass


class _TypeAliasTypeChecker:
    type_ = None
    arg = None
    attr = None

    def get_value_for_arg(self, obj):
        return getattr(obj, self.attr, None)

    def __new__(cls, type_, *args):
        if not args:
            return isinstance_of(type_)

        new = object.__new__(cls)
        cls.__init__(new, type_, *args)
        return new

    def __init__(self, type_, arg=object):
        self.type_ = to_concrete_type(type_)
        self.arg = arg

    def __call__(self, obj):
        return isinstance(obj, self.type_) and isinstance(
            self.get_value_for_arg(obj), self.arg
        )


@type_checker.register(typing.Pattern)
class PatternTypeChecker(_TypeAliasTypeChecker):
    attr = "pattern"


@type_checker.register(typing.Match)
class MatchTypeChecker(_TypeAliasTypeChecker):
    attr = "string"
