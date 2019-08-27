from typing import *
from itertools import chain, repeat
import pytest

from bourbaki.introspection.types import issubclass_generic as isg, get_generic_args as gga
from bourbaki.introspection.types import is_named_tuple_class as intc, concretize_typevars as ctv
from bourbaki.introspection.types import reparameterize_generic as rpg, eval_forward_refs as efr
from bourbaki.introspection.callables import Starred, UnStarred


T = TypeVar("T", int, str, covariant=True)


# recursive type
class foo(NamedTuple):
    x: Optional['foo']
    y: T


foo_ = efr(foo, globals())
foo__ = efr(foo, globals())

fooconcrete = ctv(foo_)


# should not register as a namedtuple
class bar(foo, Generic[T]):
    def __new__(cls, y: T, *args):
        self = super().__new__(cls, *args)
        self.y = y
        return self


class intstr(NamedTuple):
    foo: int
    bar: str


@pytest.mark.parametrize("subclass, superclass",
    chain(zip(repeat(intstr), [Tuple[Union[int, float], str], Tuple[int, str]]),
          [(bar, foo), (bar[int], foo), (bar[bool], bar[int])])
)
def test_namedtuple_issubclass_generic(subclass, superclass):
    assert isg(subclass, superclass)

assert gga(rpg(bar[T], {T: str})) == (str,)


def test_eval_forward_refs_namedtuple():
    assert foo_.__annotations__['x'] == Optional[foo]
    assert foo_ is foo__
    assert isg(foo_, foo)
    assert isg(foo_, foo__)


@pytest.mark.parametrize("cls", [foo, foo_])
def test_is_namedtuple_class(cls):
    assert intc(cls)


@pytest.mark.parametrize("cls", [bar])
def test_not_is_namedtuple_class(cls):
    assert not intc(cls)


def test_concretize_typevars_namedtuple():
    assert fooconcrete.__annotations__['y'] == Union[int, str]
    assert fooconcrete.__annotations__['x'] == Optional[foo]


def test_starred_namedtuple():
    assert UnStarred(foo)((None, 2)) == (foo(None, 2))
