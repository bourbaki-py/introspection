# coding:utf-8
import os
from inspect import stack
from warnings import warn

INTROSPECTION_DEBUG_ENV_VAR = "BOURBAKI_INTROSPECTION_DEBUG"


def _trace(f):  # pragma: no cover
    offset = len(stack()) - 2

    def f_(*a, **kw):
        indent = " " * max((len(stack()) - offset), 0)
        print("{}{}({})".format(indent, f.__name__, ", ".join(map(repr, a))))
        try:
            result = f(*a, **kw)
        except Exception as e:
            print("{}  !! {}".format(indent, e))
            raise e
        else:
            print("{}  -> {}".format(indent, result))
        return result

    return f_


DEBUG = os.environ.get(INTROSPECTION_DEBUG_ENV_VAR, "").lower().strip()
if DEBUG == "true" or (DEBUG.isdigit() and DEBUG != "0"):  # pragma: no cover
    warn(
        "Found environment variable {}={}; verbose output will be generated for code in the introspection module".format(
            INTROSPECTION_DEBUG_ENV_VAR, DEBUG
        )
    )
    DEBUG = True if not DEBUG.isdigit() else int(DEBUG)
    trace = _trace
else:  # pragma: no cover
    DEBUG = False

    def trace(x):
        return x
