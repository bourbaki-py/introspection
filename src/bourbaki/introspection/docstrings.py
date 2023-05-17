# coding:utf-8
from typing import Dict, Tuple, Union, Callable
from enum import Enum
from itertools import chain
import re
from .utils import py_name_re, py_dot_name_re

param_regex = re.compile(
    r"^(?P<indent>\s*)[:@](?:param|arg) (?:(?P<type>{}) )?(?P<name>{}):(?:\s+(?P<doc>.*))?\s*$".format(
        py_dot_name_re, py_name_re
    )
)

param_type_regex = re.compile(
    r"^(?P<indent>\s*)[:@]type (?P<name>{}):(?:\s+(?P<doc>.*))?\s*$".format(py_name_re)
)

return_regex = re.compile(
    r"^(?P<indent>\s*)[:@]return(?:s)?(?: (?P<type>{}))?:(?:\s+(?P<doc>.*))?\s*$".format(
        py_dot_name_re
    )
)

rtype_regex = re.compile(r"^(?P<indent>\s*)[:@]rtype:(?:\s+(?P<type>.*))?\s*$")

raises_regex = re.compile(
    r"^(?P<indent>\s*)[:@]raise(?:s)? (?:(?P<type>{})):(?:\s+(?P<doc>.*))?\s*$".format(
        py_dot_name_re
    )
)

leading_whitespace = re.compile(r"\s*")

google_param_regex = re.compile(
    r"^(?P<indent>\s*)(?P<stars>\*{1,2})?(?P<name>%s)(?:\s+\((?P<type>[^)]+)\))?:(?:\s+(?P<doc>.*))?\s*"
    % py_name_re
)

google_return_regex = re.compile(
    r"^(?P<indent>\s*)(?:(?P<type>[\w\s]+\w)):(?:\s+(?P<doc>.*))?\s*"
)

google_raises_regex = re.compile(
    r"^(?P<indent>\s*)(?:(?P<type>{})):(?:\s+(?P<doc>.*))?\s*".format(py_dot_name_re)
)

google_block_heading_regex = re.compile(
    r"^(?P<indent>\s*)(?P<heading>[A-Z][A-Za-z]+):\s*"
)


def _dedent(line, indent):
    if re.match(indent, line):
        return line[len(indent) :]
    return line.lstrip()


def _indentation(line):
    indent = leading_whitespace.match(line)
    if indent:
        return indent.group()
    return ""


class NoDocString(AttributeError, TypeError):
    pass


class DocStyle(Enum):
    sphinx = "sphinx-style docstrings"
    google = "google-style docstrings"
    auto = "infer docstring style"


class CallableDocs:
    def __init__(
        self, short_desc=None, long_desc=None, params=(), returns=None, raises=()
    ):
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
        return "\n\n".join(d for d in (self.short_desc, self.long_desc) if d)

    @classmethod
    def parse(cls, doc_or_documented):
        return parse_docstring(doc_or_documented)

    def __str__(self):
        return "\n\n".join(
            filter(
                None,
                map(
                    str,
                    filter(
                        None,
                        (
                            self.short_desc,
                            self.long_desc,
                            self.params,
                            self.raises,
                            self.returns,
                        ),
                    ),
                ),
            )
        )


class ParamDocBase:
    def __init__(self, doc=None, type=None):
        self.type = type
        self.doc = doc


class ReturnsDoc(ParamDocBase):
    def __str__(self):
        rdoc = ":return: {}".format(self.doc) if self.doc else ""
        rtype = ":rtype: {}".format(self.type) if self.type else ""
        return "\n".join(filter(None, (rdoc, rtype)))


class RaisesDoc(ParamDocBase):
    def __str__(self):
        return ":raises {}:{}".format(
            "{}".format(self.type) if self.type else Exception.__name__,
            " {}".format(self.doc) if self.doc else "",
        )


class ParamDoc(ParamDocBase):
    def __init__(self, name, doc=None, type=None):
        super().__init__(doc, type)
        self.name = name

    def __str__(self):
        paramdoc = ":param {}:{}".format(
            self.name, " {}".format(self.doc) if self.doc else ""
        )
        paramtype = (
            ":type {}:{}".format(self.name, " {}".format(self.type))
            if self.type
            else ""
        )
        return "\n".join(filter(None, (paramdoc, paramtype)))


class RaisesDocs(Tuple[RaisesDoc]):
    def __new__(cls, *raises):
        return super().__new__(
            cls, (r if isinstance(r, RaisesDoc) else RaisesDoc(**r) for r in raises)
        )

    def __str__(self):
        return "\n".join(map(str, self))

    def __getnewargs__(self):
        return tuple(self)


class ParamDocs(Dict[str, ParamDoc]):
    def __init__(self, *params):
        params = (p if isinstance(p, ParamDoc) else ParamDoc(**p) for p in params)
        super().__init__(((p.name, p) for p in params))

    def __str__(self):
        return "\n".join(map(str, self.values()))


def parse_docstring(
    doc_or_documented: Union[str, Callable], style: DocStyle = DocStyle.auto
) -> CallableDocs:
    if isinstance(style, str):
        style = getattr(DocStyle, style, style)
    if not isinstance(style, DocStyle):
        raise TypeError(
            "style must be one of {}; got {}".format(
                tuple(s.name for s in DocStyle), style
            )
        )

    arg_error = "argument to parse_docstring must be a string or object with a string __doc__ attribute; got {}"
    if isinstance(doc_or_documented, str):
        doc = doc_or_documented
    elif hasattr(doc_or_documented, "__doc__"):
        doc = getattr(doc_or_documented, "__doc__")
    else:
        raise NoDocString(arg_error.format(doc_or_documented))

    if doc is None:
        return CallableDocs()

    if style == DocStyle.sphinx:
        parser = parse_sphinx_style_docstring
    elif style == DocStyle.google:
        parser = parse_google_style_docstring
    else:
        lines = doc.splitlines()
        n_sphinx_params = sum(1 for line in lines if param_regex.match(line))
        n_google_params = sum(1 for line in lines if google_param_regex.match(line))
        if not n_sphinx_params and not n_google_params:
            parser = parse_google_style_docstring
            for line in lines:
                if (
                    return_regex.match(line)
                    or rtype_regex.match(line)
                    or raises_regex.match(line)
                ):
                    parser = parse_sphinx_style_docstring
                    break
        else:
            parser = (
                parse_sphinx_style_docstring
                if n_sphinx_params > n_google_params
                else parse_google_style_docstring
            )

    return parser(doc)


def parse_sphinx_style_docstring(doc: str) -> CallableDocs:
    return_ = dict(doc=None, type=None)
    raises = []
    short = []
    long = []
    params = []
    param_types = []
    lastdict = None
    last_indent = None

    regexes = [param_regex, param_type_regex, raises_regex, return_regex, rtype_regex]
    SHORT, LONG, PARAM, PARAMTYPE, RAISES, RETURN, RTYPE = range(7)

    state = SHORT
    for line in doc.split("\n"):
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
                key = "type" if state == RTYPE else "doc"
                if last_indent:
                    line = _dedent(line, last_indent)
                lastdict[key] = "\n".join(d or "" for d in (lastdict[key], line))
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

    return CallableDocs(
        short_desc="\n".join(short).rstrip(),
        long_desc="\n".join(long).rstrip(),
        params=params,
        raises=raises,
        returns=return_,
    )


def parse_google_style_docstring(doc: str) -> CallableDocs:
    # raise NotImplementedError()
    short = []
    long = []
    params = []
    raises = []
    return_ = dict(doc=None, type=None)
    doc_indent = None
    heading_indent = None
    block_indent = None
    firstline = True

    SHORT, LONG, PARAM_BLOCK, RAISES_BLOCK, RETURN_BLOCK, RETURN, UNKNOWN_BLOCK = range(
        7
    )
    heading_states = {
        "args": PARAM_BLOCK,
        "arguments": PARAM_BLOCK,
        "return": RETURN_BLOCK,
        "returns": RETURN_BLOCK,
        "raise": RAISES_BLOCK,
        "raises": RAISES_BLOCK,
    }

    def heading_state(line, fallback=None, heading_indent=None):
        heading_match = google_block_heading_regex.fullmatch(line)
        if heading_match:
            dict_ = heading_match.groupdict()
            this_heading_indent = dict_.pop("indent")
            if heading_indent is None or heading_indent == this_heading_indent:
                heading = dict_["heading"].lower()
                return (
                    heading_states.get(heading.lower(), UNKNOWN_BLOCK),
                    this_heading_indent,
                )

        return fallback, heading_indent

    def add_to_last_doc(line, indent, dict_, key="doc"):
        if indent:
            line = _dedent(line, indent)
        dict_[key] = "\n".join(d or "" for d in (dict_[key], line))

    state = SHORT
    for line in doc.split("\n"):
        is_whitespace = leading_whitespace.fullmatch(line)

        if state == SHORT:
            state, heading_indent = heading_state(line, state, heading_indent)
            if state == SHORT:
                if not short and (not is_whitespace) and (not firstline):
                    doc_indent = _indentation(line)
                elif short and not doc_indent:
                    doc_indent = _indentation(line)

                if doc_indent:
                    line = _dedent(line, doc_indent)

                if line and not is_whitespace:
                    short.append(line)
                elif short:
                    state = LONG
        elif state == LONG:
            state, heading_indent = heading_state(line, state, heading_indent)
            if state == LONG:
                if not long and (not is_whitespace) and (not doc_indent):
                    doc_indent = _indentation(line)
                if doc_indent:
                    line = _dedent(line, doc_indent)
                if long or (not long and not is_whitespace):
                    long.append(line)
        elif state in (PARAM_BLOCK, RAISES_BLOCK):
            param_list, pattern = (
                (params, google_param_regex)
                if state == PARAM_BLOCK
                else (raises, google_raises_regex)
            )
            param_match = pattern.fullmatch(line)

            thisdict = param_match.groupdict() if param_match else None
            if param_match and (
                block_indent is None or thisdict["indent"] == block_indent
            ):
                block_indent = thisdict.pop("indent")
                thisdict.pop("stars", None)
                param_list.append(thisdict)
            else:
                maybe_state, heading_indent = heading_state(line, state, heading_indent)
                if maybe_state == state:
                    # continued docs for last arg
                    if param_list:
                        add_to_last_doc(line, block_indent, param_list[-1])
                else:
                    state = maybe_state
        elif state == RETURN_BLOCK:
            return_match = google_return_regex.fullmatch(line)

            thisdict = return_match.groupdict() if return_match else None
            if return_match and (
                block_indent is None or thisdict["indent"] == block_indent
            ):
                block_indent = thisdict.pop("indent")
                return_ = thisdict
                state = RETURN
            else:
                state, heading_indent = heading_state(line, RETURN, heading_indent)
                if state == RETURN:
                    if block_indent is None:
                        block_indent = _indentation(line)
                    add_to_last_doc(line, block_indent, return_)
        elif state == RETURN:
            state, heading_indent = heading_state(line, state, heading_indent)
            if state == RETURN:
                add_to_last_doc(line, block_indent, return_)
        elif state == UNKNOWN_BLOCK:
            state, heading_indent = heading_state(line, state, heading_indent)

        if firstline:
            firstline = False

    for p in chain(params, raises, (return_,)):
        d = p["doc"]
        if isinstance(d, str):
            p["doc"] = d.rstrip()

    rtype = return_["type"]
    if isinstance(rtype, str):
        return_["type"] = rtype.strip()

    return CallableDocs(
        short_desc="\n".join(short).rstrip(),
        long_desc="\n".join(long).rstrip(),
        params=params,
        raises=raises,
        returns=return_,
    )
