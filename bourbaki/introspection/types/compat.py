# coding:utf-8
from typing import Tuple, Union, Callable, Any, TypeVar
import typing
import re
import sys
import collections
from itertools import combinations
from functools import singledispatch
import typing_inspect
from typing_inspect import (
    is_callable_type,
    get_origin,
    get_parameters,
    get_generic_bases as _get_generic_bases,
)
from ..utils import identity
from ..debug import trace

NON_TYPING_STDLIB_MODULES = frozenset(
    (
        "builtins",
        "collections",
        "datetime",
        "time",
        "ipadress",
        "pathlib",
        "urllib",
        "uuid",
        "numbers",
        "decimal",
        "fractions",
        "re",
        "_sre",
        "os",
        "enum",
    )
)

ForwardRef = None
_GenericAlias = None

if sys.version_info[:2] >= (3, 7):  # pragma: no cover
    from typing import ForwardRef, _GenericAlias

    EVALUATE_DEFAULT = True
    TYPE_ALIASES = False
    NEW_TYPING = True

    class _TypeAlias:
        name = None
        impl_type = None
        type_var = None

    typing_bases = None

    get_concrete_origin = get_origin

    _tvars = (TypeVar("A"), TypeVar("B"), TypeVar("C"), TypeVar("D"))
    _tvars_for_base = {
        typing.Counter: (_tvars[0], int),
        typing.ByteString: (Union[int, bytes, bytearray],),
    }

    if sys.version_info >= (3, 8):
        abstract_types = (typing.Protocol, typing.Generic)
    else:
        abstract_types = (typing._Protocol, typing.Generic)
    generics = {
        t
        for t in vars(typing).values()
        if t not in abstract_types
        and isinstance(t, typing._GenericAlias)
        and get_parameters(t)
    }
    generics.add(Callable)

    def _parameterize(t, params=_tvars):
        ps = get_parameters(t)
        if ps:
            return t[params[: len(ps)]]
        return t

    def _set_typing_bases():
        global typing_bases

        typing_bases = collections.defaultdict(set)

        for u, t in combinations(generics, 2):
            for a, b in [(u, t), (t, u)]:
                try:
                    if issubclass(a, b):
                        ps = _tvars_for_base.get(a, _tvars)
                        b = _parameterize(b, ps)
                        typing_bases[a].add(b)
                except TypeError:
                    pass

        def remove_non_bases(types: set):
            for t1, t2 in combinations(list(types), 2):
                org1, org2 = get_origin(t1), get_origin(t2)
                if (org2 is None) or issubclass(org1, org2) and t2 in types:
                    types.remove(t2)
                elif (org1 is None) or issubclass(org2, org1) and t1 in types:
                    types.remove(t1)
            return tuple(types)

        typing_bases = {k: remove_non_bases(v) for k, v in typing_bases.items() if v}

    _set_typing_bases()

    def get_generic_bases(t):
        if t.__module__ == "typing":
            t = get_generic_origin(t)
            return typing_bases.get(t, ())
        return _get_generic_bases(t) or ()


else:  # pragma: no cover
    from typing import _ForwardRef as ForwardRef
    from typing import _TypeAlias

    _GenericAlias = None
    from typing_inspect import get_generic_bases

    EVALUATE_DEFAULT = False
    TYPE_ALIASES = True
    NEW_TYPING = False

    typing_bases = None
    generics = None
    _parameterize = None

    @singledispatch
    def get_concrete_origin(t):
        org = get_origin(t)
        if not org:
            return None
        return getattr(org, "__extra__", t)

    @get_concrete_origin.register(_TypeAlias)
    def _get_alias_concrete_origin(t):
        return t.impl_type

    def get_generic_bases(t):
        bases = _get_generic_bases(t)
        org = get_generic_origin(t)
        # prevents RecursionError in reparameterized_bases under py3.6
        return tuple(b for b in bases if get_generic_origin(b) is not org)


class CallableSignature(list):
    """hashable list subclass for parameterizing Callable while allowing lru_cache to work
    on various type-level functions"""
    def __hash__(self):
        return hash(tuple(self))


# get the base generic origin of a parameterized generic


@singledispatch
@trace
def get_generic_origin(t):
    org = get_origin(t)
    if org is None:
        return stdlib_type_to_typing_alias.get(t, t)
    return origin_to_typing_alias.get(org, org)


@get_generic_origin.register(tuple)
def _get_generic_origin(tup):
    return get_generic_origin(tup[0])


@get_generic_origin.register(CallableSignature)
def _get_generic_origin_sig(sig):
    return None


@get_generic_origin.register(_TypeAlias)
def _get_alias_origin(
    alias
):  # pragma: no cover (python3.6 only, works if tests pass - they include Pattern)
    return getattr(typing, alias.name)


# get concrete args from a generic

# we have to monkey-patch this for now due to a bug in typing_inspect

def _eval_args(args):
    """Internal helper for get_args."""
    res = []
    for arg in args:
        if not isinstance(arg, tuple):
            res.append(arg)
        elif is_callable_type(arg[0]):
            callable_args = _eval_args(arg[1:])
            if len(arg) == 2:
                res.append(Callable[[], callable_args[0]])
            elif arg[1] is Ellipsis:
                res.append(Callable[..., callable_args[1]])
            else:
                res.append(Callable[[*callable_args[:-1]], callable_args[-1]])
        else:
            res.append(type(arg[0]).__getitem__(arg[0], _eval_args(arg[1:])))
    return tuple(res)


typing_inspect._eval_args = _eval_args


# get typevars from a generic


@singledispatch
@trace
def get_generic_params(t):
    return get_parameters(t) or ()


@get_generic_params.register(tuple)
def _get_generic_params(tup):
    return get_generic_params(tup[0]) if tup else ()


@get_generic_params.register(CallableSignature)
def _get_generic_params_sig(sig):
    return ()


@get_generic_params.register(_TypeAlias)
def _get_alias_params(alias):  # pragma: no cover (python3.6 only, works if tests pass)
    param = alias.type_var
    if isinstance(param, TypeVar):
        return (param,)
    return ()


# get original bases (i.e. those that appeared in the source code `class ClassName(*original_bases): ...`


@singledispatch
@trace
def get_original_bases(t):
    bases = getattr(t, "__orig_bases__", ())
    if not bases:
        bases = getattr(get_generic_origin(t), "__orig_bases__", ())
    return tuple(t for t in bases if get_generic_origin(t) is not typing.Generic)


@get_original_bases.register(tuple)
def _get_original_bases(t):
    # TODO: is this correct on both py3.6 and py3.7?
    return get_original_bases(t[0])


# get a concrete type (i.e. one that can be called as a constructor) from a generic alias


def to_concrete_type(t):
    return typing_alias_to_stdlib_type.get(t, t)


# get a type alias from a (possibly) instantiable stdlib type (inverse of the above)


def to_type_alias(t):
    return stdlib_type_to_typing_alias.get(t, t)


# for mapping abstract types to concrete constructors


def get_constructor_for(type_):
    return typing_to_stdlib_constructor.get(type_, type_)


# global mappings between type aliases and concrete types/constructors

origin_to_typing_alias = {}
stdlib_type_to_typing_alias = {}
typing_alias_to_stdlib_type = {}
typing_to_stdlib_constructor = {}
typetypes = (
    type(Union),
    type(Tuple),
    type(Callable),
    type(typing.Mapping),
    type(typing.Pattern),
    _TypeAlias,
)


def _set_origin_to_typing_alias():
    global origin_to_typing_alias
    for t in vars(typing).values():
        if not isinstance(t, typetypes):
            continue
        try:
            org = get_origin(t)
        except TypeError:
            pass
        else:
            if org is not None and org is not t:
                origin_to_typing_alias[org] = t


def _set_stdlib_type_to_typing_alias():
    global stdlib_type_to_typing_alias
    for t in vars(typing).values():
        if not isinstance(t, typetypes):
            continue
        org = get_concrete_origin(t)
        if org:
            stdlib_type_to_typing_alias[org] = t
            typing_alias_to_stdlib_type[t] = org
    stdlib_type_to_typing_alias[object] = Any
    typing_alias_to_stdlib_type[Any] = object


def _set_typing_to_stdlib_constructor():
    global typing_to_stdlib_constructor
    typing_to_stdlib_constructor.update(
        {
            typing.Iterable: list,
            typing.Container: list,
            typing.Sequence: list,
            typing.MutableSequence: list,
            typing.Collection: list,
            typing.List: list,
            typing.Tuple: tuple,
            typing.AbstractSet: set,
            typing.Set: set,
            typing.MutableSet: set,
            typing.FrozenSet: frozenset,
            typing.Mapping: dict,
            typing.MutableMapping: dict,
            typing.Dict: dict,
            typing.Counter: collections.Counter,
            typing.ChainMap: collections.ChainMap,
            typing.Deque: collections.deque,
            typing.ByteString: bytes,
        }
    )
    for tname, type_ in [
        ("OrderedDict", collections.OrderedDict),
        ("_Pattern", re.compile),
        ("Pattern", re.compile),
        ("TypedDict", dict),
        ("Literal", identity),
    ]:
        t = getattr(typing, tname, None)
        if t is not None:
            typing_to_stdlib_constructor[t] = type_


_set_origin_to_typing_alias()
_set_stdlib_type_to_typing_alias()
_set_typing_to_stdlib_constructor()
