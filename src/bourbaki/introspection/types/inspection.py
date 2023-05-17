# coding: utf-8
from typing import TypeVar, Generic
import typing
from functools import singledispatch, lru_cache
from collections import abc as collections_abc
from typing_inspect import get_args
from .compat import (
    get_generic_origin,
    get_generic_params,
    get_generic_bases,
    typing_bases,
    generics,
    _parameterize,
)
from .compat import (
    _TypeAlias,
    CallableSignature,
    EVALUATE_DEFAULT,
    NON_TYPING_STDLIB_MODULES,
    NEW_TYPING,
)
from ..debug import trace

# Note: ideally, get_generic_args would be defined in compat, but we define it here because it requires access to
# is_newtype, which made sense to define here


def is_top_type(t):
    return t in (typing.Any, object)


def is_callable_origin(t):
    return t in (typing.Callable, collections_abc.Callable)


def is_tuple_origin(t):
    return t in (typing.Tuple, tuple)


@singledispatch
def is_concrete_type(t):
    args = get_generic_args(t, evaluate=EVALUATE_DEFAULT)
    return all(map(is_concrete_type, args))


@is_concrete_type.register(typing.TypeVar)
def _is_concrete_typevar(t):
    return False


def is_newtype(t):
    return (
        callable(t)
        and hasattr(t, "__supertype__")
        and getattr(t, "__module__", None) == "typing"
    )


def base_newtype_of(t):
    if is_newtype(t):
        return base_newtype_of(t.__supertype__)
    return t


def newtype_chain(t):
    sentinel = object()
    next_ = t
    while next_ is not sentinel:
        yield next_
        next_ = getattr(next_, "__supertype__", sentinel)


@lru_cache(None)
def is_named_tuple_class(cls: type):
    try:
        mro = cls.mro()
    except (AttributeError, TypeError):
        pass
    else:
        if len(mro) > 2:
            base_nt_cls = mro[-3]
            # custom subclass with overridden initialization
            if (
                cls.__new__ is not base_nt_cls.__new__
                or cls.__init__ is not base_nt_cls.__init__
            ):
                return False

    return (
        isinstance(cls, type)
        and issubclass(cls, tuple)
        and all(hasattr(cls, a) for a in ("_asdict", "_replace", "_fields"))
    )


def get_named_tuple_arg_types(cls: type):
    return tuple(cls.__annotations__.values())


@singledispatch
@trace
def get_generic_args(t, evaluate=EVALUATE_DEFAULT):
    if is_newtype(t):
        return get_generic_args(base_newtype_of(t))
    if NEW_TYPING and (t in typing_bases or t in generics):
        return ()
    return get_args(t, evaluate=evaluate) or ()


# Note: the tuple case is registered in evaluation.py to avoid a circular import (requires eval_type_tree)


@get_generic_args.register(CallableSignature)
def _get_generic_args_sig(sig, evaluate=EVALUATE_DEFAULT):
    return ()


@get_generic_args.register(_TypeAlias)
def _get_alias_args(
    alias, evaluate=EVALUATE_DEFAULT
):  # pragma: no cover (python3.6 only, works if tests pass)
    arg = alias.type_var
    if isinstance(arg, TypeVar):
        return ()
    return (arg,)


# tie all of the attibute-getters together: origin, args, parameters, and bases


@trace
def generic_metadata(t: type, evaluate=EVALUATE_DEFAULT):
    org = get_generic_origin(t)
    args = get_generic_args(t, evaluate=evaluate)
    bases = tuple(
        base
        for base in get_generic_bases(org)
        if get_generic_origin(base) is not Generic
    )
    if args and NEW_TYPING and getattr(org, "__module__", None) == "typing":
        org = _parameterize(org)
        params = get_generic_params(org)
    else:
        params = get_generic_params(org)
    return org, bases, params, args


# get origin, args, and boolean indicating a fixed-length tuple/signature or not where appropriate, in one call


def normalized_origin_args(
    t,
    evaluate=EVALUATE_DEFAULT,
    remove_tuple_ellipsis=True,
    extract_namedtuple_args=False,
):
    if getattr(t, "__module__", None) in NON_TYPING_STDLIB_MODULES:
        return get_generic_origin(t), (), False

    org, args, fixlen = (
        get_generic_origin(t),
        get_generic_args(t, evaluate=evaluate),
        False,
    )

    if is_tuple_origin(org) and args:
        fixlen = args[-1] is not Ellipsis
        if remove_tuple_ellipsis and not fixlen:
            args = args[:-1]
    elif is_callable_origin(org) and args and args[0] is not Ellipsis:
        # should return 2 args: signature and return
        if evaluate:
            # 2 args, first is a list
            sig, ret = args[0], args[1]
        else:
            # 1 or more args, last is return, leading are signature
            sig, ret = args[:-1], args[-1]
        args = CallableSignature(sig), ret
        fixlen = True
    elif is_named_tuple_class(org):
        if extract_namedtuple_args:
            args = get_named_tuple_arg_types(org)
        fixlen = True

    return org, args, fixlen
