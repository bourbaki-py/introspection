# coding:utf-8
from inspect import signature, Signature
from itertools import islice
from operator import attrgetter
from ..callables import bind
from ..simple_repr import set_simple_repr_init_args, set_simple_repr_class_attrs
from ..subclassing import SubclassMutatorMethod


class ScalaClass(type):
    """At import time, a class with ScalaClass as its metaclass will require:
        - at most one of its bases will have an __init__ (the others are mixins/interfaces)
        - there can be no conflicting arguments in the respective __init__ methods; i.e. if a named argument is
          included in the signature of the subclass (not including the varargs and var-keyword args aliases),
          it must be of the same kind as the named argument in the superclass __init__ (positional, keyword-only, etc.)

    Additionally, these come for free:
        - calls to the inherited proper class's __init__ (if any) occur automatically with the proper args/kwargs
          (even in the presence of *args, **kwargs in the init signature, with no explicit superclass args)
        - a __repr__ that reflects the call signature, including arguments passed implicitly to the superclass __init__
        - attributes are stored on the instance when the class has dummy attributes which are var or val instances
        - val attributes cannot be mutated (they are properties with no setter)
    """

    __vals__ = None

    def __new__(mcs, name, bases, namespace):
        bases, proper_base = validate_bases(bases)

        if proper_base is not None:
            namespace["__base__"] = proper_base
            base_init = proper_base.__init__ if defines_init(proper_base) else None
        else:
            base_init = None

        annotations = namespace.get("__annotations__", {})

        vals = dict(
            (name, v.set_name(name).set_type(annotations.get(name)))
            for name, v in namespace.items()
            if isinstance(v, (val, var))
        )

        if hasattr(proper_base, "__vals__"):
            vals.update(proper_base.__vals__)

        namespace["__vals__"] = vals

        namespace.update((name, v.make_property()) for name, v in vals.items())

        if "__init__" in namespace:
            init = namespace["__init__"]

            if proper_base is not None and base_init is not None:
                init = SubclassMutatorMethod(
                    init, base_init, wrapped_is_method=True, call_wrapped_manually=False
                )
            else:
                init.__signature__ = signature(init)

            namespace["__init__"] = init
            namespace["__signature__"] = make_class_signature(init)
        else:
            if base_init is not None:
                namespace["__signature__"] = make_class_signature(base_init)
            else:
                # have to get around signature() looking up the metaclass __call__
                namespace["__signature__"] = Signature()

        if (
            "__new__" in namespace
            and proper_base is not None
            and defines_new(proper_base)
        ):
            raise Multiple__new__Error(proper_base)

        cls = type.__new__(mcs, name, bases, namespace)

        cls_sig = signature(cls)
        cls.__signature__ = cls_sig

        params = cls_sig.parameters.keys()
        if any(name not in params for name in vals):
            raise MissingValError(set(vals).difference(params), cls_sig)

        if "__repr__" not in namespace:
            # if no repr is defined manually, insert the standard repr
            cls = set_simple_repr_class_attrs(
                cls,
                inspect_attrs=True,
                replace_defaults=False,
                use_qualname=False,
                override_init=False,
            )

        return cls

    def __call__(cls, *args, **kwargs):
        new = cls.__new__
        if new is object.__new__:
            self = new(cls)
        else:
            self = new(cls, *args, **kwargs)

        sig = cls.__signature__
        bound = bind(sig, args, kwargs)

        # vals - doing this before __init__ ensures that the vals are available there
        for v in cls.__vals__.values():
            v.assign(self, bound.arguments[v.name])
            bound.arguments[v.name] = getattr(self, v.name)

        cls.__init__(self, *bound.args, **bound.kwargs)

        # for repr info
        set_simple_repr_init_args(self, args, kwargs, bound=bound)

        return self

    def __repr__(cls):
        return "<{} {}>".format(cls.__qualname__, str(signature(cls)))


##############
# properties #
##############


class val_mixin:
    name = None
    private_name = None
    validators = ()

    def __init__(self, *validators):
        validators_ = []
        for v in validators:
            if not callable(v):
                raise ValValidatorError(self, v)
            validators_.append(v)

        self.validators = tuple(validators_)

    def set_name(self, name):
        self.name = name
        self.private_name = "_{}".format(name)
        return self

    def set_type(self, type_=None):
        if type_ is None:
            return self
        else:
            if not isinstance(type_, tuple):
                type_ = (type_,)
            self.validators = self.validators + (type_check(*type_),)

        return self

    def validate(self, value):
        if not self.validators:
            return value

        for f in self.validators:
            try:
                value = f(value)
            except Exception as e:
                raise ValValidationError(self.name, e)

        return value

    def assign(self, obj, value):
        setattr(obj, self.private_name, self.validate(value))

    def __str__(self):
        if not self.validators:
            return "<val {}>".format(self.name)
        else:
            return "<val {}(validators=({}))>".format(
                self.name, ", ".join(map(repr, self.validators))
            )


class val(val_mixin):
    def make_property(self):
        return property(attrgetter(self.private_name))


class var(val_mixin):
    def make_property(self):
        return property(attrgetter(self.private_name), self.attrsetter())

    def attrsetter(self):
        def set_(obj, value):
            value_ = self.validate(value)
            setattr(obj, self.private_name, value_)
            obj.__init_args__[self.name] = value_

        return set_


class type_check:
    def __init__(self, *type_):
        self.type_ = type_

    def __call__(self, obj):
        if isinstance(obj, self.type_):
            return obj
        raise TypeError(
            "expected an instance of {}; got {}".format(self.type_, type(obj))
        )

    def __str__(self):
        return "{}({})".format(
            self.__class__.__name__, ", ".join(map(repr, self.type_))
        )

    __repr__ = __str__


###########
# helpers #
###########


def validate_bases(bases):
    proper_bases = list(filter(is_proper_class, bases))

    if len(proper_bases) > 1:
        raise MultipleInheritanceError(*proper_bases)

    proper_base = proper_bases[0] if len(proper_bases) > 0 else None

    return bases, proper_base


def is_proper_class(cls):
    return defines_init(cls) or defines_new(cls)


def defines_new(cls):
    return cls.__new__ is not object.__new__


def defines_init(cls):
    return cls.__init__ is not object.__init__


def make_class_signature(init):
    sig = signature(init)
    return Signature(islice(sig.parameters.values(), 1, None))


##############
# Exceptions #
##############


class ScalaClassError(Exception):
    pass


class MultipleInheritanceError(ScalaClassError, TypeError):
    def __str__(self):
        return (
            "Can only inherit from at most one proper (non-interface) class; {} all define custom "
            "__init__ or __new__".format(self.args)
        )


class Multiple__new__Error(ScalaClassError, TypeError):
    def __str__(self):
        return (
            "Cannot override __new__ when inheriting from a class which also defines it; {} defines a "
            "custom __new__".format(self.args[0])
        )


class MissingValError(ScalaClassError, TypeError):
    def __str__(self):
        return "{} are specified as vals on the class but their names are absent in the init signature: {}".format(
            self.args[0], self.args[1]
        )


class ValValidationError(ScalaClassError, ValueError):
    def __str__(self):
        return "Error setting val {}: {}".format(self.args[0], self.args[1])


class ValValidatorError(ScalaClassError, TypeError):
    def __str__(self):
        return "Expected validator for {} to be callable; got type {}".format(
            self.args[0], type(self.args[1])
        )


class ValTypeValidatorError(ScalaClassError, TypeError):
    def __str__(self):
        return "Expected validator for {} to be a type; got {}".format(
            self.args[0], self.args[1]
        )
