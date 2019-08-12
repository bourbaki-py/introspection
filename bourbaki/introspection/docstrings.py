# coding:utf-8
from typing import Dict, Tuple, Union, Callable
from itertools import chain
import re
from .utils import py_name_re, py_dot_name_re

param_regex = re.compile(r'^(?P<indent>\s*)[:@](?:param|arg) (?:(?P<type>{}) )?(?P<name>{}):(?:\s+(?P<doc>.*))?\s*$'
                         .format(py_dot_name_re, py_name_re))

param_type_regex = re.compile(r'^(?P<indent>\s*)[:@]type (?P<name>{}):(?:\s+(?P<doc>.*))?\s*$'
                              .format(py_name_re))

return_regex = re.compile(r'^(?P<indent>\s*)[:@]return(?:s)?(?: (?P<type>{}))?:(?:\s+(?P<doc>.*))?\s*$'
                          .format(py_dot_name_re))

rtype_regex = re.compile(r'^(?P<indent>\s*)[:@]rtype:(?:\s+(?P<type>.*))?\s*$')

raises_regex = re.compile(r'^(?P<indent>\s*)[:@]raise(?:s)? (?:(?P<type>{})):(?:\s+(?P<doc>.*))?\s*$'
                          .format(py_dot_name_re))

leading_whitespace = re.compile(r"\s*")


def _dedent(line, indent):
    if re.match(indent, line):
        return line[len(indent):]
    return line.lstrip()


class NoDocString(AttributeError, TypeError):
    pass


class CallableDocs:
    def __init__(self, short_desc=None, long_desc=None, params=(), returns=None, raises=()):
        self.short_desc = short_desc
        self.long_desc = long_desc
        self.params = ParamDocs(*params)
        if isinstance(returns, ReturnsDoc):
            self.returns = returns
        else:
            self.returns = ReturnsDoc() if returns is None else ReturnsDoc(**returns)
        self.raises = RaisesDocs(*raises)

    @property
    def desc(self):
        return '\n\n'.join(d for d in (self.short_desc, self.long_desc) if d)

    @classmethod
    def parse(cls, doc_or_documented):
        return parse_docstring(doc_or_documented)

    def __str__(self):
        return '\n\n'.join(filter(None, map(str, filter(None, (self.short_desc,
                                                               self.long_desc,
                                                               self.params,
                                                               self.raises,
                                                               self.returns)))))


class ParamDocBase:
    def __init__(self, doc=None, type=None):
        self.type = type
        self.doc = doc


class ReturnsDoc(ParamDocBase):
    def __str__(self):
        rdoc = ":return: {}".format(self.doc) if self.doc else ''
        rtype = ":rtype: {}".format(self.type) if self.type else ''
        return '\n'.join(filter(None, (rdoc, rtype)))


class RaisesDoc(ParamDocBase):
    def __str__(self):
        return ":raises {}:{}".format("{}".format(self.type) if self.type else Exception.__name__,
                                      " {}".format(self.doc) if self.doc else '')


class ParamDoc(ParamDocBase):
    def __init__(self, name, doc=None, type=None):
        super().__init__(doc, type)
        self.name = name

    def __str__(self):
        paramdoc = ":param {}:{}".format(self.name, " {}".format(self.doc) if self.doc else '')
        paramtype = ":type {}:{}".format(self.name, " {}".format(self.type)) if self.type else ''
        return '\n'.join(filter(None, (paramdoc, paramtype)))


class RaisesDocs(Tuple[RaisesDoc]):
    def __new__(cls, *raises):
        return super().__new__(cls, (r if isinstance(r, RaisesDoc) else RaisesDoc(**r) for r in raises))

    def __str__(self):
        return '\n'.join(map(str, self))

    def __getnewargs__(self):
        return tuple(self)


class ParamDocs(Dict[str, ParamDoc]):
    def __init__(self, *params):
        params = (p if isinstance(p, ParamDoc) else ParamDoc(**p) for p in params)
        super().__init__(((p.name, p) for p in params))

    def __str__(self):
        return '\n'.join(map(str, self.values()))


def parse_docstring(doc_or_documented: Union[str, Callable]) -> CallableDocs:
    arg_error = "argument to parse_docstring must be a string or object with a string __doc__ attribute; got {}"
    if isinstance(doc_or_documented, str):
        doc = doc_or_documented
    elif hasattr(doc_or_documented, "__doc__"):
        doc = getattr(doc_or_documented, "__doc__")
    else:
        raise NoDocString(arg_error.format(doc_or_documented))

    if doc is None:
        return CallableDocs()

    return_ = dict(doc=None, type=None)
    raises = []
    short = []
    long = []
    params = []
    param_types = []
    lastdict = None
    last_indent = None

    regexes = [param_regex, param_type_regex, raises_regex, return_regex, rtype_regex]
    SHORT, LONG, PARAM, PARAMTYPE, RAISES, RETURN, RTYPE = 0, 1, 2, 3, 4, 5, 6

    state = SHORT
    for line in doc.split('\n'):
        try:
            matches = ((i, r.match(line)) for i, r in enumerate(regexes, PARAM))
            state, match = next(tup for tup in matches if tup[1])
        except StopIteration:
            is_whitespace = leading_whitespace.fullmatch(line)
            if state == SHORT:
                if not short and not is_whitespace:
                    last_indent = leading_whitespace.match(line)
                if line:
                    if last_indent:
                        line = _dedent(line, last_indent.group())
                    short.append(line)
                elif short:
                    state = LONG
            elif state == LONG:
                if not long and not is_whitespace:
                    last_indent = leading_whitespace.match(line)
                if last_indent:
                    line = _dedent(line, last_indent.group())
                long.append(line)
            elif state in (PARAM, PARAMTYPE, RAISES, RETURN, RTYPE):
                key = 'type' if state == RTYPE else 'doc'
                if last_indent:
                    line = _dedent(line, last_indent)
                lastdict[key] = '\n'.join(d or '' for d in (lastdict[key], line))
        else:
            lastdict = match.groupdict()
            last_indent = lastdict.pop("indent")
            if state == PARAM:
                params.append(lastdict)
            elif state == PARAMTYPE:
                param_types.append(lastdict)
            elif state == RAISES:
                raises.append(lastdict)
            elif state in (RETURN, RTYPE):
                return_.update(lastdict)
                lastdict = return_

    param_types = {p["name"]: p["doc"] for p in param_types}
    for p in params:
        ptype = param_types.get(p["name"])
        if ptype:
            p["type"] = ptype.strip()

    for p in chain(params, raises, (return_,)):
        d = p["doc"]
        if isinstance(d, str):
            p["doc"] = d.rstrip()

    rtype = return_["type"]
    if isinstance(rtype, str):
        return_["type"] = rtype.rstrip()

    return CallableDocs(short_desc='\n'.join(short).rstrip(),
                        long_desc='\n'.join(long).rstrip(),
                        params=params, raises=raises, returns=return_)
