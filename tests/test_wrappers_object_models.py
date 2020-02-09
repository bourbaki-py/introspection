#coding:utf-8
import pytest
from inspect import signature
from bourbaki.introspection.subclassing import subclass_mutator_method, subclass_method
from bourbaki.introspection.simple_repr import with_simple_repr
from bourbaki.introspection.object_models.scala import MultipleInheritanceError, ScalaClass, val, var
from bourbaki.introspection.typechecking import type_checker
from typing import List, Tuple, Set, Sequence


@pytest.fixture(scope="module")
def ClassWithSimpleRepr():
    @with_simple_repr(use_qualname=False, inspect_attrs=('things', 'x', 'y', 'foo'))
    class Foo:
        def __init__(self, *things, x, y=1, z=2, **extras):
            self.things = tuple(map(str, things))
            self.x = bool(x)
            self.y = -abs(y)
            self.z = float(z)

            if 'foo' in extras:
                self.foo = extras['foo'].strip()
            else:
                self.foo = None

    return Foo


@pytest.fixture(scope="module")
def Foo():
    class Foo:
        def __init__(self, a, *, b: int=4):
            """I take a and an int b"""
            self.a = a
            self.b = b
            """i take a and an int b"""

        def add(self):
            return self.a + self.b

        def list(self):
            return self.a, self.b

    return Foo


@pytest.fixture(scope="module")
def Bar(Foo):
    class Bar:
        @subclass_mutator_method(Foo)
        def __init__(self, d=0, a=2, *args, c: str="foo", **kw):
            """i also take a str c and anything d"""
            self.d = d
            self.c = c

        @subclass_method(Foo, pass_to_wrapper_as="x")
        def add(self, x=0):
            return self.c + self.d + x

        @subclass_method(Foo.list, pass_to_wrapper_as=("a", "b"))
        def add_again(self, a=None, b=None):
            return a + b + self.c + self.d

    return Bar


@pytest.fixture
def bar(Bar):
    return Bar(4, 1, b=2, c=3)


def test_SubclassMutator_init(bar):
    for attr, n in zip("abcd", [1, 2, 3, 4]):
        assert getattr(bar, attr) == n


def test_SubclassMutator_init_sig(Bar):
    assert list(signature(Bar).parameters) == ['d', 'a', 'c', 'b']
    assert list(signature(Bar.__init__).parameters) == ['self', 'd', 'a', 'c', 'b']


def test_SubclassMethod_one_arg(bar):
    assert bar.add() == 10


def test_SubclassMethod_multi_arg(bar):
    assert bar.add_again() == 10


def test_simple_repr(ClassWithSimpleRepr):
    name = ClassWithSimpleRepr.__name__
    x, y, z = 1, 1, 3
    foo = ClassWithSimpleRepr(1, 2, (3, 4), x=x, z=z, **dict(foo="  bar  ", bar="  baz  "))

    assert foo.x == bool(x)
    assert foo.y == -abs(y) and isinstance(foo.y, type(y))
    assert foo.z == float(z) and isinstance(foo.z, float)
    assert foo.foo == "bar"
    # things, x, y, and foo are inspected, but y is the default
    # so repr should show things, x, and foo as they exist as attributes, y as default (1 vs -1)
    print(repr(foo))
    assert repr(foo) == ("{}('1', '2', '(3, 4)', x=True, y=1, z=3, bar='  baz  ', foo='bar')"
                         .format(name))


# Scala object model tests

class A(metaclass=ScalaClass):
    x: float = val(float)

    def __init__(self, x=5):
        print("x is", x)


class B(A):
    y: str = var(str.strip, str.lower)

    def __init__(self, y, *a): pass


class mixin:
    @property
    def z(self):
        return str(self.x) + self.y


class C(B, mixin):
    def __init__(self, *a, **kw):
        print(a, kw)


class pythonclass1:
    def __init__(self, **kw):
        self.__dict__.update(**kw)


class pythonclass2:
    def __init__(self, **kw):
        self.__dict__.update(**kw)


class pythonclass3(pythonclass1, pythonclass2):
    def __init__(self, **kw):
        pythonclass1.__init__(self, **kw)
        pythonclass2.__init__(self, **kw)


@pytest.fixture
def a():
    return A()


@pytest.fixture
def b():
    return B('  ASDF  ')


@pytest.fixture
def c():
    return C('  fghj  ')


def test_scala_class_repr():
    for cls in A, B, C:
        assert repr(cls) == "<{} {}>".format(cls.__name__, str(signature(cls)))


def test_scala_class_init(a, b, c):
    for obj in a, b, c:
        assert obj.x == 5.0


def test_scala_instance_repr(a, b, c):
    assert repr(a) == "A(x=5.0)"
    assert repr(b) == "B(x=5.0, y='asdf')"
    assert repr(c) == "C(x=5.0, y='fghj')"


def test_set_var(b):
    b.y = "  FOObar  "
    assert b.y == 'foobar'


def test_set_val(a):
    with pytest.raises(AttributeError):
        a.x = 5


def test_property_depending_on_vals(c):
    assert c.z == '5.0fghj'


@pytest.mark.parametrize("scalaclass", [A, B, C])
@pytest.mark.parametrize("pyclass", [pythonclass1, pythonclass2, pythonclass3])
def test_multiple_inheritance_forbidden(scalaclass, pyclass):
    with pytest.raises(MultipleInheritanceError):
        class Cls(scalaclass, pyclass):
            pass


@pytest.mark.parametrize("t,v",
                         [(List[int], [1, 2, 3]),
                          (Tuple, ("foo", 34)),
                          (Tuple[str, int], ("foo", 42)),
                          (Set[Tuple[int, ...]], {(1,), (1, 2, 3)}),
                          (Sequence[int], (1, 2, 3)),
                          (Sequence[str], "asdf"),
                          (bytes, b'foo'),
                          ])
def test_typechecker(t, v):
    tc = type_checker(t)
    assert tc(v)
