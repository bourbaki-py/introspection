# coding:utf-8
from types import MethodType
from functools import update_wrapper
from inspect import signature, Signature, Parameter
from .callables import bind_verbosely, validate_overrides, merged_signature


# decorators
def subclass_mutator_method(
    wrapped_method_or_class,
    call_wrapped_first=True,
    call_wrapped_manually=False,
    wrapped_is_method=True,
    concat_docs=True,
):
    """Decorate e.g. an __init__ for a subclass with @subclass_mutator_method(Superclass), when a new argument is
    needed or a prior default value overridden but there is no complex logic required for initialization that involves
    a mixture of the arguments from the parent class method and the subclass method.

    By default, the parent method is called with the subset of arguments that it accepts, then the new method is called
    with all of the arguments. If you wish to call the parent method yourself you may pass the keyword arg
    `call_wrapped_manually=True` to the decorator. If the wrapped method is actually a plain function, pass
    `wrapped_is_method=False` to the decorator. This prevents the wrapper's first argument (i.e. `self`) from being
    passed to the wrapped method, even if its name happens to match that of an argument in the wrapped method.
    """

    def dec(wrapper_method):
        return SubclassMutatorMethod(
            wrapper_method,
            wrapped_method_or_class,
            call_wrapped_first=call_wrapped_first,
            call_wrapped_manually=call_wrapped_manually,
            wrapped_is_method=wrapped_is_method,
            concat_docs=concat_docs,
        )

    return dec


subclass_init = subclass_mutator_method


def subclass_method(
    wrapped_method_or_class, pass_to_wrapper_as, wrapped_is_method=True
):
    def dec(wrapper_method):
        return SubclassMethod(
            wrapper_method,
            wrapped_method_or_class,
            pass_to_wrapper_as=pass_to_wrapper_as,
            wrapped_is_method=wrapped_is_method,
        )

    return dec


class _SubclassMethodBase:
    new_pos = None
    old_pos = None
    new_varpos = None
    old_varpos = None
    new_kw = None
    old_kw = None
    new_varkw = None
    old_varkw = None
    wrapped = None
    wrapper = None
    wrapped_sig = None
    wrapper_sig = None
    wrapped_is_method = None
    __signature__ = None

    def __init__(
        self, wrapper, wrapped_method_or_class, *, wrapped_is_method, concat_docs=True
    ):
        self.wrapped = get_wrapped_method(wrapper, wrapped_method_or_class)
        self.wrapped_sig = signature(self.wrapped)
        self.wrapper = wrapper
        self.wrapper_sig = signature(wrapper)
        self.wrapped_is_method = bool(wrapped_is_method)

        wrapper_names, wrapped_names = validate_overrides(
            wrapper=self.wrapper_sig,
            wrapped=self.wrapped_sig,
            wrapper_is_method=True,
            wrapped_is_method=wrapped_is_method,
        )

        self.new_pos, self.new_varpos, self.new_kw, self.new_varkw = wrapper_names
        self.old_pos, self.old_varpos, self.old_kw, self.old_varkw = wrapped_names

        wrapped, wrapper = self.wrapped, self.wrapper

        update_wrapper(
            self,
            wrapper,
            assigned=(
                "__name__",
                "__qualname__",
                "__module__",
                "__annotations__",
                "__kwdefaults__",
            ),
            updated=(),
        )

        if concat_docs and (wrapped.__doc__ is not None or wrapper.__doc__ is not None):
            self.__doc__ = "\n".join(f.__doc__ for f in (wrapped, wrapper) if f.__doc__)

    def get_wrapped_args_kwargs(self, args, kwargs):
        bound = bind_verbosely(
            self.wrapper_sig, args, kwargs, name=self.wrapper.__qualname__
        )
        allargs = bound.arguments

        new_varpos, new_varkw = (self.new_varpos, self.new_varkw)
        varargnames = new_varpos, new_varkw

        # self
        wrapped_args = [args[0]] if self.wrapped_is_method else []

        # wrapped positional args that
        wrapped_args.extend(
            allargs[k] for k in self.old_pos if k in allargs and k not in varargnames
        )

        if new_varpos:
            wrapped_args.extend(allargs[new_varpos])

        wrapped_kwargs = dict(
            (k, allargs[k])
            for k in self.old_kw
            if k in allargs and k not in varargnames
        )

        if new_varkw is not None:
            wrapped_kwargs.update(allargs[new_varkw])

        # this will throw a nice error if anything is missing
        _ = bind_verbosely(
            self.wrapped_sig,
            tuple(wrapped_args),
            wrapped_kwargs,
            name=self.wrapped.__qualname__,
        )

        return wrapped_args, wrapped_kwargs

    def __get__(self, obj, cls):
        if obj is not None:
            return MethodType(self, obj)
        return self

    def __call__(self, *args, **kwargs):
        pass


class SubclassMutatorMethod(_SubclassMethodBase):
    call_wrapped_manually = None

    def __init__(
        self,
        wrapper,
        wrapped_method_or_class,
        *,
        wrapped_is_method=True,
        call_wrapped_first=True,
        call_wrapped_manually=False,
        concat_docs=True
    ):
        super().__init__(
            wrapper,
            wrapped_method_or_class,
            wrapped_is_method=wrapped_is_method,
            concat_docs=concat_docs,
        )

        self.__signature__ = merged_signature(
            self.wrapper_sig,
            self.wrapped_sig,
            wrapper_is_method=True,
            wrapped_is_method=wrapped_is_method,
            return_arg_names=False,
        )

        self.call_wrapped_first = bool(call_wrapped_first)
        self.call_wrapped_manually = bool(call_wrapped_manually)

    def __call__(self, *args, **kwargs):
        wrapped_args, wrapped_kwargs = self.get_wrapped_args_kwargs(args, kwargs)
        if not self.call_wrapped_manually:
            if self.call_wrapped_first:
                self.wrapped(*wrapped_args, **wrapped_kwargs)
                return self.wrapper(*args, **kwargs)
            else:
                self.wrapper(*args, **kwargs)
                return self.wrapped(*wrapped_args, **wrapped_kwargs)
        else:
            return self.wrapper(*args, **kwargs)


class SubclassMethod(_SubclassMethodBase):
    pass_to_wrapper_as = None
    pass_to_wrapper_kind = None
    pass_multiple_args = None

    def __init__(
        self,
        wrapper,
        wrapped_method_or_class,
        *,
        wrapped_is_method=True,
        pass_to_wrapper_as=None
    ):
        if not isinstance(pass_to_wrapper_as, str):
            if not isinstance(pass_to_wrapper_as, tuple) or not all(
                isinstance(n, str) for n in pass_to_wrapper_as
            ):
                raise TypeError(
                    "`pass_to_wrapper_as` must be str or a tuple of str; got {}".format(
                        repr(pass_to_wrapper_as)
                    )
                )

        super().__init__(
            wrapper, wrapped_method_or_class, wrapped_is_method=wrapped_is_method
        )

        pass_multiple = isinstance(pass_to_wrapper_as, tuple)
        self.pass_multiple_args = pass_multiple
        self.pass_to_wrapper_as = pass_to_wrapper_as

        pass_to_wrapper_kind = (
            tuple(self.wrapper_sig.parameters[k].kind for k in pass_to_wrapper_as)
            if pass_multiple
            else self.wrapper_sig.parameters[pass_to_wrapper_as].kind
        )

        self.pass_to_wrapper_kind = pass_to_wrapper_kind

        kinds = pass_to_wrapper_kind if pass_multiple else (pass_to_wrapper_kind,)
        if not all(
            k in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
            for k in kinds
        ):
            raise TypeError(
                "wrapped result is specified to be passed to {}, which is of kind {}; only parameter kinds "
                "{} are allowed here".format(
                    pass_to_wrapper_as,
                    repr(pass_to_wrapper_kind),
                    (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY),
                )
            )

        pass_names = pass_to_wrapper_as if pass_multiple else (pass_to_wrapper_as,)
        wrapper_call_sig = Signature(
            p for p in self.wrapper_sig.parameters.values() if p.name not in pass_names
        )
        self.__signature__ = merged_signature(
            wrapper_call_sig,
            self.wrapped_sig,
            wrapper_is_method=True,
            wrapped_is_method=wrapped_is_method,
            return_arg_names=False,
        )

    def __call__(self, *args, **kwargs):
        wrapped_args, wrapped_kwargs = self.get_wrapped_args_kwargs(args, kwargs)

        result = self.wrapped(*wrapped_args, **wrapped_kwargs)

        result_arg = self.pass_to_wrapper_as

        if not self.pass_multiple_args:
            kwargs[result_arg] = result
        else:
            kwargs.update(zip(result_arg, result))

        return self.wrapper(*args, **kwargs)


def get_wrapped_method(wrapper, wrapped_method_or_class):
    if isinstance(wrapped_method_or_class, type):
        # resolve the method on the parent class
        wrapped = getattr(wrapped_method_or_class, wrapper.__name__)
    else:
        wrapped = wrapped_method_or_class

    return wrapped
