# coding: utf-8
from typing import List, Generic, Tuple, TypeVar, Union
import typing
import sys
from functools import lru_cache
from inspect import getmro, signature, Signature, Parameter
from itertools import repeat, islice
import types
from .inspection import (
    is_tuple_origin,
    is_top_type,
    is_callable_origin,
    is_newtype,
    base_newtype_of,
    newtype_chain,
    get_generic_args,
    generic_metadata,
    normalized_origin_args,
    is_named_tuple_class,
)
from .compat import (
    get_generic_origin,
    get_generic_params,
    to_concrete_type,
    EVALUATE_DEFAULT,
)
from .evaluation import concretize_typevars, reparameterize_generic
from ..debug import trace

T_co = TypeVar("T_co", covariant=True)


@trace
def reparameterized_bases(
    t, recurse=True, evaluate=EVALUATE_DEFAULT, concretize=False, memo=None
):
    org, bases, params, args = generic_metadata(t, evaluate=evaluate)
    if memo is None:
        memo = set()

    if concretize and args:
        args = tuple(map(concretize_typevars, args))

    if args:
        if is_tuple_origin(org):
            if args:
                if args[-1] is Ellipsis or len(args) == 1:
                    arg = args[0]
                else:
                    arg = (Union, *args)
                base = (typing.Sequence, arg)
            else:
                base = typing.Sequence

            if base not in memo:
                memo.add(base)
                yield base
            yield from reparameterized_bases(
                base,
                recurse=recurse,
                evaluate=evaluate,
                concretize=concretize,
                memo=memo,
            )
        else:
            tvar_map = dict(zip(params, args))
            for base in bases:
                new_base = reparameterize_generic(base, tvar_map, evaluate=evaluate)
                if new_base in memo:
                    continue
                memo.add(new_base)
                yield new_base
                if recurse:
                    yield from reparameterized_bases(
                        new_base, recurse=recurse, evaluate=evaluate, memo=memo
                    )
    else:
        # no args but there may be generic bases!
        if concretize:
            bases = map(concretize_typevars, bases)
        for base in bases:
            memo.add(base)
            yield base
            yield from reparameterized_bases(
                base, recurse=recurse, evaluate=evaluate, concretize=True, memo=memo
            )


@lru_cache(None)
@trace
def issubclass_generic(t1: Union[type, tuple], t2: Union[type, tuple]) -> bool:
    if is_newtype(t1):
        if is_newtype(t2):
            return _issubclass_newtype_newtype(t1, t2)
        return issubclass_generic(base_newtype_of(t1), t2)
    elif is_newtype(t2):
        return False

    org1, org2 = get_generic_origin(t1), get_generic_origin(t2)

    if org1 is Union:
        args1 = get_generic_args(t1)
        if not args1:
            return is_top_type(org2)
        elif org2 is Union:
            args2 = get_generic_args(t2)
            if not args2:
                # Union[type, ...] is a Union
                return True
            return _issubclass_union_union(args1, args2)
        else:
            return _issubclass_union_any(args1, t2)

    if org2 is Union:
        args2 = get_generic_args(t2)
        if is_top_type(org1):
            # any type is a Union of itself, but we enforce Union <: Any to keep a DAG structure on all types
            return False
        return _issubclass_any_union(t1, args2)

    args2 = get_generic_args(t2)
    if args2:
        # The hard case; type parameter variance must be considered
        return issubclass_parameterized(t1, t2)
    else:
        # no args at all; the easy case
        return _issubclass(org1, org2)


def _issubclass_newtype_newtype(t1, t2) -> bool:
    return t2 in newtype_chain(t1)


@trace
def issubclass_parameterized(t1: Union[type, tuple], t2: Union[type, tuple]) -> bool:
    org1, args1, fixlen1 = normalized_origin_args(t1, extract_namedtuple_args=True)
    org2, args2, fixlen2 = normalized_origin_args(t2, extract_namedtuple_args=True)

    if is_tuple_origin(org1) or is_named_tuple_class(org1):
        if fixlen1:
            # fixed-length tuples can be subclasses of sequence/iterable types if all types match
            if fixlen2:
                return _issubclass_fixlen_fixlen(org1, args1, org2, args2)
            return _issubclass_fixlen_any(org1, args1, org2, args2)
        elif fixlen2:
            # but not the other way around
            return False

    if is_callable_origin(org2):
        if not is_callable_origin(org1):
            return _issubclass_generic_callable(org1, args1, org2, args2)
        if args2 and not args1:
            return False
        return _issubclass_callable_callable(args1, args2)
    else:
        return _issubclass_parameterized_general(org1, args1, org2, args2)


def _is_generic(t):
    try:
        mro = getmro(t)
    except AttributeError:
        return False
    # might be a little faster to check from the right end since generic will usually be near the top of the hierarchy
    return Generic in reversed(mro)


@lru_cache(None)
@trace
def _issubclass(t1, t2):
    # concrete types; handles Any
    t2 = to_concrete_type(t2)
    if t2 is Generic:
        return _is_generic(t1)
    try:
        return issubclass(to_concrete_type(t1), t2)
    except Exception as e:
        if is_newtype(t1):
            if is_newtype(t2):
                return _issubclass_newtype_newtype(t1, t2)
            return issubclass_generic(base_newtype_of(t1), t2)
        elif is_newtype(t2):
            return False
        else:
            print("_issubclass({}, {}) -> {}".format(t1, t2, e), file=sys.stderr)
            raise e


def _issubclass_union_any(types, t):
    return all(issubclass_generic(t1, t) for t1 in types)


def _issubclass_any_union(t, types):
    return any(issubclass_generic(t, t2) for t2 in types)


def _issubclass_union_union(types1, types2):
    return all(any(issubclass_generic(t1, t2_) for t2_ in types2) for t1 in types1)


def _issubclass_fixlen_fixlen(org1, args1, org2, args2):
    return (
        len(args1) == len(args2)
        and _issubclass(org1, org2)
        and all(issubclass_generic(t1_, t2_) for t1_, t2_ in zip(args1, args2))
    )


def _issubclass_fixlen_any(org1, args1, org2, args2):
    return (
        _issubclass(org1, org2)
        and len(args2) == 1
        and all(
            issubclass_generic(t1_, t2_) for t1_, t2_ in zip(args1, repeat(args2[0]))
        )
    )


@trace
def _issubclass_parameterized_general(org1, args1, org2, args2):
    if org1 is org2:
        if args2 and not args1:
            return False
        # top type defines the variance relation
        params = (T_co,) if org2 is Tuple else get_generic_params(org2)
        return all(
            _issubclass_with_variance(t1, t2, p)
            for t1, t2, p in zip(args1, args2, params)
        )

    ttup1, ttup2 = (org1, *args1), (org2, *args2)
    return _issubclass(org1, org2) and any(
        issubclass_generic(base, ttup2)
        for base in reparameterized_bases(ttup1, concretize=True)
    )


@trace
def _issubclass_with_variance(t1, t2, param: TypeVar):
    if param.__covariant__:
        return issubclass_generic(t1, t2)
    if param.__contravariant__:
        return issubclass_generic(t2, t1)
    return t1 == t2


def _issubclass_generic_callable(org1, generic_args1, org2, args2):
    # org1 must be a callable class
    if not issubclass_generic(org1, org2):
        return False

    # args1 from signature of __call__
    sig = signature(types.MethodType(org1.__call__, org1))
    sig_args2 = args2[0]
    if sig_args2 is not Ellipsis:
        sig_params1 = [
            # take one more than the number of args in input_args2 in case there is an extra required arg
            p
            for name, p in islice(sig.parameters.items(), len(sig_args2) + 1)
            if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
        ]

        if len(sig_params1) < len(sig_args2):
            return False
        elif len(sig_params1) > len(sig_args2):
            if sig_params1[len(sig_args2)].default is Parameter.empty:
                # extra required arg; not compatible
                return False
            sig_params1 = sig_params1[: len(sig_args2)]
        # now input_params1 has the same length as input_args2
        # bind generic params into signature types
        tparams = get_generic_params(org1)
        tparam_dict = dict(zip(tparams, generic_args1))
        args1 = (
            [
                reparameterize_generic(arg.annotation, tparam_dict)
                for arg in sig_params1
            ],
            reparameterize_generic(sig.return_annotation, tparam_dict),
        )
    else:
        # only return types matter
        tparams = get_generic_params(org1)
        tparam_dict = dict(zip(tparams, generic_args1))
        args1 = (Ellipsis, reparameterize_generic(sig.return_annotation, tparam_dict))
    return _issubclass_callable_callable(args1, args2)


def _issubclass_callable_callable(args1, args2):
    sig1, ret1 = args1
    sig2, ret2 = args2

    if sig1 is Ellipsis and sig2 is not Ellipsis:
        # T1 <: T2 => ((*args) -> T1) <: ((arg1, arg2) -> T2)
        return issubclass_generic(ret1, ret2)
    elif sig2 is Ellipsis:
        # ... could mean any number of args of any type (so Any for typecheck purposes),
        # which by variance rules would mean the only subtype possible is again Callable[..., R] where R <: ret2
        # but we treat it as meaning any number of args of _unspecified_ type, which allows specifying a callable
        # type only by what it returns
        return issubclass_generic(ret1, ret2)
    if len(sig1) != len(sig2):
        return False
    # contravariant in arguments
    return issubclass_generic(ret1, ret2) and all(
        issubclass_generic(t2, t1) for (t2, t1) in zip(sig2, sig1)
    )


def comparable_signature_args(
    sig: Signature, sig_args2: Tuple[List[typing.Type], typing.Type]
):
    sig_params1 = [
        # take one more than the number of args in input_args2 in case there is an extra required arg
        p
        for name, p in islice(sig.parameters.items(), len(sig_args2) + 1)
        if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
    ]

    if len(sig_params1) < len(sig_args2):
        return False
    elif len(sig_params1) > len(sig_args2):
        if sig_params1[len(sig_args2)].default is Parameter.empty:
            # extra required arg; not compatible
            return False
        sig_params1 = sig_params1[: len(sig_args2)]
    # now input_params1 has the same length as input_args2
    # bind generic params into signature types
    tparams = get_generic_params(org1)
    tparam_dict = dict(zip(tparams, sig_args1))
    args1 = (
        [reparameterize_generic(arg.annotation, tparam_dict) for arg in sig_params1],
        reparameterize_generic(sig.return_annotation, tparam_dict),
    )
