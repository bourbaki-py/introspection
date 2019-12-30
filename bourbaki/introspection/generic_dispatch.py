# coding:utf-8
from typing import List, Tuple, Callable, Dict, Type, Union, Optional, Generic
import re
from tempfile import mktemp
from itertools import chain, combinations
from .debug import DEBUG
from .wrappers import const
from .utils import name_of
from .types import (
    issubclass_generic,
    deconstruct_generic,
    reconstruct_generic,
    to_type_alias,
    reparameterized_bases,
    get_generic_origin,
    get_generic_args,
    is_generic_type,
)

Signature = Tuple[type, ...]


class UnknownSignature(TypeError, NotImplementedError):
    def __str__(self):
        dispatcher, sig = self.args
        return "The dispatcher {} has no functions registered for signature {}".format(
            dispatcher, sig
        )


class AmbiguousResolutionError(ValueError):
    def __str__(self):
        dispatcher, sig, sigs = self.args
        return "The dispatcher {} resolves the signature {} to multiple ambiguous signatures: {}".format(
            dispatcher, sig, sigs
        )


def refines(sig1: Signature, sig2: Signature) -> bool:
    return len(sig1) == len(sig2) and all(
        issubclass_generic(t1, t2) for t1, t2 in zip(sig1, sig2)
    )


def generalizes(sig1: Signature, sig2: Signature) -> bool:
    return len(sig1) == len(sig2) and all(
        issubclass_generic(t2, t1) for t1, t2 in zip(sig1, sig2)
    )


def verbose_call(f):
    def verbose_f(*args):
        result = f(*args)
        print(call_repr(f, args) + " -> {}".format(result))
        return result

    return verbose_f


def call_repr(f, args, to_str=repr):
    return "{}({})".format(name_of(f), ", ".join(map(to_str, args)))


def type_str(t):
    return re.sub(r"\btyping\.\b", "", str(t))


def _deconstruct_signature(sig):
    return tuple(map(deconstruct_generic, sig))


def _reconstruct_signature(sig):
    return tuple(map(reconstruct_generic, sig))


def _deconstruct_collection(coll):
    return [_deconstruct_signature(sig) for sig in coll]


def _reconstruct_collection(coll, type_):
    return type_(_reconstruct_signature(sig) for sig in coll)


def _deconstruct_mapping(sigmap, values=False):
    decons_val = _deconstruct_signature if values else lambda x: x
    return [(_deconstruct_signature(sig), decons_val(v)) for sig, v in sigmap.items()]


def _reconstruct_mapping(sigmap, type_=dict, values=False):
    recons_val = _deconstruct_signature if values else lambda x: x
    return type_((_reconstruct_signature(sig), recons_val(v)) for sig, v in sigmap)


# Dispatchers


class GenericTypeLevelDispatch:
    _bottoms = None
    _tops = None

    def __init__(self, name, isolated_bases: Optional[List[Type]] = None):
        self.name = self.__name__ = name
        self._cache = {}
        self._sig_cache = {}
        # self.dag = DiGraph()
        self.funcs = {}
        if isolated_bases:
            self.isolated_bases = set(
                t if isinstance(t, tuple) else (t,) for t in isolated_bases
            )
        else:
            self.isolated_bases = None

    def __str__(self):
        return call_repr(type(self), (self.__name__,))

    def register(self, *sig, debug: bool = DEBUG, as_const: bool = False):
        if debug:
            print(call_repr("{}.register".format(self.__name__), sig))

        sig = tuple(map(to_type_alias, sig))

        def dec(f):
            if as_const:
                f = const(f)

            self.insert(sig, f, debug=debug)
            if debug:
                print()
            if debug > 1:
                self.visualize(view=True, debug=True, target_sig=sig)

            return f

        return dec

    def register_all(
        self, *sigs: Union[Signature, Type], debug: bool = DEBUG, as_const: bool = False
    ):
        def dec(f):
            for s in sigs:
                if not isinstance(s, (tuple, list)):
                    s = (s,)
                self.register(*s, debug=debug, as_const=as_const)(f)
            return f

        return dec

    def register_from_mapping(
        self,
        sigmap: Dict[Union[Signature, Type], Callable],
        debug: bool = DEBUG,
        as_const: bool = False,
    ):
        for s, f in sigmap.items():
            if not isinstance(s, (tuple, list)):
                s = (s,)
            _ = self.register(*s, debug=debug, as_const=as_const)(f)

        return self

    def insert(self, sig, f, *, debug=DEBUG):
        if debug:
            print("Registering function {} for signature {}".format(f, sig))
        self.funcs[sig] = f
        return self

    def resolve(self, sig, *, debug: bool = False):
        if debug:
            print("Resolving signature {} for dispatcher {}".format(sig, self))
        f = self._cache.get(sig)
        if f is None:
            f = self.funcs.get(sig)
            if f is None:
                nodes = list(self._resolve_iter(sig, debug=debug))
                best = self._most_specific(nodes, sig)
                f = self.funcs[best]
            else:
                if debug:
                    print("Found signature {} in {}.funcs".format(sig, self.__name__))
                best = sig

            self._sig_cache[sig] = best
            self._cache[sig] = f
        elif debug:
            print("Found signature {} in {}._cache".format(sig, self.__name__))
        return f

    def _resolve_iter(self, sig, debug=DEBUG):
        edge_predicate = verbose_call(refines) if debug else refines
        return (s for s in self.funcs if edge_predicate(sig, s))

    def _most_specific(self, nodes: List[Signature], sig: Signature) -> Signature:
        if len(nodes) == 0:
            raise UnknownSignature(self, sig)
        elif len(nodes) > 1:
            refined = set()
            for s1, s2 in combinations(nodes, 2):
                if refines(s1, s2):
                    refined.add(s2)
                elif refines(s2, s1):
                    refined.add(s1)

            best = [node for node in nodes if node not in refined]

            if self.isolated_bases:
                best_ = self.isolated_bases.intersection(best)
                if best_:
                    best = list(best_)

            if len(best) > 1:
                raise AmbiguousResolutionError(self, sig, best)
        else:
            best = nodes

        return best[0]

    def visualize(
        self,
        target_sig=None,
        view=True,
        path=None,
        debug=False,
        title: Optional[str] = None,
        format_="svg",
        highlight_color="green",
        highlight_color_error="red",
        highlight_style="filled",
    ):
        try:
            from graphviz import Digraph as Dot
            from networkx import (
                DiGraph,
                induced_subgraph,
                transitive_reduction,
                neighbors,
            )
        except ImportError:
            raise ImportError(
                "the visualize method requires graphviz and networkx>=2.0"
            )

        dag = self.dag()

        if title is None:
            title = "Signature DAG for {} {} with {} signatures".format(
                type(self).__name__, self.__name__, len(dag)
            )

        d = Dot(self.__name__, format=format_)
        d.attr(label=title)
        d.edges((str(b), str(a)) for a, b in dag.edges)

        if path is None:
            path = mktemp(suffix="-{}.gv".format(self.__name__))

        if target_sig is not None:
            if not isinstance(target_sig, tuple):
                target_sig = (target_sig,)

            try:
                # side effect: populate the cache
                _ = self.resolve(target_sig)
            except AmbiguousResolutionError:
                highlight_color = highlight_color_error
                highlight_sigs = list(self._resolve_iter(target_sig))
            else:
                highlight_sigs = [self._sig_cache[target_sig]]
        else:
            highlight_sigs = []

        no_highlight = {}
        highlight = dict(color=highlight_color, style=highlight_style)
        for sig, metadata in dag.nodes(data=True):
            f = self.funcs[sig]
            label = call_repr(f, sig, to_str=type_str)
            if debug:
                label = "{}: {}".format(metadata["order"], label)
            attrs = highlight if sig in highlight_sigs else no_highlight
            d.node(str(sig), label=label, **attrs)

        if view:
            d.render(path, view=view, cleanup=True)
        return d

    def dag(self):
        try:
            from networkx import DiGraph, transitive_reduction
        except ImportError:
            raise ImportError("the dag method requires networkx>=2.0")
        dag = DiGraph()
        for order, node in enumerate(self.funcs):
            dag.add_node(node, order=order)
        for sig1, sig2 in combinations(self.funcs, 2):
            if refines(sig1, sig2):
                dag.add_edge(sig1, sig2)
            elif refines(sig2, sig1):
                dag.add_edge(sig2, sig1)
        return transitive_reduction(dag)

    def __getstate__(self):
        state = self.__dict__.copy()
        funcs, cache, sig_cache = (
            state.pop(attr) for attr in ["funcs", "_cache", "_sig_cache"]
        )

        funcs, cache = (_deconstruct_mapping(m) for m in (funcs, cache))
        sig_cache = _deconstruct_mapping(sig_cache, values=True)
        state["funcs"], state["_cache"], state["_sig_cache"] = funcs, cache, sig_cache
        return state

    def __setstate__(self, state):
        funcs, cache, sig_cache = (
            state.pop(attr) for attr in ["funcs", "_cache", "_sig_cache"]
        )
        state["funcs"], state["_cache"] = (
            _reconstruct_mapping(m) for m in (funcs, cache)
        )
        state["_sig_cache"] = _reconstruct_mapping(sig_cache, values=True)
        self.__dict__.update(state)

    def __call__(self, *types, **kwargs):
        f = self.resolve(types)
        return f(*types, **kwargs)


class GenericTypeLevelSingleDispatch(GenericTypeLevelDispatch):
    """Singly-dispatched version"""

    def __call__(self, type_, **kwargs):
        sig = (type_,)
        f = self.resolve(sig)
        org = get_generic_origin(type_)
        # make sure we pass the args for the correct type to the registered function
        # by ascending the generic mro;
        # i.e. Mapping[K, V] is also a Collection[K], and if the user registered for the latter case, we want to pass
        # the type args corresponding to that case
        resolved_type = self._sig_cache[sig][0]
        args = resolved_type_args(type_, resolved_type)
        # pass the args in with the constructor for ease of implementation
        return f(org, *args, **kwargs)


def resolved_type_args(type_, resolved_type):
    if is_generic_type(resolved_type) and resolved_type is not Generic:
        # only reparameterize for concrete generics
        resolved_org = get_generic_origin(resolved_type)
        for t in chain((type_,), reparameterized_bases(type_)):
            if get_generic_origin(t) is resolved_org:
                resolved_type = t
                break
    else:
        # If Generic itself was registered, take the type args directly from the type, not its resolved base
        resolved_type = type_

    return get_generic_args(resolved_type, evaluate=True)
