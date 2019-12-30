# coding:utf-8
from typing import (
    Union,
    Sequence,
    Mapping,
    Dict,
    Set,
    Tuple,
    Callable,
    Iterable,
    Any,
    Optional,
)
from abc import ABCMeta, abstractmethod
from collections import OrderedDict
from collections.abc import Mapping as MappingABC
from functools import lru_cache, singledispatch, update_wrapper
import functools
from inspect import Signature, Parameter, BoundArguments
from itertools import chain
from operator import itemgetter
from types import MappingProxyType
from multipledispatch import dispatch
from typing_inspect import is_generic_type
from .types import get_generic_params, fully_concretize_type
from .classes import most_specific_constructor
from .utils import nice_exc_args, is_prefix, is_suffix, name_of, signature


class CallableABCMeta(ABCMeta):
    def __subclasscheck__(self, subclass):
        return super().__subclasscheck__(subclass) or callable(
            getattr(subclass, "__call__", None)
        )

    def __instancecheck__(self, instance):
        return callable(instance)


class Callable_(metaclass=CallableABCMeta):
    # concrete type required as python3.7 changed typing generics like Callable to non-types;
    # we need this to dispatch on
    @abstractmethod
    def __call__(self, *args, **kwargs):
        pass


class WrapperSignatureError(TypeError):
    pass


class _Wrapper:
    def __init__(self, func):
        self.func = func
        update_wrapper(self, func)


class Starred(_Wrapper):
    def __call__(self, *args, **kwargs):
        return self.func(args, **kwargs)


class UnStarred(_Wrapper):
    def __call__(self, args, **kwargs):
        return self.func(*args, **kwargs)


def _typeof(cls):
    if isinstance(cls, type):
        return cls
    return getattr(cls, "__origin__", cls)


def is_staticmethod(cls, attr):
    cls = _typeof(cls)
    return getattr(object.__new__(cls), attr) is getattr(cls, attr)


def is_classmethod(cls, attr):
    cls = _typeof(cls)
    method = getattr(object.__new__(cls), attr)
    return getattr(method, "__self__", None) is cls


def is_method(cls, attr):
    cls = _typeof(cls)
    inst = object.__new__(cls)
    method = getattr(inst, attr)
    return getattr(method, "__self__", None) is inst


def funcname(f, qualified=False):
    attr = "__qualname__" if qualified else "__name__"
    n = getattr(f, attr, None)
    if n is None:
        w = getattr(f, "__wrapped__", None)
        if w is None:
            raise AttributeError(attr)
        else:
            return funcname(w)
    return n


def function_classpath(f):
    mod = f.__module__
    return (
        f.__qualname__
        if mod == "builtins"
        else "{}.{}".format(mod, funcname(f, qualified=True))
    )


def constructor_signature(t: Union[type, Callable]):
    if is_generic_type(t):
        cons = most_specific_constructor(t)
        return to_bound_method_signature(signature(cons))
    else:
        return signature(t)


@singledispatch
def get_globals(obj) -> Mapping[str, Any]:
    # handles FunctionType, ModuleType
    g = getattr(obj, "__globals__", None)
    if g is None:
        return get_globals_wrapped(obj)
    return g


def get_globals_wrapped(obj):
    w = getattr(obj, "__wrapped__", None)
    if w is None:
        return None
    return get_globals(w)


@get_globals.register(type)
def get_globals_type(t: type):
    return get_globals(most_specific_constructor(t))


@get_globals.register(functools.partial)
@get_globals.register(functools.partialmethod)
def get_globals_func_attr(f: Callable):
    func = getattr(f, "func", None)
    if func is None:
        return None
    return get_globals(func)


def fully_concrete_signature(
    f: Callable, from_method: bool = False, tvar_map: Optional[Mapping] = None
):
    if tvar_map is not None:
        # for lru_cache on _fully_concrete_signature helper
        tvar_map = tuple(tvar_map.items())
    return _fully_concrete_signature(f, from_method, tvar_map)


@lru_cache(None)
def _fully_concrete_signature(
    f: Callable, from_method: bool = False, tvar_map: Optional[Tuple] = None
):
    if tvar_map is not None:
        tvar_map = dict(tvar_map)
    # handles classes and functions
    sig = constructor_signature(f)
    if from_method:
        sig = to_bound_method_signature(sig)
    globals_ = get_globals(f)
    new_sig = Signature(
        [
            param.replace(
                annotation=fully_concretize_type(param.annotation, tvar_map, globals_)
            )
            for param in sig.parameters.values()
        ]
    )
    return new_sig


def to_signature(obj: Union[Callable, Signature, BoundArguments]) -> Signature:
    if isinstance(obj, Signature):
        return obj
    elif isinstance(obj, BoundArguments):
        return obj.signature
    return signature(obj)


def to_parameters(
    obj: Union[Callable, Signature, MappingProxyType]
) -> MappingProxyType:
    if isinstance(obj, MappingProxyType):
        return obj
    sig = to_signature(obj)
    return sig.parameters


def to_bound_args_dict(obj: Union[OrderedDict, BoundArguments]) -> OrderedDict:
    if isinstance(obj, OrderedDict):
        return obj
    return obj.arguments


def to_bound_method_signature(
    obj: Union[Callable, Signature, MappingProxyType, list, tuple]
):
    if isinstance(obj, (list, tuple)):
        return Signature(obj[1:])
    return Signature(list(to_parameters(obj).values())[1:])


def call_with(f, bound_args_: BoundArguments):
    return f(*bound_args_.args, **bound_args_.kwargs)


def bind(
    sig: Union[Signature, Callable], args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> BoundArguments:
    if kwargs is None:
        kwargs = {}

    sig = to_signature(sig)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()
    return bound


def bind_verbosely(
    sig: Union[Callable, Signature],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    *,
    apply_defaults=True,
    name=None
) -> BoundArguments:
    if kwargs is None:
        kwargs = {}

    if not isinstance(sig, Signature) and name is None:
        name = sig.__name__

    sig = to_signature(sig)

    try:
        bound = sig.bind(*args, **kwargs)
    except TypeError as err:
        if name:
            raise TypeError("{}: {}".format(name, nice_exc_args(err)))
        else:
            raise err

    if apply_defaults:
        bound.apply_defaults()

    return bound


def validate_overrides(
    wrapper,
    wrapped,
    wrapper_is_method,
    wrapped_is_method,
    enforce_kinds=True,
    enforce_positional_order=False,
    enforce_positional_prefix=True,
):
    old_params, new_params = (to_parameters(f) for f in (wrapped, wrapper))

    old_pos, new_pos, old_kw, new_kw = (
        params_of_kind(ps, k, names_only=True)
        for ps, k in [
            (old_params, (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)),
            (new_params, (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)),
            (old_params, Parameter.KEYWORD_ONLY),
            (new_params, Parameter.KEYWORD_ONLY),
        ]
    )

    old_varpos, new_varpos, old_varkw, new_varkw = (
        getter(params)
        for params, getter in [
            (old_params, varargs_name),
            (new_params, varargs_name),
            (old_params, varkwargs_name),
            (new_params, varkwargs_name),
        ]
    )

    old_pos, new_pos = (
        t[1:] if is_method else t
        for t, is_method in [(old_pos, wrapped_is_method), (new_pos, wrapper_is_method)]
    )

    for old, new, kind, star in [
        (old_varpos, new_varpos, "positional", "*"),
        (old_varkw, new_varkw, "keyword", "**"),
    ]:
        if old is not None and new is None:
            raise WrapperSignatureError(
                "{wrapped} has variable {kind} args {star}{old} but {wrapper} does not".format(
                    wrapped=wrapped, wrapper=wrapper, star=star, old=old, kind=kind
                )
            )

    if not set(new_pos).issuperset(old_pos) and new_varpos is None:
        raise WrapperSignatureError(
            "{wrapper}'s positional args {new_pos} do not contain all of {wrapped}'s "
            "positional args {old_pos}, and no *varargs are present in {wrapper}'s signature "
            "to pass to {wrapped}".format(**locals())
        )

    if not set(new_kw).issuperset(old_kw) and new_varkw is None:
        raise WrapperSignatureError(
            "{wrapper}'s keyword args {new_kw} do not contain all of {wrapped}'s "
            "keyword args {old_kw}, and no **varkwargs are present in {wrapper}'s signature "
            "to pass to {wrapped}".format(**locals())
        )

    if enforce_kinds:
        pos_violations, kw_violations = (
            set(new_pos).intersection(old_kw),
            set(new_kw).intersection(old_pos),
        )

        if pos_violations or kw_violations:
            both = pos_violations and kw_violations
            raise WrapperSignatureError(
                "{} of {} are attempting to override {} of {}{}".format(
                    " and ".join(
                        temp.format(vs)
                        for temp, vs in [
                            ("positional args {}", pos_violations),
                            ("keyword args {}", kw_violations),
                        ]
                        if vs
                    ),
                    wrapper,
                    " and ".join(
                        temp.format(vs)
                        for temp, vs in [
                            ("keyword args {}", pos_violations),
                            ("positional args {}", kw_violations),
                        ]
                        if vs
                    ),
                    wrapped,
                    ", respectively" if both else "",
                )
            )

    if enforce_positional_prefix:
        # Require wrapped's positional arguments to be placed at the end of the wrapper's positional argument
        # signature, up to and including the last wrapped positional that is used by the wrapper.
        # This ensures that *args that would have been passed to the wrapped function may still be passed to the
        # wrapper function _after_ *extra_wrapper_args with no changes in binding.
        # We could have required rather that a wrapper must include new positionals as a _suffix_ to the wrapped
        # function's positionals, but this would have resulted in having to repeat all the wrapped positional args in
        # the wrapper signature in order to append a new one, since including *args as a prefix in the wrapper results
        # in all trailing args being keyword-only.
        old_pos_order = tuple(n for n in new_pos if n in old_pos)

        if not is_suffix(old_pos_order, new_pos) or not is_prefix(
            old_pos_order, old_pos
        ):
            prefixerr = (
                ""
                if is_prefix(old_pos_order, old_pos)
                else "{old_pos_order} is not a prefix of {wrapped}'s positional args {old_pos}".format(
                    **locals()
                )
            )
            suffixerr = (
                ""
                if is_suffix(old_pos_order, new_pos)
                else (
                    "{con} a suffix of {wrapper}'s positional args {new_pos}".format(
                        con=" or" if prefixerr else "{} is not".format(old_pos_order),
                        **locals()
                    )
                )
            )

            raise WrapperSignatureError(
                "{wrapper} overrides positional args {old_pos} from {wrapped} but "
                "{prefixerr}{suffixerr}".format(**locals())
            )
    elif enforce_positional_order:
        # Strictly less strict than enforce_positional_prefix, so we don't have to compute this in that case
        new_pos_order = tuple(n for n in new_pos if n in old_pos)
        old_pos_order = tuple(n for n in old_pos if n in new_pos)
        if new_pos_order != old_pos_order:
            raise WrapperSignatureError(
                "{} is attempting to reorder {}'s positional arguments {} to {}".format(
                    wrapper, wrapped, old_pos_order, new_pos_order
                )
            )

    return (
        (new_pos, new_varpos, new_kw, new_varkw),
        (old_pos, old_varpos, old_kw, old_varkw),
    )


def merged_signature(
    wrapper,
    wrapped,
    wrapper_is_method,
    wrapped_is_method,
    *,
    return_arg_names=False,
    enforce_kinds=True,
    enforce_positional_prefix=False
):
    wrapper_params, wrapped_params = to_parameters(wrapper), to_parameters(wrapped)
    wrapper_names, wrapped_names = validate_overrides(
        wrapper,
        wrapped,
        wrapper_is_method,
        wrapped_is_method,
        enforce_kinds=enforce_kinds,
        enforce_positional_prefix=enforce_positional_prefix,
    )
    new_pos, new_varpos, new_kw, new_varkw = wrapper_names
    old_pos, old_varpos, old_kw, old_varkw = wrapped_names
    new_params = []

    if wrapper_is_method:
        self_param = next(iter(wrapper_params.values()))
        new_params.append(self_param)

    new_params.extend(wrapper_params[p] for p in new_pos)
    new_params.extend(wrapped_params[p] for p in old_pos if p not in new_pos)

    if old_varpos is not None:
        # validation ensures that the wrapper has varargs too
        new_params.append(wrapped_params[old_varpos])

    new_params.extend(wrapper_params[p] for p in new_kw)
    new_params.extend(wrapped_params[p] for p in old_kw if p not in new_kw)

    if old_varkw is not None:
        # validation ensures that the wrapper has varkwargs too
        new_params.append(wrapped_params[old_varkw])

    sig = Signature(new_params)

    if not return_arg_names:
        return sig
    else:
        return sig, wrapper_names, wrapped_names


def params_of_kind(
    params, kind: Union[int, Sequence[int], Set[int]], filter_=None, names_only=False
):
    if not isinstance(params, Iterable):
        params = to_parameters(params)

    if isinstance(params, MappingProxyType):
        params = params.values()

    if isinstance(kind, int):
        kind = (kind,)

    ps = (p for p in params if p.kind in kind)

    if filter_ is not None:
        ps = filter(filter_, ps)
    if names_only:
        ps = (p.name for p in ps)

    return tuple(ps)


def leading_positionals(params, names_only=False):
    if not isinstance(params, Iterable):
        params = to_parameters(params)

    if isinstance(params, MappingProxyType):
        params = params.values()

    def inner(params):
        for p in params:
            if p.kind in (
                Parameter.VAR_POSITIONAL,
                Parameter.KEYWORD_ONLY,
                Parameter.VAR_KEYWORD,
            ):
                break
            yield p

    ps = inner(params)

    if names_only:
        ps = (p.name for p in ps)

    return tuple(ps)


def has_varkwargs(sig):
    return varkwargs_name(sig) is not None


def has_varargs(sig):
    return varargs_name(sig) is not None


def varkwargs_name(sig):
    params = to_parameters(sig)

    if not params:
        return None

    last_arg = next(reversed(params.values()))
    return last_arg.name if last_arg.kind == Parameter.VAR_KEYWORD else None


def varargs_name(sig):
    params = to_parameters(sig)

    if not params:
        return None

    param = None
    for param in params.values():
        if param.kind in (
            Parameter.VAR_POSITIONAL,
            Parameter.KEYWORD_ONLY,
            Parameter.VAR_KEYWORD,
        ):
            break

    return param.name if param.kind == Parameter.VAR_POSITIONAL else None


def argnames(func, skip_first=False):
    return _argnames(func, skip_first=skip_first, required=False)


def required_argnames(func, skip_first=False):
    return _argnames(func, skip_first=skip_first, required=True)


def _argnames(func, skip_first, required):
    params = to_parameters(func)

    if skip_first:
        params = list(params.values())[1:]

    filter_ = is_required if required else None

    return params_of_kind(
        params,
        (Parameter.KEYWORD_ONLY, Parameter.POSITIONAL_OR_KEYWORD),
        filter_=filter_,
        names_only=True,
    )


def is_required(param: Parameter):
    return param.default is Parameter.empty


Nameable_Types = (str, type, Callable_)


@dispatch(Callable_, tuple)
def call_repr(f, args):
    return call_repr(f, args, {})


@dispatch(Callable_, tuple, MappingABC)
def call_repr(f, args, kwargs):
    sig = signature(f)
    return call_repr(f, sig, args, kwargs)


@dispatch(Nameable_Types, BoundArguments)
def call_repr(name, bound):
    sig = bound.signature
    return call_repr(name, sig, bound)


@dispatch(Nameable_Types, Signature, tuple)
def call_repr(name, sig, args):
    return call_repr(name, sig, args, {})


@dispatch(Nameable_Types, Signature, tuple, MappingABC)
def call_repr(name, sig, args, kwargs):
    bound = bind(sig, args, kwargs)
    return call_repr(name, bound)


@dispatch(Nameable_Types, BoundArguments)
def call_repr(name, bound):
    sig = bound.signature
    return call_repr(name, sig, bound)


@dispatch(Callable_)
def get_callable_params(f):
    return get_callable_params(signature(f))


@dispatch(Signature)
def get_callable_params(sig):
    return get_callable_params(sig.parameters)


@dispatch(MappingProxyType)
def get_callable_params(params):
    def inner(annotations):
        memo = set()
        for t in annotations:
            for p in get_generic_params(t):
                if t in memo:
                    continue
                memo.add(p)
                yield p

    return tuple(inner(p.annotation for p in params.values()))


class Missing:
    pass


@dispatch(Nameable_Types, Signature, (BoundArguments, OrderedDict))
def call_repr(name, sig, bound, varpos_name=Missing, varkw_name=Missing):
    name = name_of(name)
    args_dict = to_bound_args_dict(bound).copy()

    if varkw_name is Missing:
        varkw_name = varkwargs_name(sig.parameters)
    if varpos_name is Missing:
        varpos_name = varargs_name(sig.parameters)

    if varpos_name is not None:
        pos_names = params_of_kind(
            sig.parameters, Parameter.POSITIONAL_OR_KEYWORD, names_only=True
        )
        pos = (args_dict.pop(n) for n in pos_names)
        args = tuple(chain(pos, args_dict.pop(varpos_name)))
    else:
        args = ()

    kwargs = args_dict.pop(varkw_name) if varkw_name is not None else {}

    return "{}({})".format(
        name,
        ", ".join(
            f(a)
            for f, a in [
                (args_repr, args),
                (kwargs_repr, args_dict),
                (kwargs_repr, kwargs),
            ]
            if a
        ),
    )


def kwargs_repr(kwargs: Union[Mapping, Iterable[Tuple[str, Any]]]):
    items = sorted(
        kwargs.items() if isinstance(kwargs, MappingABC) else kwargs, key=itemgetter(0)
    )
    return ", ".join("{}={}".format(k, repr(v)) for k, v in items)


def args_repr(args: Tuple[Any]):
    return ", ".join(map(repr, args))
