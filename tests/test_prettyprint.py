# coding:utf-8
from bourbaki.introspection.prettyprint import fmt_pyobj

obj = {
    'foo': 'bar',
    'baz': [1, 2, (3, 4, {5, 6})],
    'wut': dict(),
    'wat': frozenset([('wat', 123)])
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

s_ = """foo='bar'
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


def test_fmt_pyobj():
    assert s == fmt_pyobj(obj)


def test_fmt_pyobj_top_level():
    assert s_ == fmt_pyobj(obj, top_level=True)
