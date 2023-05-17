# coding:utf-8
try:
    from importlib.metadata import PackageNotFoundError  # type: ignore
    from importlib.metadata import version  # type: ignore
except ImportError:  # pragma: no cover
    from importlib_metadata import version, PackageNotFoundError  # type: ignore

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
from .references import find_refs, find_refs_by_id, find_refs_by_size, find_refs_by_type
from .simple_repr import with_simple_repr
from .subclassing import subclass_method, subclass_mutator_method
from .typechecking import type_checker
from .types import issubclass_generic
from .wrappers import cached_getter, lru_cache_sig_preserving

try:
    __version__ = version(__name__)
except PackageNotFoundError:  # pragma: no cover
    try:
        __version__ = version(__name__.replace(".", "-"))
        # Due to interaction between Poetry's name normalization and Python < 3.9
    except PackageNotFoundError:  # pragma: no cover
        __version__ = "unknown"
