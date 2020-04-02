from numbers import Real
from bourbaki.introspection.polymorphism import SingleValueDispatch

import pytest

func = SingleValueDispatch("func")

# fallback
@func.register(lambda x: True)
def identity(x):
    return x


@func.register_fork(
    {"str": lambda x: x + "1", "bool": lambda x: not x, "complex": lambda x: abs(x)}
)
def typename(x):
    return type(x).__name__


# registered last; highest priority
@func.register(lambda x: isinstance(x, Real))
def func_real(x: Real):
    return x + 1


@pytest.mark.parametrize(
    "i,o",
    [
        (1, 2),
        (1.0, 2.0),
        # Real instance check registered after the fork - so it takes precedence
        (True, 2),
        (3 + 4j, 5.0),
        ("foo", "foo1"),
        ([1, 2, 3], [1, 2, 3]),
    ],
)
def test_single_value_dipatch(i, o):
    r = func(i)
    assert type(r) is type(o)
    assert r == o
