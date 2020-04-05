# coding:utf-8
from typing import Dict, TypeVar, Union, Type, Optional, Mapping, Any, NewType
from collections import OrderedDict
from functools import singledispatch, lru_cache
from itertools import repeat
from typing_inspect import get_constraints, get_bound
from .compat import get_generic_origin, get_generic_params, EVALUATE_DEFAULT
from .compat import ForwardRef, CallableSignature
from .abcs import LazyType, PseudoGenericMeta
from ..debug import trace
from .inspection import (
    is_callable_origin,
    is_top_type,
    is_newtype,
    get_generic_args,
    normalized_origin_args,
    is_named_tuple_class,
)

_newtype_cache = {}


@get_generic_args.register(tuple)
def _get_generic_args(tup, evaluate=EVALUATE_DEFAULT):
    """destructured tuple representation of a type, (origin, *args)"""
    if not evaluate:
        return tup[1:]
    args = tuple(map(eval_type_tree, tup[1:]))
    if evaluate and is_callable_origin(tup[0]) and args[0] is not Ellipsis:
        args = list(args[:-1]), args[-1]
    return args


# main helper - evaluates forward refs, substitutes concrete constraint types or specified type args for type vars

def fully_concretize_type(
    t: Type,
    param_dict: Optional[Mapping[Any, Type]],
    globals_: Optional[Mapping[str, Any]],
):
    return concretize_typevars(
        reparameterize_generic(eval_forward_refs(t, globals_), param_dict)
    )


# fetch module namespace in which to evaluate a forwardref

def get_globals(t: Type) -> Optional[Dict[str, Any]]:
    try:
        mod = __import__(t.__module__)
    except (AttributeError, ImportError):
        return None
    else:
        return getattr(mod, "__dict__", None)


# materialize delayed string references (forward refs) in type annotations

def eval_forward_refs(t, globals_, dont_recurse=()):
    if t in dont_recurse:
        return t

    if isinstance(t, ForwardRef):
        return eval(t.__forward_arg__, globals_)
    elif isinstance(t, str):
        return eval(t, globals_)
    elif globals_ is None:
        globals_ = get_globals(t)

    org, args, fixlen = normalized_origin_args(
        t, remove_tuple_ellipsis=False, extract_namedtuple_args=True
    )

    if not args:
        return org

    if org is LazyType:
        # this may have ForwardRef args; don't recurse
        return t
    elif is_callable_origin(org):
        sig, ret = args
        if fixlen:
            sig = [eval_forward_refs(s, globals_, (t, *dont_recurse)) for s in sig]
        args = sig, eval_forward_refs(ret, globals_)
    else:
        args = tuple(eval_forward_refs(a, globals_, (t, *dont_recurse)) for a in args)

    if is_named_tuple_class(org):
        typedict = getattr(org, "__annotations__", getattr(org, "_field_types", None))
        if not typedict:
            return t
        typedict.update(zip(org._fields, args))
        return org

    if len(args) == 1:
        args = args[0]

    return org[args]


# turn a (generic, *args) tuple into a fully evaluated generic type

@singledispatch
def eval_type_tree(t):
    # literal type
    return t


@eval_type_tree.register(tuple)
def _eval_type_tree(tup):
    t, args = tup[0], tup[1:]
    if not args:
        return t
    if t is NewType:
        return _cached_newtype(*tup)
    if is_newtype(t):
        return t
    if is_named_tuple_class(t):
        return t
    if is_callable_origin(t):
        args = _eval_callable_args(args)
    else:
        if len(args) == 1:
            # don't [getitem] on a single-value tuple
            args = eval_type_tree(args[0])
        else:
            args = tuple(map(eval_type_tree, args))
    return get_generic_origin(t)[args]


@eval_type_tree.register(CallableSignature)
def _eval_type_tree_signature(sig):
    return list(map(eval_type_tree, sig))


@lru_cache(None)
def _cached_newtype(newtype, name, type_, id_):
    # id_ is here only to ensure distinctness of otherwise-identically-defined NewTypes, via the lru cache
    # in case we're reconstructing a type that was deconstructed in the same runtime, we check the _newtype_cache first
    return _newtype_cache.get(id_, newtype(name, reconstruct_generic(type_)))


def _eval_callable_args(args):
    if len(args) == 1:
        return [], eval_type_tree(args[0])
    elif args[0] is Ellipsis:
        return ..., eval_type_tree(args[1])
    else:
        if isinstance(args[0], (list, CallableSignature)):
            sig = args[0]
        else:
            sig = args[:-1]
        return list(map(eval_type_tree, sig)), eval_type_tree(args[-1])


def eval_args(tup):
    return tuple(map(eval_type_tree, tup))


# turn a generic type whose type tree may contain type variables into a concrete type by substituting appropriate
# most-general types for type variables

def constraint_type(tvar: TypeVar):
    ts = get_constraints(tvar)
    if ts:
        return Union[ts]
    else:
        bound = get_bound(tvar)
        return object if bound is None else bound


@lru_cache(None)
def new_namedtuple_subclass(org, args):
    if args:
        annotations = OrderedDict(zip(org._fields, args))
        ns = {"__annotations__": annotations, "_field_types": annotations}
    else:
        ns = {}
    return type(org.__name__, (org,), ns)


@singledispatch
def concretize_typevars(t: Type, dont_recurse=()):
    if t in dont_recurse:
        return t

    org, args, _ = normalized_origin_args(
        t, remove_tuple_ellipsis=False, extract_namedtuple_args=True
    )
    if not args:
        if org is Type:
            return Type[Any]
        args = get_generic_params(t)
        if not args:
            return t
        args_ = tuple(concretize_typevars(t_, (t, *dont_recurse)) for t_ in args)
        if all(map(is_top_type, args_)):
            # don't parameterize with nonspecific parameters
            return t
    else:
        args_ = tuple(concretize_typevars(t_, (t, *dont_recurse)) for t_ in args)

    if is_named_tuple_class(org):
        return new_namedtuple_subclass(org, args_)

    try:
        return org[args_]
    except:
        # newtypes
        return (org, *args_)


@concretize_typevars.register(TypeVar)
def _concretize_typevars_typevar(tvar: TypeVar, dont_recurse=()):
    t = constraint_type(tvar)
    return concretize_typevars(t, dont_recurse)


@concretize_typevars.register(CallableSignature)
def concretize_typevars_signature(sig: CallableSignature, dont_recurse=()):
    return CallableSignature(map(concretize_typevars, sig, repeat(dont_recurse)))


# deconstructed generic type
@concretize_typevars.register(tuple)
def concretize_typevars_signature(type: tuple, dont_recurse=()):
    return (type[0], *map(concretize_typevars, type[1:], repeat(dont_recurse)))


# turn a fully evaluated generic type into a (generic, *args) tuple

@lru_cache(None)
def deconstruct_generic(t):
    if isinstance(t, TypeVar):
        return t
    if isinstance(t, PseudoGenericMeta):
        return (t.__origin__, *t.__args__)
    if is_newtype(t):
        id_ = id(t)
        _newtype_cache[id_] = t
        return NewType, t.__name__, deconstruct_generic(t.__supertype__), id_

    org, args, fixlen = normalized_origin_args(t, remove_tuple_ellipsis=False)
    if not args:
        return org
    if args and is_callable_origin(org):
        sig, ret = args
        if sig is not Ellipsis:
            # we do this to ensure hashability, e.g. for storage in a generic dispatch cache
            sig = CallableSignature(map(deconstruct_generic, sig))
        return org, sig, deconstruct_generic(ret)

    return (org, *map(deconstruct_generic, args))


reconstruct_generic = eval_type_tree


# substitute types for corresponding type vars in a generic type recursively

@trace
def reparameterize_generic(t, tvar_map, evaluate=True):
    if not tvar_map:
        return t
    if isinstance(t, TypeVar):
        return tvar_map.get(t, t)

    base_org, base_args, fixlen = normalized_origin_args(t, remove_tuple_ellipsis=False)

    if is_callable_origin(base_org):
        # if evaluate == True, we get a 2-tuple, else a (*sig_types, return_type) tuple
        sig, ret = base_args if evaluate else (base_args[:-1], base_args[-1])
        if sig is not Ellipsis:
            sig = CallableSignature(
                tvar_map.get(a, reparameterize_generic(a, tvar_map)) for a in sig
            )
        new_args = sig, reparameterize_generic(ret, tvar_map)
    else:
        new_args = tuple(
            tvar_map.get(arg, reparameterize_generic(arg, tvar_map))
            for arg in base_args
        )

    type_tup = (base_org, *new_args)
    return eval_type_tree(type_tup) if evaluate else type_tup


# get mapping from type var to type arg from a parameterized generic

def get_param_dict(t):
    args = get_generic_args(t)
    if not args:
        return None
    params = get_generic_params(get_generic_origin(t))
    return dict(zip(params, args))


def _maybe_singleton(it):
    """unpack single-entry collection to single value"""
    if len(it) == 1:
        return it[0]
    return it
