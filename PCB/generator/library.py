"""Loads symbols from the KiCad install, flattening `extends`, and reports pins."""

import copy
import math
import os

from sexpr import Sym, find, find_all, parse, prop

KICAD_SHARE = os.environ.get(
    "KICAD_SHARE",
    r"C:\Users\Maher Yousif\AppData\Local\Programs\KiCad\10.0\share\kicad",
)
SYMBOL_DIR = os.path.join(KICAD_SHARE, "symbols")
FOOTPRINT_DIR = os.path.join(KICAD_SHARE, "footprints")

_libs = {}


def _load_lib(lib):
    if lib not in _libs:
        path = os.path.join(SYMBOL_DIR, lib + ".kicad_sym")
        with open(path, encoding="utf-8") as f:
            tree = parse(f.read())
        _libs[lib] = {s[1]: s for s in find_all(tree, "symbol")}
    return _libs[lib]


def _rename_units(sym, old, new):
    for c in find_all(sym, "symbol"):
        if c[1].startswith(old + "_"):
            c[1] = new + c[1][len(old):]


def load_symbol(lib_id):
    """Returns a flattened copy of the symbol, named 'Lib:Name'."""
    lib, name = lib_id.split(":")
    syms = _load_lib(lib)
    sym = copy.deepcopy(syms[name])

    ext = find(sym, "extends")
    if ext:
        parent = copy.deepcopy(syms[ext[1]])
        _rename_units(parent, ext[1], name)
        # child properties override parent ones
        child_props = {p[1]: p for p in find_all(sym, "property")}
        merged = [parent[0], name]
        for c in parent[2:]:
            if isinstance(c, list) and c[0] == "property" and c[1] in child_props:
                merged.append(child_props.pop(c[1]))
            else:
                merged.append(c)
        merged.extend(child_props.values())
        sym = merged

    sym[1] = lib_id
    return sym


def symbol_pins(sym):
    """[(unit, number, name, x, y, angle, electrical_type, hidden)] in symbol coordinates."""
    pins = []
    base = sym[1].split(":")[1]
    for unit_sym in find_all(sym, "symbol"):
        suffix = unit_sym[1][len(base) + 1:] if unit_sym[1].startswith(base + "_") else unit_sym[1].split("_", 1)[-1]
        unit = int(suffix.split("_")[0])
        for p in find_all(unit_sym, "pin"):
            at = find(p, "at")
            name = find(p, "name")[1]
            number = find(p, "number")[1]
            hidden = any(isinstance(c, Sym) and c == "hide" for c in p) or (find(p, "hide") is not None and find(p, "hide")[1] == "yes")
            pins.append((unit, number, name, float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0, str(p[1]), hidden))
    return pins


def unit_count(sym):
    units = {u for (u, *_rest) in symbol_pins(sym)}
    units.discard(0)
    return max(units) if units else 1


def symbol_footprint(sym):
    return prop(sym, "Footprint") or ""


if __name__ == "__main__":
    import sys

    for lib_id in sys.argv[1:]:
        s = load_symbol(lib_id)
        print(f"== {lib_id}  fp={symbol_footprint(s)}  units={unit_count(s)}")
        for pin in sorted(symbol_pins(s), key=lambda p: (p[0], p[1].zfill(4))):
            print("   ", pin)
