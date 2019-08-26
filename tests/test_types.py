# coding:utf-8
from typing import *
from typing import Pattern, Match, ChainMap, Counter, TypeVar
import pytest
import collections
from collections import abc as collections_abc
from numbers import Number, Integral, Real
from itertools import repeat, chain, product, combinations
from bourbaki.introspection.types import (issubclass_generic, get_generic_params, deconstruct_generic,
                                             reconstruct_generic, get_constructor_for, eval_forward_refs,
                                             constraint_type, LazyType, Builtin, NonStrCollection,
                                             NonAnyStrCollection, NonStrSequence, NonAnyStrSequence)

T_co = TypeVar("T", covariant=True)
K = TypeVar("K")

class Foo(Mapping[K, T_co]): ...

class Bar(Foo[int, T_co]): ...

class MyStr(str): ...

class MySpecialStr(MyStr): ...

class Baz(Bar[MySpecialStr]):
    """I should be a subclass of Mapping[int, str] and Mapping[int, MyStr] and
    Container[int]"""

class Boom(Baz): ...

class FooTuple(NamedTuple):
    foo: int
    bar: bool
    baz: MyStr

newtype1 = NewType("newtype1", List[int])

newtype2 = NewType("newtype2", newtype1)


Hashable.register(Number)

atomic_chains = [
    (bool, int, Integral, Number, Union[Number, str], Hashable),
    (float, Real, Number, Hashable, Any),
    (complex, Number, Any),
    (str, Union[str, bytes], Any),
    (bytes, Union[str, bytes], Hashable),
    (Pattern[str], Pattern, Any),
    (Match[bytes], Match, Any),
    (newtype2, newtype1, Collection[Number]),
]

generic_chains = [
    (List, Sequence, Collection, Iterable),
    (Set, AbstractSet, Collection, Iterable),
    (Tuple[T_co, ...], Sequence, Collection, Union[Sized, Iterable[T_co]]),
    (Union[List[T_co], Tuple[T_co]], Sequence, Collection),
    (Union[List[T_co], Tuple[T_co, ...], Set[T_co]], Collection),
]

key_types = list(set(chain.from_iterable(atomic_chains)))

mapping_chains = [
    (Mapping, Collection),
    (ChainMap, Mapping, Collection),
]

tuple_chains = [
    (FooTuple, Tuple[Union[int, complex], int, str], Tuple[Number, Union[int, Number], Hashable], Tuple[Union[Number, Hashable], Any, Hashable]),
    (Tuple[Counter[str], Mapping[str, int]], Tuple[Mapping[str, Number], Mapping[str, Any]], Tuple[Collection[Hashable], ...]),
]

callable_chains = [
    (Callable[[Any, Any], Union[Number, str]], Callable[[Number, Number], Hashable], Callable[[int, float], Any], Callable),
    (Callable[[Mapping[str, Hashable]], Number], Callable[[Mapping[str, Number]], Hashable], Callable[[Counter[str]], Any]),
    (Callable[[Any, Number], bool], Callable[..., int], Callable[..., Number])
]

generic_constructors = [
    (List, list),
    (Tuple, tuple),
    (Dict, dict),
    (MutableMapping, dict),
    (Counter, collections.Counter),
    (ChainMap, collections.ChainMap),
    (FrozenSet, frozenset),
    (Iterable, list),
    (AbstractSet, set),
    (MutableSet, set),
]


class Dummy:
    pass


type_refs = [
    (Tuple["Number", "T_co", "Dummy"], Tuple[Number, T_co, Dummy]),
    (Mapping[Tuple["Any", "Dummy"], Set["T_co"]], Mapping[Tuple[Any, Dummy], Set[T_co]]),
    (Callable[[Tuple["T_co", ...]], Set[Tuple["Dummy", Iterable["Any"]]]],
     Callable[[Tuple[T_co, ...]], Set[Tuple[Dummy, Iterable[Any]]]]),
    (LazyType["collections.abc.Iterable"], LazyType["collections.abc.Iterable"]),
]


class mystr(str):
    pass


abstract_classes_pos = [
    (Builtin, [int, str, list, tuple, bytes, set, frozenset, complex]),
    (NonStrCollection, [list, tuple, set, frozenset, bytes, Tuple, List, Collection, Mapping, Set, ByteString]),
    (NonAnyStrCollection, [list, tuple, set, frozenset, Tuple, List, Collection, Mapping, Set]),
    (NonStrSequence, [list, tuple, bytes, Tuple, List, ByteString]),
    (NonAnyStrSequence, [list, tuple, Tuple, List]),
]

abstract_classes_neg = [
    (Builtin, [collections_abc.Collection, Number, Any]),
    (NonStrCollection, [str, mystr]),
    (NonAnyStrCollection, [str, mystr, bytes, ByteString]),
    (NonStrSequence, [str, mystr]),
    (NonAnyStrSequence, [str, mystr, bytes, ByteString]),
]


def abstract_class_test_cases(classes):
    return chain.from_iterable(zip(repeat(cls), subs) for cls, subs in classes)


def tvars_and_constraint_types(types):
    for t in types:
        yield TypeVar("T", bound=t), t
    for t1, t2 in combinations(types, 2):
        yield TypeVar("T", t1, t2), Union[t1, t2]


def ordered_pairs(seq):
    return combinations(seq, 2)


def parameterize(org, *args):
    return org[args[:len(get_generic_params(org))]]


def _test_cases(generic_chain, atomic_chain, *extras, reverse=False):
    if reverse:
        generic_chain = reversed(generic_chain)
        atomic_chain = reversed(atomic_chain)
    # g1 <: g1 & t1 <: t2 => g1[t1] <: g2[t2]
    return ((parameterize(g1, *extras, t1), parameterize(g2, *extras, t2))
            for (g1, g2), (t1, t2) in product(ordered_pairs(generic_chain),
                                              ordered_pairs(atomic_chain))
            )


def _mapping_test_cases(mapping_chain, atomic_chain, key_types, reverse=False):
    return _test_cases(mapping_chain, atomic_chain, *key_types, reverse=reverse)


def all_test_cases(reverse=False):
    return list(set(chain(
        chain.from_iterable(_mapping_test_cases(gc, ac, key_types, reverse=reverse)
                            for gc, ac in product(mapping_chains, atomic_chains)),
        chain.from_iterable(_test_cases(gc, ac, reverse=reverse)
                            for gc, ac in product(generic_chains, atomic_chains)),
        chain.from_iterable(ordered_pairs(reversed(tups) if reverse else tups) for tups in tuple_chains + callable_chains),
    )))


@pytest.mark.parametrize("t1,t2", all_test_cases())
def test_issubclass_generic_pos(t1, t2):
    assert issubclass_generic(t1, t2)


@pytest.mark.parametrize("t1,t2", all_test_cases(reverse=True))
def test_issubclass_generic_neg(t1, t2):
    assert not issubclass_generic(t1, t2)


@pytest.mark.parametrize("type_", list(set(chain.from_iterable(chain(atomic_chains,
                                                                     generic_chains,
                                                                     mapping_chains,
                                                                     callable_chains)))))
def test_deconstruct_reconstruct_type(type_):
    assert reconstruct_generic(deconstruct_generic(type_)) == type_


@pytest.mark.parametrize("generic,type_", product(
    [Tuple, Collection, Counter, Iterable, Callable[[K], K]],
    set(chain.from_iterable(chain(atomic_chains,
                                  generic_chains,
                                  mapping_chains,
                                  callable_chains)))))
def test_deconstruct_reconstruct_type(generic, type_):
    t = generic[type_]
    assert reconstruct_generic(deconstruct_generic(t)) == t


@pytest.mark.parametrize("generic,type_", generic_constructors)
def test_get_constructor_for(generic, type_):
    assert get_constructor_for(generic) is type_


@pytest.mark.parametrize("ref,type_", type_refs)
def test_eval_forward_refs(ref, type_):
    evaled = eval_forward_refs(ref, globals())
    assert evaled == type_


@pytest.mark.parametrize("tvar,constraint", tvars_and_constraint_types(key_types))
def test_constraint_type(tvar, constraint):
    assert constraint_type(tvar) == constraint


@pytest.mark.parametrize("base,type_", abstract_class_test_cases(abstract_classes_pos))
def test_abstract_types_pos(base, type_):
        assert issubclass(type_, base)


@pytest.mark.parametrize("base,type_", abstract_class_test_cases(abstract_classes_neg))
def test_abstract_types_neg(base, type_):
        assert not issubclass(type_, base)


@pytest.mark.parametrize("base,type_", product([Mapping[int, str], Mapping[int, MyStr], Collection[int]],
                                               [Baz, Boom]))
def test_transitive_generic(base, type_):
    assert issubclass_generic(type_, base)


@pytest.mark.parametrize("type1,type2,pos", [(Pattern[str], Pattern, True), (Pattern[bytes], Pattern, True),
                                             (Pattern, Pattern[str], False), (Pattern, Pattern[bytes], False),
                                             (Pattern[str], Pattern[bytes], False),
                                             (Pattern[bytes], Pattern[str], False)])
def test_py36_fake_types(type1, type2, pos):
    if pos:
        assert issubclass_generic(type1, type2)
    else:
        assert not issubclass_generic(type1, type2)
