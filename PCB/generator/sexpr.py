"""Minimal S-expression reader/writer for KiCad files."""

import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()"]+))', re.S)


class Sym(str):
    """An unquoted atom (keyword or number) as opposed to a quoted string."""


def parse(text):
    stack = [[]]
    pos = 0
    while True:
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        lp, rp, s, atom = m.groups()
        if lp:
            stack.append([])
        elif rp:
            done = stack.pop()
            stack[-1].append(done)
        elif s is not None:
            stack[-1].append(s[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(Sym(atom))
    return stack[0][0]


def _atom(x):
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        return fmt_num(x)
    s = str(x).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def fmt_num(v):
    if isinstance(v, int):
        return str(v)
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def dump(node, indent=0):
    if not isinstance(node, list):
        return _atom(node)
    pad = "\t" * indent
    simple = all(not isinstance(c, list) for c in node)
    if simple:
        return "(" + " ".join(_atom(c) for c in node) + ")"
    head = []
    rest = []
    for c in node:
        if not rest and not isinstance(c, list):
            head.append(_atom(c))
        else:
            rest.append(c)
    out = "(" + " ".join(head)
    for c in rest:
        out += "\n" + pad + "\t" + dump(c, indent + 1)
    return out + "\n" + pad + ")"


def find(node, key):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def prop(node, name):
    for c in find_all(node, "property"):
        if c[1] == name:
            return c[2]
    return None
