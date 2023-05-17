# coding:utf-8
from typing import Tuple, Union
import typing
import builtins
from typing import Callable
import ast
from functools import singledispatch
import os
import re
import sys
from types import MethodType, FunctionType
from functools import partial, update_wrapper
from textwrap import indent
from inspect import stack
from importlib import import_module
from logging import getLogger
from .utils import py_dot_name_re
from .types.compat import typing_to_stdlib_constructor, ForwardRef, typetypes

# we'll import this on call to import_type to avoid a circular import
eval_type_tree = None

py_dot_name_regex = re.compile(py_dot_name_re)

logger = getLogger(__name__)

ModuleType = type(os)
MODULE_ATTRS = set(dir(ModuleType))
ALL = "*"


def import_object(classpath):
    """
    Same semantics as importlib.import_module, but for any object in the recursive namespace of a module

    :param classpath: a '.'-separated name referencing an object in the current environment, such as 'os.path.isdir'
    :return: the object corresponding to the classpath in the current environment
    """
    if classpath == "...":
        return Ellipsis

    names = classpath.split(".")

    i, obj = 0, None
    for i, name in enumerate(names, 1):
        modpath = ".".join(names[:i])
        try:
            # try to import a module from a qualified path
            obj = import_module(modpath)
        except ImportError as e:
            # no module found; if we're at the first entry, check for a builtin object
            if i == 1:
                try:
                    obj = getattr(builtins, modpath)
                except AttributeError:
                    raise e
            else:
                # otherwise, we've run out of modules; switch to looking up attributes;
                # the current index should be retried for an attribute lookup
                i = i - 1
            break

    for name in names[i:]:
        obj = getattr(obj, name)

    return obj


def import_type(parameterized_classpath) -> type:
    if isinstance(parameterized_classpath, ForwardRef):  # pragma: no cover
        parameterized_classpath = parameterized_classpath.__forward_arg__

    if py_dot_name_regex.fullmatch(parameterized_classpath):
        # prevent an ast.parse call if it's a simple case
        t = _eval_type_tree_expr(parameterized_classpath)
    else:
        tree = ast.parse(parameterized_classpath, mode="eval").body
        expr = _to_typetree_expr(tree)
        t = _eval_type_tree_expr(expr)

    if not isinstance(t, (type, typetypes)):
        raise TypeError(
            "import of {} yielded object of type {}, not a type".format(
                parameterized_classpath, type(t)
            )
        )
    return t


def _eval_type_tree_expr(expr: Union[str, Tuple[str, ...]]) -> type:
    # ugly local import but prevents circular imports
    global eval_type_tree
    if eval_type_tree is None:
        from .types import eval_type_tree

    if isinstance(expr, str):
        # allow typing aliases to be referenced directly without qualification
        t = getattr(typing, expr, None)
        if t is None:
            t = import_object(expr)
        return t
    types = tuple(map(_eval_type_tree_expr, expr))
    return eval_type_tree(types)


@singledispatch
def _to_typetree_expr(node) -> Union[str, Tuple[str, ...]]:
    raise SyntaxError("{} is not a valid python generic type reference".format(node))


@singledispatch
def _to_classpath(node) -> str:
    raise SyntaxError("{} is not a valid python classpath".format(node))


@singledispatch
def _to_index_expr(node):
    raise SyntaxError(
        "{} is not a valid index value for the parameters of a parameterized type expression".format(
            node
        )
    )


@_to_typetree_expr.register(ast.Subscript)
def _to_typetree_expr_subscript(
    node: ast.Index
) -> Tuple[Union[str, Tuple[str, ...]], ...]:
    cp = _to_classpath(node.value)
    index_cps = _to_index_expr(node.slice.value)
    return (cp, *index_cps)


@_to_classpath.register(ast.Attribute)
@_to_typetree_expr.register(ast.Attribute)
def _to_classpath_attr(node: ast.Attribute) -> str:
    return ".".join((_to_classpath(node.value), node.attr))


@_to_classpath.register(ast.Name)
@_to_typetree_expr.register(ast.Name)
def _to_classpath_name(node: ast.Name) -> str:
    return node.id


@_to_index_expr.register(ast.Attribute)
@_to_index_expr.register(ast.Name)
def _to_index_expr_ref(node: Union[ast.Attribute, ast.Name]) -> Tuple[str, ...]:
    return (_to_classpath(node),)


@_to_index_expr.register(ast.Ellipsis)
def _to_index_expr_ellipsis(node: ast.Ellipsis) -> Tuple[str, ...]:
    return ("...",)


if sys.version_info >= (3, 8):
    # python 3.8 made Ellipsis an instance of ast.Constant
    @_to_index_expr.register(ast.Constant)
    def _to_index_expr_ellipsis_constant(node: ast.Constant) -> Tuple[str, ...]:
        if node.value is Ellipsis:
            return ("...",)
        else:
            raise SyntaxError(
                "{} is not a valid subexpression of a parameterized type expression".format(
                    node.value
                )
            )


@_to_index_expr.register(ast.Tuple)
def _to_index_expr_tuple(node: ast.Tuple) -> Tuple[Union[str, Tuple[str, ...]], ...]:
    return tuple(map(_to_index_expr, node.elts))


@_to_index_expr.register(ast.Subscript)
def _to_index_expr_subscript(
    node: ast.Subscript
) -> Tuple[Union[str, Tuple[str, ...]], ...]:
    return (_to_typetree_expr(node),)


def lazy_imports(*modulespecs):
    """require a function to perform imports at call time (for speeding up app start-up).
    each `modulespec` is a tuple or a str:
    - if a str or length-1 tuple, import the qualified module named by the string
    - if a 2-tuple, import names (2nd) from the module (1st) as in `from X import Y, Z`
      if the 2nd entry is a dict, this is equivalent to `from X import Key1 as Val1, Key2 as Val2, ...`
    - if a 3-tuple, the 2nd entry should be none (no absolute name imports), and the 3rd entry should
      specify a renaming of the imported module, as in `import X as Y`
    """
    return partial(LazyImportsCallable, modulespecs)


class _ImportSpec:
    names = modname = asname = None

    def __init__(self, modname, names=None, asname=None):
        if names is None:
            tup = (modname,) if asname is None else (modname, as_, asname)
        elif asname is None:
            tup = (modname, names)
        else:
            tup = (modname, names, asname)
        self.import_spec = _validate_module_spec(tup, allow_tuple=True)
        self.names, self.modname, self.asname = names, modname, asname

    def __iter__(self):
        # for *args unpacking to _import
        return iter(self.import_spec)


class import_:
    def __init__(self, modname):
        self.modname = modname

    def as_(self, rename):
        return _ImportSpec(self.modname, as_, rename)


# alias
module_ = import_


class from_:
    def __init__(self, modname):
        self.modname = modname

    def import_(self, *args, **renames):
        renames.update(zip(args, args))
        return _ImportSpec(self.modname, renames)


class as_:
    pass


class LazyImportsCallable:
    __wrapped__ = None

    def __init__(self, modulespecs, func: Callable):
        if not callable(func):  # pragma: no cover
            raise TypeError("func must be callable; got {}".format(type(func)))
        if not hasattr(func, "__globals__"):
            raise AttributeError(
                "func must have a __globals__ attribute; type {} does not".format(
                    type(func)
                )
            )
        if isinstance(modulespecs, str):
            modulespecs = (modulespecs,)

        self.__imports__ = list(map(_validate_module_spec, modulespecs))
        self.__called__ = False
        self.__func__ = func
        # this sets __wrapped__
        update_wrapper(self, func)

    def __call__(self, *args, **kwargs):
        f = self.__func__
        if not self.__called__:
            globals_ = get_globals(f)
            for spec in self.__imports__:
                _import(*spec, globals_=globals_)
        return self.__wrapped__(*args, **kwargs)

    def __get__(self, instance, owner):
        if instance is None:
            return self
        f = MethodType(self.__call__, instance)
        setattr(instance, self.__name__, f)
        return f


def get_globals(callable_):
    if isinstance(callable_, type):
        try:
            mod = import_module(callable_.__module__)
        except ImportError:
            try:
                f = next(
                    f
                    for f in callable_.__dict__.values()
                    if isinstance(f, FunctionType)
                )
            except StopIteration:  # pragma: no cover
                raise AttributeError(
                    "cannot extract globals dict from class {} with no locally defined methods "
                    "and non-importable module {}".format(
                        callable_, callable_.__module__
                    )
                )
        else:
            return vars(mod)
    else:
        f = callable_

    try:
        g = f.__globals__
    except AttributeError:
        raise AttributeError("could not find __globals__ attribute on {}".format(f))

    return g


def module_from(module, sourcepath=None):
    """
    Same semantics as importlib.import_module, but imports can be made relative to a given source directory without
    affecting sys.path
    :param module: a '.'-separated name referencing a module in the current environment.
    :param sourcepath: a path to a directory from which to perform the import. Optionally, this may set to None and
      the directory path prepended on the module name with a separating slash
    :return: the imported module
    """
    module, sourcepath = _classpath_and_dir(module, sourcepath, checkdir=True)
    logger.debug(
        "Attempting to import module {}{}".format(
            module, "" if sourcepath is None else " locally from {}".format(sourcepath)
        )
    )

    if sourcepath is not None:
        wd = os.getcwd()
        os.chdir(sourcepath)
        mod = import_module(module)
        os.chdir(wd)
    else:
        mod = import_module(module)

    return mod


def object_from(classpath, sourcepath=None, subclass_check=None, instance_check=None):
    """
    Same semantics as import_object, but imports can be made relative to a given source directory without
    affecting sys.path
    """
    classpath, sourcepath = _classpath_and_dir(classpath, sourcepath, checkdir=True)
    logger.debug(
        "Attempting to import object {}{}".format(
            classpath,
            "" if sourcepath is None else " locally from {}".format(sourcepath),
        )
    )

    if sourcepath is not None:
        wd = os.getcwd()
        os.chdir(sourcepath)
        obj = import_object(classpath)
        os.chdir(wd)
    else:
        obj = import_object(classpath)

    if subclass_check is not None:
        assert isinstance(obj, type) and issubclass(
            obj, subclass_check
        ), "{} is not a subclass of {}".format(classpath, subclass_check)
    if instance_check is not None:
        assert isinstance(obj, instance_check), "{} is not an instance of {}".format(
            classpath, instance_check
        )

    return obj


def _check_instance_type(obj, instance_check=None):
    assert isinstance(obj, instance_check), "{} is not an instance of {}".format(
        obj, instance_check
    )


def _import(
    module, names=None, asname=None, sourcepath=None, globals_=None, _stack_height=1
):
    all_ = False
    if isinstance(names, str):
        if names.strip() == ALL:
            all_ = True
            names = None
        else:
            names = (names,)

    if sourcepath is not None:
        mod = module_from(module, sourcepath)
    else:
        mod = import_module(module)

    globals_ = (
        globals_ if globals_ is not None else stack()[_stack_height].frame.f_globals
    )
    if names in (None, as_):
        if all_:
            if hasattr(mod, "__all__"):
                namespace = [(n, mod.__dict__[n]) for n in mod.__all__]
            else:
                namespace = [
                    (n, v)
                    for n, v in mod.__dict__.items()
                    if n not in MODULE_ATTRS and not n.startswith("_")
                ]
        else:
            if asname is None:
                parentmodule = module.split(".")[0]
                namespace = [(parentmodule, import_module(parentmodule))]
            else:
                namespace = [(asname, mod)]
    else:
        if asname is not None:
            raise ValueError(
                "If names are passed, asname must be None; got {}. "
                "if you would like to specify new names for the imports, pass a dict as names, mapping "
                "the source module name to the imported name".format(asname)
            )
        if isinstance(names, dict):
            rename = names
        elif isinstance(names, (list, tuple)):
            rename = dict(t if isinstance(t, tuple) else (t, t) for t in names)
        else:  # pragma: no cover
            raise TypeError(
                "Names must be a dict, list, str, or None; see docstring for details"
            )

        namespace = [(rename[n], mod.__dict__[n]) for n in rename]

    collisions = [
        (n, globals_[n], v)
        for n, v in namespace
        if n in globals_ and _isnot(v, globals_[n])
    ]

    if collisions:
        logger.warning(
            "the following names will be shadowed in the global namespace after importing from {}:\n{}".format(
                module, indent(_pprint(collisions), "    ")
            )
        )

    globals_.update(namespace)


def _classpath_and_dir(classpath, sourcepath, checkdir=True):
    if sourcepath is None:
        sourcepath = os.path.dirname(classpath) or None
        classpath = os.path.basename(classpath)
    else:
        assert os.path.sep not in classpath, (
            "if a sourcepath is passed, then classpath must not contain {}, "
            "which is ambiguous; got {}".format(os.path.sep, classpath)
        )
        if not os.path.isdir(sourcepath):
            if checkdir:
                raise ValueError("if a sourcepath is passed, it must be a directory")
            sourcepath = os.path.dirname(sourcepath) or None

    assert sourcepath is None or os.path.isdir(
        sourcepath
    ), "if a sourcepath is passed, it must be an existing file or directory"

    return classpath, sourcepath


def _isnot(obj1, obj2):  # pragma: no cover
    try:
        val = obj1 is not obj2
    except Exception:
        val = True
    return val


def _pprint(collisions):
    return "\n".join("{}: {} -> {}".format(*map(repr, t)) for t in collisions)


def _validate_module_spec(spec, allow_tuple=False):
    if type(spec) is _ImportSpec:
        return spec.import_spec
        modname = None  # never evaluated; makes PyCharm happy
    elif type(spec) is import_:
        modname = spec.modname
        spec = (spec.modname,)
    elif isinstance(spec, str):
        modname = spec
        spec = (modname,)
    elif isinstance(spec, tuple) and allow_tuple:
        if len(spec) == 1:
            modname = spec[0]
            spec = (modname,)
        if len(spec) == 2:
            modname, imports = spec

            if isinstance(imports, str) and imports != ALL:  # pragma: no cover
                raise TypeError(
                    "if a string is passed to from_(modname).import_, it must be '*' "
                    "(aliased to application.imports.ALL); got {}".format(imports)
                )
            if isinstance(imports, (list, tuple)):
                renames = imports
            elif isinstance(imports, dict):
                renames = imports.items()
            else:  # pragma: no cover
                raise TypeError()

            bad_renames = [n for n in renames if not _is_valid_rename(n)]
            if bad_renames:
                raise ValueError(
                    "the arguments to from_(modname).import_ must be names as positional args or "
                    "`new_name=old_name` as keyword args; got bad ags {}".format(
                        ", ".join(
                            repr(n) if isinstance(n, str) else "=".join(map(repr, n))
                            for n in bad_renames
                        )
                    )
                )

            spec = (modname, imports)
        elif len(spec) == 3:
            modname, imports, asname = spec

            if not isinstance(asname, str):  # pragma: no cover
                raise TypeError("; got {}".format(type(asname)))
    else:  # pragma: no cover
        raise TypeError(
            "An import specification must be one of: from_(module).import_(*names, **renames),"
            "import_(module).as_(rename), or import_(module); got {}".format(spec)
        )

    if not isinstance(modname, str):  # pragma: no cover
        raise TypeError(
            "The first entry of an import specification must be a string specifying the module to be "
            "imported (from); got {}".format(modname)
        )

    return spec


def _is_valid_rename(name):
    return (
        isinstance(name, str)
        or isinstance(name, tuple)
        and len(name) == 2
        and all(isinstance(n, str) for n in name)
    )


# add a few standard constructors here so that the .types submodule needn't import from this one
typing_to_stdlib_constructor[typing.Callable] = import_object
typing_to_stdlib_constructor[typing.Type] = import_type
