# coding:utf-8
from typing import List, Tuple, Deque, Iterable, Callable, Dict, Type, Union, Optional, Generic
import re
from collections import deque
from tempfile import mktemp
from itertools import repeat, chain, product, combinations, filterfalse
from graphviz import Digraph as Dot
from networkx import DiGraph, induced_subgraph, transitive_reduction, neighbors, reverse_view
from .debug import DEBUG
from .wrappers import const
from .utils import name_of
from .types import (issubclass_generic, deconstruct_generic, reconstruct_generic, to_type_alias,
                    reparameterized_bases, get_generic_origin, get_generic_args, is_generic_type)

Signature = Tuple[type, ...]


class AmbiguousSignatureError(TypeError):
    def __str__(self):
        return "The signatures {} are ambiguous".format(self.args)


class UnknownSignature(TypeError, NotImplementedError):
    def __str__(self):
        dispatcher, sig = self.args
        return "The dispatcher {} has no functions registered for signature {}".format(dispatcher, sig)


class AmbiguousResolutionError(ValueError):
    def __str__(self):
        dispatcher, sig, sigs = self.args
        return ("The dispatcher {} resolves the signature {} to multiple ambiguous signatures: {}"
                .format(dispatcher, sig, sigs))


def refines(sig1: Signature, sig2: Signature) -> bool:
    return len(sig1) == len(sig2) and all(issubclass_generic(t1, t2) for t1, t2 in zip(sig1, sig2))


def generalizes(sig1: Signature, sig2: Signature) -> bool:
    return len(sig1) == len(sig2) and all(issubclass_generic(t2, t1) for t1, t2 in zip(sig1, sig2))


def bottoms(d: DiGraph):
    return [n for n, deg in d.in_degree() if deg == 0]


def tops(d: DiGraph):
    return [n for n, deg in d.out_degree() if deg == 0]


def most_specific(d: DiGraph, sigs: Optional[List[Signature]]=None):
    if sigs is not None:
        d = induced_subgraph(d, sigs)
    return bottoms(d)


def most_general(d: DiGraph, sigs: Optional[List[Signature]]=None):
    if sigs is not None:
        d = induced_subgraph(d, sigs)
    return tops(d)


def verbose_call(f):
    def verbose_f(*args):
        result = f(*args)
        print(call_repr(f, args) + " -> {}".format(result))
        return result
    return verbose_f


def call_repr(f, args, to_str=repr):
    return "{}({})".format(name_of(f), ', '.join(map(to_str, args)))


def type_str(t):
    return re.sub(r'\btyping\.\b', '', str(t))


def _depth_first(dag: DiGraph, root: Signature, sig: Signature, memo: set,
                 edge_predicate: Callable[[Signature, Signature], bool]=refines) -> Iterable[Signature]:
    for node in filterfalse(memo.__contains__, chain((root,), neighbors(dag, root))):
        memo.add(node)
        if edge_predicate(sig, node):
            yield node
            memo.update(dag.successors(node))
        else:
            yield from _depth_first(dag, node, sig, memo, edge_predicate)


def _breadth_first(dag: DiGraph, roots: Deque[Signature], sig: Signature, memo: set,
                   edge_predicate: Callable[[Signature, Signature], bool]=refines) -> Iterable[Signature]:
    while roots:
        node = roots.popleft()
        if node not in memo:
            memo.add(node)
            if edge_predicate(sig, node):
                yield node
                memo.update(dag.successors(node))
            else:
                roots.extend(neighbors(dag, node))


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

    def __init__(self, name, isolated_bases: Optional[List[Type]]=None):
        self.name = self.__name__ = name
        self._cache = {}
        self._sig_cache = {}
        self.dag = DiGraph()
        self.funcs = {}
        if isolated_bases:
            self.isolated_bases = set(t if isinstance(t, tuple) else (t,) for t in isolated_bases)
        else:
            self.isolated_bases = None

    def __str__(self):
        return call_repr(type(self), (self.__name__,))

    def register(self, *sig, debug: bool=DEBUG, as_const: bool=False):
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

    def register_all(self, *sigs: Union[Signature, Type], debug: bool=DEBUG, as_const: bool=False):
        def dec(f):
            for s in sigs:
                if not isinstance(s, (tuple, list)):
                    s = (s,)
                self.register(*s, debug=debug, as_const=as_const)(f)
            return f

        return dec

    def register_from_mapping(self, sigmap: Dict[Union[Signature, Type], Callable],
                              debug: bool=DEBUG, as_const: bool=False):
        for s, f in sigmap.items():
            if not isinstance(s, (tuple, list)):
                s = (s,)
            _ = self.register(*s, debug=debug, as_const=as_const)(f)

        return self

    def insert(self, sig, f, *, debug=DEBUG):
        if sig not in self.funcs:
            dag = self.dag
            order = len(dag)

            if len(dag) > 0:
                parents = list(self._resolve_iter(sig, debug=debug))
                children = list(self._resolve_iter(sig, reverse=True, debug=debug))

                parents = most_specific(dag, parents)
                children = most_general(dag, children)

                dag.add_edges_from(zip(repeat(sig), parents))
                dag.add_edges_from(zip(children, repeat(sig)))
                dag.remove_edges_from(product(children, parents))

                self.bottoms.difference_update(parents)
                if not children:
                    self.bottoms.add(sig)
                self.tops.difference_update(children)
                if not parents:
                    self.tops.add(sig)

            dag.add_node(sig, order=order)

        self.funcs[sig] = f
        return self

    @property
    def bottoms(self):
        leaves = self._bottoms
        if leaves is None:
            self._bottoms = leaves = set(bottoms(self.dag))
        return leaves

    @property
    def tops(self):
        leaves = self._tops
        if leaves is None:
            self._tops = leaves = set(tops(self.dag))
        return leaves

    def resolve(self, sig, *, debug: bool=False):
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

    def _resolve_iter(self, sig, reverse=False, memo=None, debug=DEBUG, depth_first=False):
        if reverse:
            dag = reverse_view(self.dag)
            initial = self.tops
            edge_predicate = generalizes
        else:
            dag = self.dag
            initial = self.bottoms
            edge_predicate = refines

        if debug:
            edge_predicate = verbose_call(edge_predicate)

        if memo is None:
            memo = set()

        roots = (s for s in initial if len(s) == len(sig))
        if depth_first:
            for extrema in roots:
                yield from _depth_first(dag, extrema, sig, memo, edge_predicate)
        else:
            yield from _breadth_first(dag, deque(roots), sig, memo, edge_predicate)

    def _most_specific(self, nodes: List[Signature], sig: Signature) -> Signature:
        if len(nodes) == 0:
            raise UnknownSignature(self, sig)
        elif len(nodes) > 1:
            g = DiGraph()
            g.add_nodes_from(nodes)
            for edge in combinations(nodes, 2):
                if refines(*edge):
                    g.add_edge(*edge)
                elif refines(*reversed(edge)):
                    g.add_edge(edge[1], edge[0])

            best = most_specific(g)

            if self.isolated_bases:
                best_ = self.isolated_bases.intersection(best)
                if best_:
                    best = list(best_)

            if len(best) > 1:
                raise AmbiguousResolutionError(self, sig, best)
        else:
            best = nodes

        return best[0]

    def visualize(self, target_sig=None, view=True, path=None, debug=False, title: Optional[str]=None, format_="svg",
                  highlight_color="green", highlight_color_error="red", highlight_style="filled"):
        if path is None:
            path = mktemp(suffix='-{}.gv'.format(self.__name__))

        if title is None:
            title = ("Signature DAG for {} {} with {} signatures"
                     .format(type(self).__name__, self.__name__, len(self.dag)))

        d = Dot(self.__name__, format=format_)
        d.attr(label=title)
        # don't remove edges in debug mode
        dag = self.dag if debug else transitive_reduction(self.dag)
        d.edges((str(b), str(a)) for a, b in dag.edges)

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
                label = "{}: {}".format(metadata['order'], label)
            attrs = highlight if sig in highlight_sigs else no_highlight
            d.node(str(sig), label=label, **attrs)

        if view:
            d.render(path, view=view, cleanup=True)
        return d

    def cleanup(self, clear_cache=False):
        dag = transitive_reduction(self.dag)
        dag.add_nodes_from(self.dag.nodes(data=True))
        self.dag = dag
        if clear_cache:
            self._cache.clear()
        return self

    def __getstate__(self):
        state = self.__dict__.copy()
        funcs, dag, cache, sig_cache, bot, top = (state.pop(attr) for attr in
                                                  ["funcs", "dag", "_cache", "_sig_cache", "_bottoms", "_tops"])
        funcs, cache = (_deconstruct_mapping(m) for m in (funcs, cache))
        bot, top = (_deconstruct_collection(c) for c in (bot, top))
        sig_cache = _deconstruct_mapping(sig_cache, values=True)
        dag = transitive_reduction(dag)
        edges = [(_deconstruct_signature(t1), _deconstruct_signature(t2)) for t1, t2 in dag.edges]
        nodes = [(_deconstruct_signature(t), data) for t, data in dag.nodes(data=True)]
        state["funcs"], state["dag"], state["_cache"], state["_sig_cache"], state["_bottoms"], state["_tops"] = \
            funcs, (nodes, edges), cache, sig_cache, bot, top
        return state

    def __setstate__(self, state):
        funcs, (nodes, edges), cache, sig_cache, bot, top = (
            state.pop(attr) for attr in ["funcs", "dag", "_cache", "_sig_cache", "_bottoms", "_tops"])
        state["funcs"], state["_cache"] = (_reconstruct_mapping(m) for m in (funcs, cache))
        state["_sig_cache"] = _reconstruct_mapping(sig_cache, values=True)
        state["_bottoms"], state["_tops"] = (_reconstruct_collection(c, set) for c in (bot, top))
        dag = DiGraph((_reconstruct_signature(t1), _reconstruct_signature(t2)) for t1, t2 in edges)
        dag.add_nodes_from((_reconstruct_signature(t), data) for t, data in nodes)
        state["dag"] = dag
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
