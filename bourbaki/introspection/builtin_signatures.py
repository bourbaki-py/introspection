"""Signatures for builtins - these raise error on call to inspect.signature"""
from numbers import Number
from typing import (
    Iterable,
    Iterator,
    Collection,
    Callable,
    Sequence,
    Hashable,
    List,
    Tuple,
    Set,
    FrozenSet,
    Type,
    Union,
    Any,
    SupportsAbs,
    TypeVar,
)

A = TypeVar("A", bound=SupportsAbs)
N = TypeVar("N", bound=Number)
H = TypeVar("H", bound=Hashable)
T = TypeVar("T")
O = TypeVar("O")


# We use these for instance checks on builtin _types_ as instances of callable types,
# i.e. isinstance_generic(int, Callable[[object], int]) == True
# and that is why those with overloaded signatures are represented as _lists_ rather than Unions.
# A generic subclass check with a Union in the first position requires _all_ types in the union
# to be subtypes of the type in the second position
builtin_callable_types = {
    int: [
        Callable[[Union[Number, str]], int],
        Callable[[Union[str, bytes, bytearray], int], int],
    ],
    float: Callable[[Union[Number, str]], float],
    complex: [Callable[[str], complex], Callable[[Number, Number], complex]],
    bool: Callable[[Any], bool],
    # leaving out abs - generic in the return type
    all: Callable[[Iterable], bool],
    any: Callable[[Iterable], bool],
    ascii: Callable[[Any], str],
    bin: Callable[[int], str],
    bytes: [
        Callable[[Union[Iterable[int], int, bytes, bytearray, memoryview]], bytes],
        Callable[[str, str], bytes],
    ],
    bytearray: [
        Callable[[Union[Iterable[int], int, bytes, bytearray, memoryview]], bytearray],
        Callable[[str, str], bytearray],
    ],
    callable: Callable[[Any], bool],
    chr: Callable[[int], str],
    # leaving out compile - too complex and of questionable use
    # leaving out delattr - only for side effects
    dir: Callable[[Any], List[str]],
    # leaving out divmod - generic in the return type
    enumerate: [
        Callable[[Iterable[T]], Iterable[Tuple[int, T]]],
        Callable[[Iterable[T], int], Iterable[Tuple[int, T]]],
    ],
    eval: Callable[[str], Any],
    # leaving out exec - only for side effects
    # leaving out exit - only for side effects
    filter: Callable[[Callable[[T], bool], Iterable[T]], Iterable[T]],
    frozenset: Callable[[Iterable[H]], FrozenSet[H]],
    # leaving out getattr - no constraint on return type
    # leaving out getattr - no constraint on values of return type
    hasattr: Callable[[Any, str], bool],
    hash: Callable[[Hashable], int],
    hex: Callable[[int], str],
    id: Callable[[Any], int],
    isinstance: Callable[[Any, Type], bool],
    issubclass: Callable[[Type, Type], bool],
    iter: Callable[[Iterable[T]], Iterator[T]],
    len: Callable[[Collection], int],
    list: Callable[[Iterable[T]], List[T]],
    map: Callable[[Callable[[T], O], Iterable[T]], Iterator[O]],
    max: Callable[[Iterable[N]], N],
    min: Callable[[Iterable[N]], N],
    next: Callable[[Iterator[T]], T],
    oct: Callable[[int], str],
    ord: Callable[[str], int],
    pow: Callable[[N, N], N],
    repr: Callable[[Any], str],
    reversed: Callable[[Sequence[T]], Iterator[T]],
    set: Callable[[Iterable[H]], Set[H]],
    # leaving out setattr - only for side effects
    sorted: Callable[[Iterable[T]], List[T]],
    repr: Callable[[Any], str],
    sum: [Callable[[Iterable[N]], N], Callable[[Iterable[N], N], N]],
    tuple: Callable[[Iterable[T]], Tuple[T, ...]],
    type: Callable[[Any], Type],
    # leaving out vars - no constraint on values of return type
    # leaving out zip - variadic
}
