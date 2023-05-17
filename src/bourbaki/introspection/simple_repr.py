# coding:utf-8
from typing import Tuple, Union
from types import MethodType
from functools import partial, wraps
from warnings import warn
from inspect import signature, Parameter
from .callables import (
    bind,
    call_repr,
    params_of_kind,
    has_varargs,
    varkwargs_name,
    varargs_name,
)

# this is set on the class; we don't use __signature__ to prevent inspect.signature giving erroneous sigs on subclasses
INIT_SIG_ATTR = "__signature__"
INIT_VARKWARGS_NAME_ATTR = "__init_kwargs_name__"
INIT_VARARGS_NAME_ATTR = "__init_args_name__"
INSPECT_ATTRS_ATTR = "__inspect_attrs__"
REPLACE_DEFAULTS_ATTR = "__replace_defaults__"
REPR_NAME_ATTR = "__repr_name__"
# this is set on instances
INIT_ARGS_ATTR = "__init_args__"

INSPECT_ATTRS_DEFAULT = True
REPLACE_DEFAULTS_DEFAULT = False
USE_QUALNAME_DEFAULT = True


def simple_repr(self):
    args = getattr(self, INIT_ARGS_ATTR, None)
    if args is None:
        return object.__repr__(self)
    t = type(self)
    name, sig = getattr(t, REPR_NAME_ATTR, t.__name__), getattr(t, INIT_SIG_ATTR)
    varargs_name_, varkwargs_name_ = (
        getattr(t, INIT_VARARGS_NAME_ATTR),
        getattr(t, INIT_VARKWARGS_NAME_ATTR),
    )
    return call_repr(
        name, sig, args, varpos_name=varargs_name_, varkw_name=varkwargs_name_
    )


# class decorator
def with_simple_repr(
    inspect_attrs: Union[bool, Tuple[str]] = INSPECT_ATTRS_DEFAULT,
    replace_defaults: bool = REPLACE_DEFAULTS_DEFAULT,
    use_qualname: bool = USE_QUALNAME_DEFAULT,
):
    if isinstance(inspect_attrs, type):
        cls = inspect_attrs
        # the simple @with_simple_repr decorator usage
        return set_simple_repr_class_attrs(cls)
    else:
        # return a decorator
        return partial(
            set_simple_repr_class_attrs,
            inspect_attrs=inspect_attrs,
            replace_defaults=replace_defaults,
            use_qualname=use_qualname,
        )


# decorator for __init__ that stores call args info
class simple_repr_init:
    def __init__(self, init_func):
        self._init_func = init_func

    def __call__(init, self, *args, **kwargs):
        _init_ = init._init_func
        _init_(self, *args, **kwargs)
        set_simple_repr_init_args(self, args, kwargs)

    def __getattr__(self, item):
        return getattr(self._init_func, item)

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return MethodType(self, instance)


def set_simple_repr_init_args(self, args, kwargs, bound=None):
    if getattr(self, INIT_ARGS_ATTR, None) is not None:
        return

    sig = getattr(self, INIT_SIG_ATTR)
    if bound is None:
        bound = bind(sig, args, kwargs)

    setattr(self, INIT_ARGS_ATTR, bound.arguments)
    update_repr_args(self)


def update_repr_args(self):
    sig = getattr(self, INIT_SIG_ATTR)
    arguments = getattr(self, INIT_ARGS_ATTR)
    check_attrs = getattr(self, INSPECT_ATTRS_ATTR)
    print("CHECK", check_attrs)
    if check_attrs:
        cls = type(self)
        replace_defaults = getattr(cls, REPLACE_DEFAULTS_ATTR)

        if replace_defaults:
            filter_ = None
        else:

            def filter_(param):
                # where the default value wasn't passed, check the attribute
                return arguments[param.name] != param.default

        check_attrs_ = params_of_kind(
            sig.parameters,
            (
                Parameter.POSITIONAL_OR_KEYWORD,
                Parameter.VAR_POSITIONAL,
                Parameter.VAR_KEYWORD,
                Parameter.KEYWORD_ONLY,
            ),
            filter_=filter_,
            names_only=True,
        )

        if not isinstance(check_attrs, bool):
            # only check the specified attrs for replacement
            check_attrs_ = list(filter(check_attrs.__contains__, check_attrs_))

        arguments.update(
            (a, getattr(self, a)) for a in check_attrs_ if hasattr(self, a)
        )

        # now check any attrs that may have been set from **kwargs
        kw_name = getattr(cls, INIT_VARKWARGS_NAME_ATTR)
        if kw_name is not None:
            kwargs = arguments[kw_name]

            if isinstance(check_attrs, bool):
                check_attrs_ = list(kwargs)
            else:
                check_attrs_ = set(kwargs).intersection(check_attrs)

            kwargs.update(
                (a, getattr(self, a)) for a in check_attrs_ if hasattr(self, a)
            )

    setattr(self, INIT_ARGS_ATTR, arguments)


def update_repr(method):
    @wraps(method)
    def newmethod(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        update_repr_args(self)
        return result

    return newmethod


def set_simple_repr_class_attrs(
    cls,
    inspect_attrs=INSPECT_ATTRS_DEFAULT,
    replace_defaults=REPLACE_DEFAULTS_DEFAULT,
    use_qualname=USE_QUALNAME_DEFAULT,
    sig=None,
    override_init=True,
):
    # class signature - bound to an instance; can't call directly on cls lest signature() look up __signature__ on
    # a parent class with a different __init__
    if sig is None:
        sig = signature(cls)
    # sig = to_bound_method_signature(init_sig)

    if has_varargs(sig) and bool(params_of_kind(sig, Parameter.POSITIONAL_OR_KEYWORD)):
        warn(
            "class __init__ signatures with both *args and named positional args have less informative "
            "representations than those with *args and only named keyword-only args:\n{} has signature {}".format(
                cls, sig
            )
        )

    if isinstance(inspect_attrs, (tuple, frozenset)):
        if not all(isinstance(a, str) and str.isidentifier(a) for a in inspect_attrs):
            raise ValueError(
                "when a collection of attribute names is passed as inspect_attrs, "
                "all names should be strings and legal identifiers"
            )

        if any(a not in sig.parameters for a in inspect_attrs):  # pragma: no cover
            warn(
                "attribute names {} are not present in the init signature and will be ignored".format(
                    set(inspect_attrs).difference(sig.parameters)
                )
            )
            inspect_attrs = frozenset(sig.parameters).intersection(inspect_attrs)
    elif not isinstance(inspect_attrs, bool):  # pragma: no cover
        raise TypeError(
            "inspect_attrs should be a bool or an immutable collection (tuple, frozenset) of"
            "attribute names to be inspected"
        )

    setattr(cls, INIT_SIG_ATTR, sig)
    setattr(cls, INSPECT_ATTRS_ATTR, inspect_attrs)
    setattr(cls, REPLACE_DEFAULTS_ATTR, bool(replace_defaults))
    setattr(cls, INIT_VARKWARGS_NAME_ATTR, varkwargs_name(sig))
    setattr(cls, INIT_VARARGS_NAME_ATTR, varargs_name(sig))

    name = (
        "{}.{}".format(cls.__module__, cls.__qualname__)
        if use_qualname
        else cls.__name__
    )
    setattr(cls, REPR_NAME_ATTR, name)

    if override_init:
        cls.__init__ = simple_repr_init(cls.__init__)

    cls.__repr__ = simple_repr

    return cls
