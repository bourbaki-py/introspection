# coding:utf-8
from typing import *
import pathlib
import re
import site
import pytest
from bourbaki.introspection.imports import (import_object, object_from, import_type, module_from, lazy_imports, import_, from_,
                                            get_globals)

try:
    site_packages = site.getsitepackages()[0]
except AttributeError:
    # travis runs in virtualenv with fixed older version of site
    site_packages = site.getusersitepackages()


def func():
    pass


class Foo:
    def __init__(self):
        pass


class BadModule:
    __module__ = "ASDFASDF"
    def __init__(self):
        pass


@pytest.mark.parametrize("obj,globals_", [
    (Foo, globals()),
    (func, globals()),
    (Foo.__init__, globals()),
    (BadModule, globals()),
    (re.sub, re.__dict__),
])
def test_get_globals(obj, globals_):
    print(getattr(obj, '__module__', None))
    assert get_globals(obj) is globals_


@lazy_imports(
    import_('pathlib').as_('foolib'),
    from_('uuid').import_('UUID', uuid4='uuidfour'),
)
def import_stuff_lazily():
    return foolib, UUID, uuidfour


def test_lazy_imports():
    for name in 'foolib', 'UUID', 'uuidfour':
        assert name not in globals()

    foolib, UUID, uuidfour = import_stuff_lazily()

    for name in 'foolib', 'UUID', 'uuidfour':
        assert name in globals()
        assert globals()[name] == locals()[name]

    import pathlib
    import uuid

    assert pathlib is foolib
    assert uuid.UUID is UUID
    assert uuid.uuid4 is uuidfour


@pytest.mark.parametrize('path,o,dir_', [
    ('int', int, None),
    ('re.I', __import__('re').I, None),
    ('uuid.UUID', __import__('uuid').UUID, None),
    ('pathlib', __import__('pathlib'), None),
    ('typing.Union', Union, None),
    ('typing_inspect', __import__('typing_inspect'), site_packages),
    ('typing_inspect.get_args', __import__('typing_inspect').get_args, site_packages),
])
def test_import_object(path, o, dir_):
    obj = object_from(path, dir_)
    assert obj is o


@pytest.mark.parametrize("path", [
    "re.asdfasdf",
    "collections.asdfasdf",
])
def test_import_object_raises_attribute_error(path):
    with pytest.raises(AttributeError):
        obj = import_object(path)


@pytest.mark.parametrize("path", [
    "asdfasdf",
    "asdf.asdf",
])
def test_import_object_raises_import_error(path):
    with pytest.raises(ImportError):
        obj = import_object(path)


@pytest.mark.parametrize("path,t", [
    ('int', int),
    ('builtins.list', list),
    ('List', List),
    ('typing.Sequence', Sequence),
    ('Tuple[int,...]', Tuple[int, ...]),
    ('Dict[Tuple[int, str, bool], Sequence[complex]]', Dict[Tuple[int, str, bool], Sequence[complex]]),
    ('Union[int,complex,float]', Union[int, complex, float]),
])
def test_import_type(path, t):
    type_ = import_type(path)
    assert type_ == t


@pytest.mark.parametrize("path", [
    "-foo.bar",
    "{'foo': 'bar'}",
    "foo.bar{baz}",
])
def test_import_type_raises_syntax_error(path):
    with pytest.raises(SyntaxError):
        type_ = import_type(path)


@pytest.mark.parametrize("path", [
    're.I',
    'pathlib',
    'int.__str__',
])
def test_import_type_fails_for_non_type(path):
    with pytest.raises(TypeError):
        type_ = import_type(path)


@pytest.mark.parametrize("path,mod,dir_", [
    ('pathlib', __import__('pathlib'), None),
    ('collections.abc', __import__('collections').abc, None),
    ('typing_inspect', __import__('typing_inspect'), None),
    ('typing_inspect', __import__('typing_inspect'), site_packages),
])
def test_import_module(path, mod, dir_):
    if dir_ is not None:
        source_dirs = pathlib.Path(dir_).glob(path + '*')
        assert next(iter(source_dirs))
    assert module_from(path, dir_) is mod


@pytest.mark.parametrize("path", [
    'pathlib.Path',
    'collections.defaultdict',
    'int',
    'asdfasdg.asdgasdg',
])
def test_import_module_raises_on_non_module(path):
    with pytest.raises(ModuleNotFoundError):
        mod = module_from(path)
