import io
import pickle
import typing

from graphviz import Digraph
import pytest

from bourbaki.introspection.generic_dispatch import GenericTypeLevelSingleDispatch

type_repr = GenericTypeLevelSingleDispatch("type_repr", isolated_bases=[typing.Union])


@type_repr.register(typing.Any)
def type_repr_base(t):
    try:
        return t.__name__
    except AttributeError:
        return str(t).replace("typing.", "")


type_repr.register(str, as_const=True)('""')


@type_repr.register(typing.Collection)
def type_repr_collection(t, *args):
    name = type_repr_base(t)
    if not args or all(a in (typing.Any, object) for a in args):
        return name
    return "{}[{}]".format(name, ", ".join(map(type_repr, args)))


@type_repr.register(typing.AbstractSet)
def type_repr_set(s, *args):
    return "{{{}}}".format(", ".join(map(type_repr, args)))


@type_repr.register(typing.Tuple)
def type_repr_tuple(t, *args):
    return "({})".format(", ".join(map(type_repr, args)))


@type_repr.register(typing.Mapping)
def type_repr_collection(t, *args):
    name = type_repr_base(t)
    if not args or all(a in (typing.Any, object) for a in args):
        return name
    return "{}[{}]".format(name, ":".join(map(type_repr, args)))


@type_repr.register(typing.Callable)
def type_repr_callable(t, sig, ret):
    return "({}) -> {}".format(", ".join(map(type_repr, sig)), type_repr(ret))


@type_repr.register(typing.Union)
def type_repr_union(u, *types):
    return " | ".join(map(type_repr, types))


@pytest.mark.parametrize(
    "t,repr_",
    [
        (list, "List"),
        (typing.List[int], "List[int]"),
        (typing.Dict[str, int], 'Dict["":int]'),
        (typing.Dict[str, typing.Union[complex, bytes]], 'Dict["":complex | bytes]'),
        (typing.Tuple[int, str, complex], '(int, "", complex)'),
        (typing.Set[typing.Tuple[int]], "{(int)}"),
        (
            typing.Callable[[typing.Dict[str, object], str], object],
            '(Dict["":Any], "") -> Any',
        ),
    ],
)
def test_type_repr(t, repr_):
    type_repr.visualize(t, view=False)
    assert type_repr(t) == repr_


@pytest.mark.parametrize(
    "t",
    [
        typing.Dict[str, int],
        typing.Dict[str, typing.Union[complex, bytes]],
        typing.Tuple[int, str, complex],
        typing.Set[typing.Tuple[int]],
        typing.Callable[[typing.Dict[str, object], str], object],
    ],
)
def test_viz(t):
    g = type_repr.visualize(t, view=False, title="resolution for {}".format(t))
    assert isinstance(g, Digraph)
