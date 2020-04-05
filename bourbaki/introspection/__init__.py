# coding:utf-8
from .classes import (
    all_subclasses,
    classpath,
    inheritance_hierarchy,
    render_inheritance_hierarchy,
)
from .docstrings import parse_docstring
from .generic_dispatch import GenericTypeLevelDispatch, GenericTypeLevelSingleDispatch
from .imports import import_object, lazy_imports
from .polymorphism import MultipleDispatchMethod, TypeLevelDispatch
from .prettyprint import fmt_pyobj
from .references import find_refs, find_refs_by_type, find_refs_by_id, find_refs_by_size
from .simple_repr import with_simple_repr
from .subclassing import subclass_method, subclass_mutator_method
from .typechecking import type_checker
from .types import issubclass_generic
from .wrappers import cached_getter, lru_cache_sig_preserving

__version__ = "0.5.7"
