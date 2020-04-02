from bourbaki.introspection.simple_repr import with_simple_repr, update_repr
import pytest

module = __name__ + "."


@with_simple_repr(inspect_attrs=("a",))
class Foo:
    def __init__(self, a, *args, b, **kwargs):
        if not isinstance(a, int):
            a = int(a)
        self.a = a

    @update_repr
    def increment_a(self):
        self.a += 1
        return self


# bare decorator
@with_simple_repr
class Bar:
    def __init__(self, a, *args, b, **kwargs):
        if not isinstance(a, int):
            a = int(a)
        self.a = a


@pytest.mark.parametrize(
    "value,repr_",
    [
        (Foo(1, b=2), module + "Foo(1, b=2)"),
        (Bar(1, b=2), module + "Bar(1, b=2)"),
        (Foo(1, 2, b=3), module + "Foo(1, 2, b=3)"),
        (Bar(1.0, 2, b=3), module + "Bar(1, 2, b=3)"),
        (Foo(1.0, 2, b=3, c=5), module + "Foo(1, 2, b=3, c=5)"),
        (Foo(1.0, 2, b=3, c=5).increment_a(), module + "Foo(2, 2, b=3, c=5)"),
    ],
)
def test_simple_repr(value, repr_):
    assert repr(value) == repr_
