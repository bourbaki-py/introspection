# coding:utf-8
from typing import Generic
import collections
from functools import partial
from inspect import Parameter
from .wrappers import cached_getter
from .imports import import_type
from .utils import identity
from .types.evaluation import deconstruct_generic, reconstruct_generic
from .types.inspection import is_named_tuple_class, get_named_tuple_arg_types
from .types.compat import get_constructor_for

NoneType = type(None)
Empty = Parameter.empty


class PicklableWithType:
    type_ = None

    def __init__(self, type_, *args):
        self.type_ = reconstruct_generic((type_, *args))

    def __getstate__(self):
        state = self.__dict__.copy()
        state["type_"] = deconstruct_generic(state.pop("type_"))
        return state

    def __setstate__(self, state):
        state["type_"] = reconstruct_generic(state.pop("type_"))
        self.__dict__.update(state)


class GenericWrapper(PicklableWithType):
    getter = staticmethod(identity)


class ReducingGenericWrapper(GenericWrapper):
    get_reducer = staticmethod(get_constructor_for)
    reduce = None
    generic_type = Generic

    def __init__(self, generic, *type_args):
        if self.reduce is None:
            self.reduce = self.get_reducer(generic)
        self.generic_type = generic
        super().__init__(generic, *type_args)

    def call_iter(self, arg):
        raise NotImplementedError()

    def __call__(self, arg):
        return self.reduce(self.call_iter(arg))


class LazyWrapper(GenericWrapper):
    """subclass and override getter to implement LazyType wrappers for config or text IO,
    decorating the subclass with the dispatcher's (if any) register() method"""

    def __init__(self, lazy, ref):
        self.ref = ref if isinstance(ref, str) else ref.__forward_arg__
        super().__init__(lazy, ref)

    @property
    @cached_getter
    def func(self):
        type_ = import_type(self.ref)
        return self.getter(type_)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __getstate__(self):
        state = self.__dict__
        state.pop("_func", None)
        return state


class CollectionWrapper(ReducingGenericWrapper):
    def __init__(self, coll_type, val_type=object):
        super().__init__(coll_type, val_type)
        self.val_func = self.getter(val_type)

    def call_iter(self, arg):
        return (self.val_func(a) for a in arg)


class TupleWrapper(ReducingGenericWrapper):
    _collection_cls = CollectionWrapper
    require_same_len = True

    def __new__(cls, tup_type, *types):
        if is_named_tuple_class(tup_type) and not types:
            types = get_named_tuple_arg_types(tup_type)
        if not types:
            cls = cls._collection_cls
        elif types[-1] is Ellipsis:
            # variable-length, uniformly-typed tuple
            cls = cls._collection_cls
            types = types[:1]

        new = object.__new__(cls)
        cls.__init__(new, tup_type, *types)
        return new

    def __init__(self, tup_type, *types):
        super().__init__(tup_type, *types)
        if not getattr(self, "funcs", None):
            # somehow this is being called twice in some instances - haven't identified the source
            self.funcs = tuple(self.getter(t) for t in types)

    def call_iter(self, arg):
        return (d(v) for d, v in zip(self.funcs, arg))

    def __call__(self, value):
        if self.require_same_len and len(value) != len(self.funcs):
            raise ValueError(
                "{} expected a collection of {} values for type {} but received {}".format(
                    self, len(self.funcs), self.type_, value
                )
            )
        return super().__call__(value)


class NamedTupleWrapper(TupleWrapper):
    reduce_named = None
    get_named_reducer = staticmethod(identity)

    def __init__(self, tup_type, *types):
        super().__init__(tup_type, *types)
        if not getattr(self, "named_funcs", None):
            self.named_funcs = dict(zip(tup_type._fields, self.funcs))
        if self.reduce_named is None:
            self.reduce_named = self.get_named_reducer(tup_type)

    def __call__(self, value):
        if isinstance(value, collections.Mapping):
            kwargs = ((name, self.named_funcs[name](v)) for name, v in value.items())
            return self.reduce_named(kwargs)
        return super().__call__(value)


def keyval_tup(k, v):
    return k, v


class MappingWrapper(ReducingGenericWrapper):
    key_getter = None
    keyval_op = staticmethod(keyval_tup)

    def __init__(self, coll_type, key_type, val_type):
        super().__init__(coll_type)
        key_getter = self.key_getter if self.key_getter is not None else self.getter
        self.keyfunc = key_getter(key_type)
        self.valfunc = self.getter(val_type)

    def call_iter(self, value):
        if isinstance(value, collections.Mapping):
            keyvals = value.items()
        else:
            keyvals = iter(value)
        kt, vt, op = self.keyfunc, self.valfunc, self.keyval_op
        return (op(kt(k), vt(v)) for k, v in keyvals)


def try_map(exc_type, f, it):
    if exc_type is None:
        exc_type = Exception
    for i in it:
        try:
            result = f(i)
        except exc_type:
            pass
        else:
            yield result


class AllFailed(ValueError):
    pass


class DisallowedException(ValueError):
    pass


class UnionWrapper(ReducingGenericWrapper):
    tolerate_errors = ()  # always raise with empty tuple in except clause
    tolerate_errors_call = (Exception,)
    exc_class_bad_exception = DisallowedException
    exc_class_no_success = AllFailed

    is_optional = False

    def __init__(self, union, *types):
        if not types:
            raise TypeError("{}: Can't interpret bare Union".format(type(self)))
        self.is_optional = any(t in (NoneType, None) for t in types)
        super().__init__(union, *types)
        map_ = partial(try_map, self.tolerate_errors) if self.tolerate_errors else map

        self.funcs = tuple(map_(self.getter, types))
        if not self.funcs:
            raise TypeError(
                "Could not determine functions for {} type args using getter {}".format(
                    union[types], self.getter
                )
            )

    def call_iter(self, value):
        excs = []
        ok_excs = []
        results = False
        for f in self.funcs:
            try:
                result = f(value)
            except self.tolerate_errors_call as e:
                ok_excs.append(e)
            except Exception as e:
                excs.append(e)
            else:
                yield result
                results = True

        if excs:
            raise self.exc_class_bad_exception(*excs)
        if not results:
            raise self.exc_class_no_success(*ok_excs)
