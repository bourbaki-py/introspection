# coding:utf-8
from bourbaki.introspection.prettyprint import fmt_pyobj

obj = {
    "foo": "bar",
    "baz": [1, 2, (3, 4, {5, 6})],
    "wut": dict(),
    "wat": frozenset([("wat", 123)]),
}

s = """dict(
    foo='bar',
    baz=[
        1,
        2,
        (
            3,
            4,
            {
                5,
                6,
            },
        ),
    ],
    wut={},
    wat=frozenset([
        (
            'wat',
            123,
        ),
    ]),
)"""

s_top_level = """foo='bar'
baz=[
    1,
    2,
    (
        3,
        4,
        {
            5,
            6,
        },
    ),
]
wut={}
wat=frozenset([
    (
        'wat',
        123,
    ),
])
"""

bigint = 123456
bigfloat = 12345.0
referred1 = [1, bigfloat, bigint]
referred2 = ("one", "two")
obj_with_refs = {
    "foo": {1: referred1},
    "bar": [referred1, referred2],
    "baz": referred2,
    "wut": frozenset([bigfloat, bigint]),
}

s_with_refs_top_level = """foo={
    1: [
        1,
        12345.0,
        123456,
    ],
}
bar=[
    foo[1],
    (
        'one',
        'two',
    ),
]
baz=bar[1]
wut=frozenset([
    foo[1][2],
    foo[1][1],
])
"""


def test_fmt_pyobj():
    assert s == fmt_pyobj(obj)
    namespace = eval(s)
    assert namespace == obj


def test_fmt_pyobj_top_level():
    assert s_top_level == fmt_pyobj(obj, top_level=True)
    namespace = dict()
    exec(s_top_level, globals(), namespace)
    assert namespace == obj


def test_fmt_pyobj_with_refs():
    assert s_with_refs_top_level == fmt_pyobj(
        obj_with_refs, memo=dict(), top_level=True
    )
