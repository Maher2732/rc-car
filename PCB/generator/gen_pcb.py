"""Generates PCB/mainboard/rc_mainboard.kicad_pcb from design.py.

Run with KiCad's Python:
    "C:/Users/<you>/AppData/Local/Programs/KiCad/10.0/bin/python.exe" gen_pcb.py

Big parts are placed by hand (PLACEMENT). Each small passive is then placed next to the
pad it connects to on its "anchor" part, avoiding overlaps.
"""

import math
import os

import pcbnew

import design
from gen_sch import uid
from pcb_common import MM, board_parts, load_footprint, pad_nets

OUT = os.path.join(os.path.dirname(__file__), "..", "mainboard", "rc_mainboard.kicad_pcb")

# Board origin on the KiCad sheet, and size
OX, OY = 50.0, 40.0
W, H = 130.0, 100.0
CORNER = 3.0

# ref: (x, y, rotation_deg, side)   coordinates in board mm, (0,0) = top-left corner
PLACEMENT = {
    # ---- power strip, left edge ----
    "J1": (17.0, 21.0, 90, "F"),          # battery in, opening faces the left edge
    "F1": (25.0, 22.0, 270, "F"),         # 30 A blade fuse, runs top to bottom
    "Q1": (25.0, 43.0, 90, "F"),          # reverse polarity: drain up (fuse), source down
    "Q2": (25.0, 52.0, 270, "F"),         # on/off: source up (faces Q1), drain down
    "C1": (20.25, 46.5, 90, "F"),         # soft-start cap and gate pull-up sit inside the VBAT_RP pour
    "R2": (18.3, 46.5, 90, "F"),
    "J2": (17.0, 77.0, 90, "F"),          # to BTS7960, opening faces the left edge
    "SW1": (26.0, 93.6, 0, "F"),          # power switch, lever over the bottom edge
    "F2": (38.0, 60.0, 90, "F"),

    # ---- ESP32s, antennas over the top edge ----
    "U1": (56.0, 12.8, 0, "F"),
    "U2": (105.0, 12.8, 0, "F"),          # 49 mm from U1 so the antenna keep-outs don't overlap
    "C24": (92.0, 10.5, 90, "F"),         # U2 EN capacitor, beside the EN pin
    "R30": (92.0, 15.0, 90, "F"),         # battery divider bottom, beside IO34

    # ---- drive node I/O ----
    "J6": (40.0, 26.2, 180, "F"),         # BTS7960 ribbon header, pin 1 at the bottom to line up with IO25/26/33

    # ---- servo 5 A buck ----
    "U3": (52.0, 46.0, 0, "F"),
    "L1": (52.0, 59.0, 0, "F"),
    "D1": (63.0, 46.0, 90, "F"),
    "J7": (56.0, 69.0, 90, "F"),          # servo, right next to its supply
    "C29": (47.0, 70.0, 0, "F"),          # servo bulk electrolytic

    # ---- logic supply ----
    "U4": (76.0, 46.0, 0, "F"),
    "L2": (83.0, 46.0, 0, "F"),
    "U5": (78.0, 57.0, 0, "F"),
    "D2": (88.0, 54.0, 90, "F"),
    "D3": (66.0, 72.0, 90, "F"),
    "D4": (93.0, 72.0, 90, "F"),

    # ---- CAN ----
    "U8": (75.0, 22.0, 90, "F"),
    "U9": (118.0, 30.0, 0, "F"),
    "J5": (125.0, 84.0, 90, "F"),         # CAN to Pi, right edge
    "D6": (119.5, 84.0, 90, "F"),

    # ---- display ----
    "J8": (126.0, 33.0, 0, "F"),
    "Q7": (118.0, 40.0, 0, "F"),

    # ---- USB / CH340, USB-C openings over the bottom edge ----
    "J3": (56.0, 96.3, 0, "F"),
    "U6": (56.0, 80.0, 90, "F"),
    "J4": (105.0, 96.3, 0, "F"),
    "U7": (105.0, 80.0, 90, "F"),

    # ---- mounting holes ----
    "H1": (4.5, 45.0, 0, "F"),
    "H2": (4.5, 95.5, 0, "F"),
    "H3": (125.5, 95.5, 0, "F"),
    "H4": (90.0, 31.0, 0, "F"),
}

POWER_NETS = {"GND", "+3V3", "5V_SYS", "5V_LOG", "5V_SERVO", "VBAT_LOG", "VBAT_SW", "VBAT_RP",
              "VBAT_F", "VBAT_IN", "VBUS_A", "VBUS_B"}

NETCLASSES = {
    # name: (track mm, clearance mm, via dia, via drill, nets)
    "HighCurrent": (3.0, 0.3, 1.0, 0.5, ["VBAT_IN", "VBAT_F", "VBAT_RP", "VBAT_SW"]),
    "Power": (0.8, 0.2, 0.8, 0.4, ["VBAT_LOG", "5V_SERVO", "SRV_SW", "5V_LOG", "5V_SYS", "+3V3"]),
    # Logic buck switch node: short, ~2 A peak, and has to fit a 0.95 mm-pitch TSOT-23 pin
    "SmallPower": (0.5, 0.2, 0.6, 0.3, ["LOG_SW", "LOG_BST"]),
    "CAN": (0.3, 0.2, 0.6, 0.3, ["CAN_H", "CAN_L"]),
    "USB": (0.3, 0.2, 0.6, 0.3, ["USB_DP_A", "USB_DM_A", "USB_DP_B", "USB_DM_B"]),
}
DEFAULT_TRACK = 0.25


def at(x, y):
    return pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))


# ---------------------------------------------------------------------
# Board setup
# ---------------------------------------------------------------------

def setup_board(board):
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_TrackMinWidth = MM(0.12)          # PCBWay standard minimum is 0.1 mm
    ds.m_ViasMinSize = MM(0.6)
    ds.m_MinThroughDrill = MM(0.2)         # ESP32 footprint thermal vias; PCBWay standard minimum is 0.2 mm
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_MinClearance = MM(0.15)
    ds.SetAuxOrigin(at(0, H))                # drill/placement origin: bottom-left corner

    netclasses = ds.m_NetSettings
    default = netclasses.GetDefaultNetclass()
    default.SetTrackWidth(MM(DEFAULT_TRACK))
    default.SetClearance(MM(0.2))
    default.SetViaDiameter(MM(0.6))
    default.SetViaDrill(MM(0.3))
    for name, (track, clear, via, drill, nets) in NETCLASSES.items():
        nc = pcbnew.NETCLASS(name)
        nc.SetTrackWidth(MM(track))
        nc.SetClearance(MM(clear))
        nc.SetViaDiameter(MM(via))
        nc.SetViaDrill(MM(drill))
        netclasses.SetNetclass(name, nc)
        for n in nets:
            netclasses.SetNetclassPatternAssignment("/" + n, name)

    # Edge cuts: rounded rectangle
    def line(x0, y0, x1, y1):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(at(x0, y0)); s.SetEnd(at(x1, y1))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1))
        board.Add(s)

    def arc(cx, cy, sx, sy, ang):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        s.SetCenter(at(cx, cy)); s.SetStart(at(sx, sy))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1))
        board.Add(s)

    r = CORNER
    line(r, 0, W - r, 0); line(W, r, W, H - r); line(W - r, H, r, H); line(0, H - r, 0, r)
    arc(r, r, 0, r, 90); arc(W - r, r, W - r, 0, 90); arc(W - r, H - r, W, H - r, 90); arc(r, H - r, r, H, 90)


# ---------------------------------------------------------------------
# Footprints
# ---------------------------------------------------------------------

def add_footprints(board):
    nets = {}
    for name in design.all_nets():
        ni = pcbnew.NETINFO_ITEM(board, "/" + name)   # schematic local labels are "/NAME"
        board.Add(ni)
        nets[name] = ni

    fps = {}
    for p in board_parts():
        fp = load_footprint(p["footprint"])
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + uid("sym", p["ref"])))
        fp.SetFPIDAsString(p["footprint"])
        mapping = pad_nets(p, include_nc=True)
        for pad in fp.Pads():
            n = mapping.get(pad.GetNumber())
            if n and n.startswith("!"):
                if n not in nets:
                    nets[n] = pcbnew.NETINFO_ITEM(board, n[1:])
                    board.Add(nets[n])
                pad.SetNet(nets[n])
            elif n:
                pad.SetNet(nets[n])
        # Small parts: reference on the assembly drawing only, keeping the silkscreen clean
        lib, name = p["footprint"].split(":")
        if lib in ("Resistor_SMD", "Capacitor_SMD", "LED_SMD", "Jumper") \
                or name in ("SOT-23", "SOD-123", "SOT-23-6", "TSOT-23-6"):
            fp.Reference().SetLayer(pcbnew.F_Fab)
        fp.Value().SetLayer(pcbnew.F_Fab)       # values belong on the assembly drawing, not the silkscreen
        if p["mpn"]:
            fp.SetField("MPN", p["mpn"])
            mpn = next(f for f in fp.GetFields() if f.GetName() == "MPN")
            mpn.SetVisible(False)
            mpn.SetLayer(pcbnew.F_Fab)
        # Unnumbered pads inside a numbered pad (thermal vias on exposed pads) share its net
        for pad in fp.Pads():
            if pad.GetNumber() == "" and pad.HasHole():
                for other in fp.Pads():
                    if other.GetNumber() and other.GetNetCode() and other.HitTest(pad.GetPosition()):
                        pad.SetNet(other.GetNet())
                        break
        board.Add(fp)
        fps[p["ref"]] = (fp, p)
    return fps, nets


def place(fp, x, y, rot, side):
    if side == "B":
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(at(x, y))


def courtyard_box(fp, margin=0.15):
    cy = fp.GetCourtyard(pcbnew.F_CrtYd if not fp.IsFlipped() else pcbnew.B_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
    return (pcbnew.ToMM(bb.GetLeft()) - OX - margin, pcbnew.ToMM(bb.GetTop()) - OY - margin,
            pcbnew.ToMM(bb.GetRight()) - OX + margin, pcbnew.ToMM(bb.GetBottom()) - OY + margin)


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# Keep-out rectangles nothing small may be placed in (board mm)
KEEPOUTS = [
    (46.0, 0.0, 66.0, 7.5),     # U1 antenna
    (95.0, 0.0, 115.0, 7.5),    # U2 antenna
]


def anchor_for(p, fps, placed_refs):
    """The placed part (and pad) this passive should sit next to."""
    mine = {n for n in p["nets"].values() if n != "NC"}
    signal = [n for n in mine if n not in POWER_NETS]
    best = None
    for ref in placed_refs:
        fp, other = fps[ref]
        if other["ref"].startswith("H"):
            continue
        for pad in fp.Pads():
            name = pad.GetNetname().lstrip("/")
            if name in signal:
                return fp, pad
            if best is None and name in mine and name != "GND":
                best = (fp, pad)
    return best


def auto_place(fps):
    boxes = [courtyard_box(fps[r][0]) for r in PLACEMENT if r in fps]
    placed = [r for r in PLACEMENT if r in fps]
    pending = [r for r in fps if r not in PLACEMENT]

    # Parts with signal nets first, so they get the spots next to their IC pins
    def priority(ref):
        nets = set(fps[ref][1]["nets"].values())
        return 0 if nets - POWER_NETS - {"NC"} else 1
    pending.sort(key=priority)

    for ref in pending:
        fp, p = fps[ref]
        anchor = anchor_for(p, fps, placed)
        if anchor:
            tx = pcbnew.ToMM(anchor[1].GetPosition().x) - OX
            ty = pcbnew.ToMM(anchor[1].GetPosition().y) - OY
        else:
            tx, ty = W / 2, H / 2
        done = False
        for radius in [i * 0.5 for i in range(1, 60)]:
            for k in range(max(8, int(radius * 6))):
                a = 2 * math.pi * k / max(8, int(radius * 6))
                x = round((tx + radius * math.cos(a)) * 4) / 4
                y = round((ty + radius * math.sin(a)) * 4) / 4
                for rot in (0, 90):
                    place(fp, x, y, rot, "F")
                    box = courtyard_box(fp)
                    if box[0] < 1 or box[1] < 1 or box[2] > W - 1 or box[3] > H - 1:
                        continue
                    if any(overlaps(box, b) for b in boxes + KEEPOUTS + label_boxes()):
                        continue
                    boxes.append(box)
                    placed.append(ref)
                    done = True
                    break
                if done:
                    break
            if done:
                break
        if not done:
            raise SystemExit(f"Could not place {ref}")


# ---------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------

def add_zone(board, net, layer, poly, priority=0, keepout=False, name=""):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if keepout:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetZoneName(name)
    else:
        z.SetNet(net)
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(MM(0.3))
        z.SetMinThickness(MM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetThermalReliefGap(MM(0.4))
        z.SetThermalReliefSpokeWidth(MM(0.6))
    outline = z.Outline()
    outline.NewOutline()
    for x, y in poly:
        outline.Append(MM(OX + x), MM(OY + y))
    board.Add(z)
    return z


# Solid copper for the battery -> motor path (F.Cu, above the ground pour).
# Each is drawn generously: the fill keeps clearance from other nets' pads by itself.
POWER_POURS = {
    "VBAT_IN": [(14.0, 18.0), (28.0, 18.0), (28.0, 27.4), (14.0, 27.4)],
    "VBAT_F": [(20.0, 29.4), (30.0, 29.4), (30.0, 44.3), (20.0, 44.3)],
    "VBAT_RP": [(17.6, 44.9), (26.25, 44.9), (26.25, 46.6), (27.5, 46.6), (27.5, 49.9),
                (23.7, 49.9), (23.7, 48.4), (21.4, 48.4), (21.4, 46.3), (17.6, 46.3)],
    "VBAT_SW": [(21.7, 50.4), (29.5, 50.4), (29.5, 60.5), (40.5, 60.5), (40.5, 66.0),
                (26.0, 66.0), (20.5, 72.5), (20.5, 80.6), (13.5, 80.6), (13.5, 72.0), (21.7, 64.0)],
}


def add_zones(board, nets):
    full = [(0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, H - 0.5), (0.5, H - 0.5)]
    add_zone(board, nets["GND"], pcbnew.B_Cu, full)
    add_zone(board, nets["GND"], pcbnew.F_Cu, full)
    for net, poly in POWER_POURS.items():
        z = add_zone(board, nets[net], pcbnew.F_Cu, poly, priority=10)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)     # no thermal spokes on motor current
        z.SetMinThickness(MM(0.5))
    # No copper under either antenna, on both layers
    for i, (x0, y0, x1, y1) in enumerate(KEEPOUTS):
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            add_zone(board, None, layer, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], keepout=True,
                     name=f"antenna_{i + 1}")


# ---------------------------------------------------------------------
# Silkscreen labels
# ---------------------------------------------------------------------

def add_text(board, text, x, y, size=1.2, layer=pcbnew.F_SilkS, rot=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(at(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(size * 0.15))
    t.SetTextAngleDegrees(rot)
    board.Add(t)


# (text, x, y, size, rotation): auto-placement keeps parts off these
LABELS = [
    ("BATTERY 2S", 9.0, 32.0, 1.2, 0),
    ("TO BTS7960 B+/B-", 14.0, 90.8, 0.9, 0),
    ("ON / OFF", 26.0, 87.5, 1.2, 0),
    ("SERVO  S + -", 58.5, 66.0, 1.0, 0),
    ("BTS7960", 40.0, 29.2, 1.0, 0),
    ("USB DRIVE", 56.0, 89.3, 1.0, 0),
    ("USB TELEMETRY", 105.0, 89.3, 1.0, 0),
    ("CAN TO PI  G L H", 121.5, 81.5, 1.0, 90),
    ("DISPLAY", 122.0, 72.0, 1.0, 90),
    ("RC CAR MAINBOARD  rev 1", 78.0, 70.0, 1.5, 0),
]


def label_boxes():
    boxes = []
    for text, x, y, size, rot in LABELS:
        half_w = len(text) * size * 0.95 / 2 + 0.3
        half_h = size * 0.8
        if rot == 90:
            half_w, half_h = half_h, half_w
        boxes.append((x - half_w, y - half_h, x + half_w, y + half_h))
    return boxes


def add_labels(board):
    for text, x, y, size, rot in LABELS:
        add_text(board, text, x, y, size, rot=rot)


def write_project():
    """Design rules and net classes live in the .kicad_pro in KiCad 10, so DRC and the
    autorouter read them from there."""
    import json
    pro = os.path.join(os.path.dirname(OUT), "rc_mainboard.kicad_pro")

    def netclass(name, track, clearance, via, drill, priority):
        return {"name": name, "track_width": track, "clearance": clearance, "via_diameter": via,
                "via_drill": drill, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
                "wire_width": 6, "bus_width": 12, "line_style": 0, "priority": priority,
                "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)"}

    classes = [netclass("Default", DEFAULT_TRACK, 0.2, 0.6, 0.3, 2147483647)]
    patterns = []
    for i, (name, (track, clear, via, drill, nets)) in enumerate(NETCLASSES.items()):
        classes.append(netclass(name, track, clear, via, drill, i))
        patterns += [{"netclass": name, "pattern": "/" + n} for n in nets]

    project = {
        "board": {"design_settings": {"rules": {
            "min_clearance": 0.15, "min_track_width": 0.12, "min_via_diameter": 0.45,
            "min_via_annular_width": 0.1, "min_through_hole_diameter": 0.2,
            "min_hole_to_hole": 0.25, "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.25,
        }}},
        "meta": {"filename": "rc_mainboard.kicad_pro", "version": 3},
        "net_settings": {"classes": classes, "meta": {"version": 4}, "netclass_patterns": patterns},
    }
    with open(pro, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)


def build():
    board = pcbnew.BOARD()
    setup_board(board)
    fps, nets = add_footprints(board)
    for ref, (x, y, rot, side) in PLACEMENT.items():
        place(fps[ref][0], x, y, rot, side)
    auto_place(fps)
    add_zones(board, nets)
    add_labels(board)
    board.Save(OUT)
    write_project()
    print(f"Board saved: {len(fps)} footprints, {len(nets)} nets")
    return board


if __name__ == "__main__":
    build()
