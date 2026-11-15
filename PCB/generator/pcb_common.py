"""Shared helpers for the PCB generator (runs under KiCad's bundled Python)."""

import os
import re

import pcbnew

import design
from library import FOOTPRINT_DIR, load_symbol, symbol_pins
from gen_sch import resolve_pins

MM = pcbnew.FromMM

_fp_cache = {}


def load_footprint(fp_id):
    lib, name = fp_id.split(":")
    fp = pcbnew.FootprintLoad(os.path.join(FOOTPRINT_DIR, lib + ".pretty"), name)
    if fp is None:
        raise SystemExit(f"Footprint not found: {fp_id}")
    return fp


def expand_numbers(number):
    """'[1,15,38,39]' or '[1-3]' -> ['1','15','38','39']; '5' -> ['5']."""
    if not number.startswith("["):
        return [number]
    out = []
    for chunk in number.strip("[]").split(","):
        m = re.fullmatch(r"(\w*?)(\d+)-(\w*?)(\d+)", chunk)
        if m and m.group(1) == m.group(3):
            out += [f"{m.group(1)}{i}" for i in range(int(m.group(2)), int(m.group(4)) + 1)]
        else:
            out.append(chunk)
    return out


# Footprint pads that don't appear on the symbol
EXTRA_PADS = {}


def unconnected_net(ref, pin_name, pad):
    """The net name KiCad gives a no-connect pin, so the board matches the schematic."""
    return f"unconnected-({ref}-{pin_name}-Pad{pad})" if pin_name else f"unconnected-({ref}-Pad{pad})"


def pad_nets(p, include_nc=False):
    """{pad number: net} for one part. With include_nc, no-connect pads get KiCad's
    'unconnected-(...)' names, prefixed with '!' to mark them as absolute."""
    sym = load_symbol(p["lib_id"])
    out = {}
    for pin, net in resolve_pins(p, sym):
        if net == "NC":
            if include_nc:
                for n in expand_numbers(pin[1]):
                    out.setdefault(n, "!" + unconnected_net(p["ref"], pin[2], n))
            continue
        for n in expand_numbers(pin[1]):
            out[n] = net
    out.update(EXTRA_PADS.get(p["footprint"], {}))
    return out


def board_parts():
    return [p for p in design.PARTS if p["footprint"]]
