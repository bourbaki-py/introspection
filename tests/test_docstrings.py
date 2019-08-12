# coding:utf-8
import pytest
from bourbaki.introspection.docstrings import parse_docstring, CallableDocs


def foo(x: int, y: str, z: object=None) -> list:
    """
    This is the short desc,
    and some more short desc.

    This is the long desc.
    :param int x: an integer
    :param y: a str
      and more y stuff
    :type y: str

    :raise TypeError: if there is a type error
    :param z: an object
    :return: a list
      and more list docs
    :rtype: list

    :raise ValueError: if there is a value error
    """

clean_doc = """This is the short desc,
and some more short desc.

This is the long desc.

:param x: an integer
:type x: int
:param y: a str
  and more y stuff
:type y: str
:param z: an object

:raises TypeError: if there is a type error
:raises ValueError: if there is a value error

:return: a list
  and more list docs
:rtype: list"""

raises_types = ["TypeError", "ValueError"]

raises_docs = ["if there is a type error", "if there is a value error"]


@pytest.fixture(scope="module")
def docs():
    return parse_docstring(foo)


def test_parse_docstring_short_desc(docs: CallableDocs):
    assert docs.short_desc == "This is the short desc,\nand some more short desc."


def test_parse_docstring_long_desc(docs: CallableDocs):
    assert docs.long_desc == "This is the long desc."


def test_parse_docstring_return_type(docs: CallableDocs):
    assert docs.returns.type == "list"


def test_parse_docstring_return_doc(docs: CallableDocs):
    assert docs.returns.doc == "a list\n  and more list docs"


@pytest.mark.parametrize("index,type_", enumerate(raises_types))
def test_parse_docstring_raises_type(docs: CallableDocs, index: int, type_: str):
    raises = docs.raises[index]
    assert raises.type == type_


@pytest.mark.parametrize("index,doc", enumerate(raises_docs))
def test_parse_docstring_raises_doc(docs: CallableDocs, index: int, doc: str):
    raises = docs.raises[index]
    assert raises.doc == doc


def test_parse_docstring_param_set(docs: CallableDocs):
    assert set(docs.params) == set("xyz")


@pytest.mark.parametrize("name", ["x", "y", "z"])
def test_parse_docstring_param_type(docs: CallableDocs, name: str):
    param = docs.params[name]
    assert param.name == name


@pytest.mark.parametrize("name,type_", [("x", "int"), ("y", "str"), ("z", None)])
def test_parse_docstring_param_type(docs: CallableDocs, name: str, type_: str):
    param = docs.params[name]
    assert param.type == type_


@pytest.mark.parametrize("name,doc", [("x", "an integer"), ("y", "a str\n  and more y stuff"), ("z", "an object")])
def test_parse_docstring_param_doc(docs: CallableDocs, name: str, doc: str):
    param = docs.params[name]
    assert param.doc == doc


def test_docstring_str(docs):
    assert str(docs) == clean_doc
