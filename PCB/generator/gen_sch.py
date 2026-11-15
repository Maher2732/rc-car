"""Generates PCB/mainboard/rc_mainboard.kicad_sch from design.py.

Every pin gets a short wire and a net label (or a no-connect flag), and each
functional block sits in its own titled frame.
"""

import json
import math
import os
import uuid

import design
from library import load_symbol, symbol_pins
from sexpr import Sym, dump

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "mainboard")
PROJECT = "rc_mainboard"
GRID = 2.54
STUB = 2.54
CHAR_W = 1.05          # approximate label character width at 1.27 mm font

NAMESPACE = uuid.UUID("6f1b8a52-7c1e-4f0e-9a43-2b7f6f0c1d11")


def uid(*parts):
    """Stable UUIDs so regenerating doesn't churn the files."""
    return str(uuid.uuid5(NAMESPACE, "/".join(str(p) for p in parts)))


ROOT_UUID = uid("root")


def snap(v):
    return round(v / GRID) * GRID


def font(size=1.27, bold=False):
    f = [Sym("font"), [Sym("size"), size, size]]
    if bold:
        f.append([Sym("bold"), Sym("yes")])
    return f


def effects(size=1.27, justify=None, hide=False, bold=False):
    e = [Sym("effects"), font(size, bold)]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    if hide:
        e.append([Sym("hide"), Sym("yes")])
    return e


# ---------------------------------------------------------------------
# Pin -> net resolution
# ---------------------------------------------------------------------

def resolve_pins(p, sym):
    """[(pin, net)] for every pin; raises on anything unmapped or unknown."""
    pins = symbol_pins(sym)
    nets = p["nets"]
    used_keys = set()
    out = []
    for pin in pins:
        unit, number, name, *_ = pin
        etype = pin[6]
        net = None
        for key in (name, number):
            if key and key in nets:
                net = nets[key]
                used_keys.add(key)
                break
        if net is None:
            if etype == "no_connect":
                net = "NC"
            else:
                raise SystemExit(f"{p['ref']} ({p['lib_id']}): pin {number} '{name}' has no net")
        out.append((pin, net))
    unknown = set(nets) - used_keys
    if unknown:
        raise SystemExit(f"{p['ref']} ({p['lib_id']}): no pins named {sorted(unknown)}")
    return out


# ---------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------

def outward(angle):
    """Unit vector pointing away from the symbol body, in schematic coordinates."""
    a = math.radians(angle)
    return (-round(math.cos(a)), round(math.sin(a)))


def part_extent(resolved):
    """Bounding box (x0, y0, x1, y1) relative to the anchor, including labels."""
    x0 = y0 = -GRID
    x1 = y1 = GRID
    for pin, net in resolved:
        _, _, _, px, py, angle, *_ = pin
        sx, sy = px, -py
        dx, dy = outward(angle)
        reach = STUB + (0 if net == "NC" else len(net) * CHAR_W + 1.5)
        ex, ey = sx + dx * reach, sy + dy * reach
        x0, x1 = min(x0, sx, ex), max(x1, sx, ex)
        y0, y1 = min(y0, sy, ey), max(y1, sy, ey)
    # room for reference / value text
    return x0 - 1, y0 - 4, x1 + 1, y1 + 4


# ---------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------

def symbol_instance(p, sym, x, y, resolved):
    ref = p["ref"]
    hidden_ref = ref.startswith("#")
    _, y0, _, y1 = part_extent(resolved)
    node = [Sym("symbol"),
            [Sym("lib_id"), p["lib_id"]],
            [Sym("at"), x, y, 0],
            [Sym("unit"), 1],
            [Sym("exclude_from_sim"), Sym("no")],
            [Sym("in_bom"), Sym("no") if hidden_ref or ref.startswith(("H", "JP")) else Sym("yes")],
            [Sym("on_board"), Sym("no") if hidden_ref else Sym("yes")],
            [Sym("dnp"), Sym("no")],
            [Sym("uuid"), uid("sym", ref)]]

    def prop(name, value, px, py, hide=False):
        node.append([Sym("property"), name, value, [Sym("at"), px, py, 0], effects(hide=hide)])

    prop("Reference", ref, x, y + y0 + 2.5, hide=hidden_ref)
    prop("Value", p["value"], x, y + y1 - 1.5, hide=hidden_ref)
    prop("Footprint", p["footprint"], x, y, hide=True)
    prop("Datasheet", "", x, y, hide=True)
    if p["mpn"]:
        prop("MPN", p["mpn"], x, y, hide=True)

    for number in sorted({pin[1] for pin, _ in resolved}):
        node.append([Sym("pin"), number, [Sym("uuid"), uid("pin", ref, number)]])

    node.append([Sym("instances"),
                 [Sym("project"), PROJECT,
                  [Sym("path"), "/" + ROOT_UUID, [Sym("reference"), ref], [Sym("unit"), 1]]]])
    return node


def pin_connections(p, x, y, resolved):
    items = []
    seen = {}
    for pin, net in resolved:
        _, number, name, px, py, angle, etype, hidden = pin
        sx, sy = round(x + px, 4), round(y - py, 4)
        key = (sx, sy)
        if key in seen:
            if seen[key] != net:
                raise SystemExit(f"{p['ref']}: stacked pins at {key} on different nets")
            continue
        seen[key] = net

        if net == "NC":
            if etype != "no_connect":
                items.append([Sym("no_connect"), [Sym("at"), sx, sy], [Sym("uuid"), uid("nc", p["ref"], number)]])
            continue

        dx, dy = outward(angle)
        ex, ey = round(sx + dx * STUB, 4), round(sy + dy * STUB, 4)
        items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), sx, sy], [Sym("xy"), ex, ey]],
                      [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                      [Sym("uuid"), uid("wire", p["ref"], number)]])

        if dx > 0:
            angle_l, just = 0, "left bottom"
        elif dx < 0:
            angle_l, just = 180, "right bottom"
        elif dy < 0:
            angle_l, just = 90, "left bottom"
        else:
            angle_l, just = 270, "right bottom"
        items.append([Sym("label"), net, [Sym("at"), ex, ey, angle_l], effects(justify=just),
                      [Sym("uuid"), uid("label", p["ref"], number)]])
    return items


def frame(title, x0, y0, x1, y1):
    return [
        [Sym("rectangle"), [Sym("start"), x0, y0], [Sym("end"), x1, y1],
         [Sym("stroke"), [Sym("width"), 0.3], [Sym("type"), Sym("dash")]],
         [Sym("fill"), [Sym("type"), Sym("none")]], [Sym("uuid"), uid("frame", title)]],
        [Sym("text"), title, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), x0 + 3, y0 + 6, 0],
         effects(size=3, justify="left bottom", bold=True), [Sym("uuid"), uid("title", title)]],
    ]


# ---------------------------------------------------------------------
# Layout: pack parts into blocks, blocks into columns
# ---------------------------------------------------------------------

BLOCK_ORDER = [
    ["Power input & switch", "Servo 5V / 5A", "Logic 5V / 3.3V"],
    ["Drive ESP32 (A)", "Telemetry ESP32 (B)"],
    ["CAN bus", "Motor, servo, battery sense", "Display", "Mechanical"],
]
BLOCK_WIDTH = 270
GAP = 12


def layout():
    symbols = {}
    placed = []        # (part, sym, resolved, x, y)
    frames = []
    blocks = design.blocks()
    assert sum(len(c) for c in BLOCK_ORDER) == len(blocks), "BLOCK_ORDER is missing a block"

    col_x = 20.0
    max_y = 0
    for column in BLOCK_ORDER:
        y_cursor = 20.0
        for name in column:
            parts = blocks[name]
            bx0, by0 = col_x, y_cursor
            cx, cy = bx0 + 6, by0 + 14
            row_h = 0
            for p in parts:
                if p["lib_id"] not in symbols:
                    symbols[p["lib_id"]] = load_symbol(p["lib_id"])
                sym = symbols[p["lib_id"]]
                resolved = resolve_pins(p, sym)
                ex0, ey0, ex1, ey1 = part_extent(resolved)
                w, h = ex1 - ex0, ey1 - ey0
                if cx + w > bx0 + BLOCK_WIDTH - 6 and cx > bx0 + 6:
                    cx = bx0 + 6
                    cy += row_h + 4
                    row_h = 0
                ax, ay = snap(cx - ex0), snap(cy - ey0)
                placed.append((p, sym, resolved, ax, ay))
                cx += w + 6
                row_h = max(row_h, h)
            by1 = cy + row_h + 6
            frames += frame(name, bx0, by0, bx0 + BLOCK_WIDTH, by1)
            y_cursor = by1 + GAP
        max_y = max(max_y, y_cursor)
        col_x += BLOCK_WIDTH + GAP
    return symbols, placed, frames, col_x + 8, max_y + 8


def build():
    symbols, placed, frames, width, height = layout()

    sch = [Sym("kicad_sch"),
           [Sym("version"), 20250610],
           [Sym("generator"), "rc_car_generator"],
           [Sym("generator_version"), "10.0"],
           [Sym("uuid"), ROOT_UUID],
           [Sym("paper"), "User", round(width, 1), round(height, 1)],
           [Sym("title_block"), [Sym("title"), "RC Car Mainboard"], [Sym("rev"), "1"],
            [Sym("comment"), 1, "Generated from PCB/generator/design.py - edit that, not this file"]],
           [Sym("lib_symbols")] + list(symbols.values())]

    for p, sym, resolved, x, y in placed:
        sch.append(symbol_instance(p, sym, x, y, resolved))
        sch.extend(pin_connections(p, x, y, resolved))
    sch.extend(frames)
    sch.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
    sch.append([Sym("embedded_fonts"), Sym("no")])

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, PROJECT + ".kicad_sch"), "w", encoding="utf-8", newline="\n") as f:
        f.write(dump(sch) + "\n")

    pro = os.path.join(OUT_DIR, PROJECT + ".kicad_pro")
    if not os.path.exists(pro):     # gen_pcb.py fills in rules and net classes
        with open(pro, "w", encoding="utf-8") as f:
            json.dump({"meta": {"filename": PROJECT + ".kicad_pro", "version": 3}}, f, indent=2)

    print(f"Schematic: {len(placed)} symbols, sheet {width:.0f} x {height:.0f} mm")
    return placed


if __name__ == "__main__":
    build()
