"""Full board build: generate, autoroute with Freerouting, fill zones, run DRC, export.

Run with KiCad's Python. Needs Freerouting and a Java runtime; set their paths with
FREEROUTING_JAR and JAVA (defaults point at a local tools folder).

    python route.py            # generate + route + DRC
    python route.py --export   # ... and write fabrication files to PCB/fab
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys

import pcbnew

import gen_pcb

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "..", "mainboard", "rc_mainboard.kicad_pcb")
WORK = os.environ.get("ROUTE_WORK", os.path.join(HERE, "..", "build"))
JAVA = os.environ.get("JAVA", "java")
JAR = os.environ.get("FREEROUTING_JAR", "freerouting.jar")
KICAD_CLI = os.path.join(os.path.dirname(sys.executable), "kicad-cli.exe")


def run_freerouting(dsn, ses, attempts=4):
    """Freerouting is multithreaded and not deterministic, so retry and keep the best run."""
    best = None
    for attempt in range(1, attempts + 1):
        out = f"{ses}.try{attempt}"
        cmd = [JAVA, "-jar", JAR, "-de", dsn, "-do", out, "-mp", "80", "--gui.enabled=false"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        log = result.stdout + result.stderr
        m = re.findall(r"final score: [\d.]+ \((\d+) unrouted", log)
        unrouted = int(m[-1]) if m else 999
        print(f"Freerouting attempt {attempt}: {unrouted} unrouted")
        if best is None or unrouted < best[0]:
            best = (unrouted, out)
        if unrouted == 0:
            break
    shutil.copyfile(best[1], ses)
    return best[0]


def remove_dangling(board):
    """Deletes router leftovers: track ends touching nothing, vias used on one layer only."""
    removed = 0
    while True:
        by_net = {}
        for item in board.GetTracks():
            by_net.setdefault(item.GetNetCode(), []).append(item)
        pads_by_net = {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                pads_by_net.setdefault(pad.GetNetCode(), []).append(pad)

        zones_by_net = {}
        for z in board.Zones():
            if not z.GetIsRuleArea():
                zones_by_net.setdefault(z.GetNetCode(), []).append(z)

        doomed = []
        kept_vias = []
        for v in board.GetTracks():
            if v.Type() == pcbnew.PCB_VIA_T:
                # Same-net vias closer than a drill apart are duplicates
                if any(k.GetNetCode() == v.GetNetCode() and
                       (k.GetPosition() - v.GetPosition()).EuclideanNorm() < pcbnew.FromMM(0.3) for k in kept_vias):
                    doomed.append(v)
                else:
                    kept_vias.append(v)
        for net, items in by_net.items():
            pads = pads_by_net.get(net, [])
            zones = zones_by_net.get(net, [])
            vias = [i for i in items if i.Type() == pcbnew.PCB_VIA_T and i not in doomed]
            tracks = [i for i in items if i.Type() == pcbnew.PCB_TRACE_T]

            def touches(point, layer, skip):
                for tr in tracks:
                    if tr is not skip and tr.GetLayer() == layer and tr.HitTest(point):
                        return True
                if skip is None or skip.Type() != pcbnew.PCB_VIA_T:   # a via can't keep another via alive
                    for v in vias:
                        if v is not skip and v.HitTest(point):
                            return True
                for pad in pads:
                    if pad.IsOnLayer(layer) and pad.HitTest(point):
                        return True
                for z in zones:          # copper pours (GND, battery path) also connect
                    if z.GetLayer() == layer and z.Outline().Contains(point):
                        return True
                return False

            for tr in tracks:
                if tr.GetLength() < pcbnew.FromMM(0.01):
                    doomed.append(tr)
                    continue
                if not (touches(tr.GetStart(), tr.GetLayer(), tr) and touches(tr.GetEnd(), tr.GetLayer(), tr)):
                    doomed.append(tr)
            if zones and len({z.GetLayer() for z in zones}) > 1:
                continue        # vias on a net poured on both layers stitch the pours together
            for v in vias:
                layers = sum(touches(v.GetPosition(), layer, v) for layer in (pcbnew.F_Cu, pcbnew.B_Cu))
                if layers < 2:
                    doomed.append(v)

        if not doomed:
            break
        for item in doomed:
            board.Remove(item)
        removed += len(doomed)
    print(f"Removed {removed} dangling track(s)/via(s)")


def add_stitching(board, pitch=4.0, keep=3.0):
    """GND vias wherever both ground pours overlap, tying the two layers together."""
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    gnd = board.FindNet("/GND")
    pours = {layer: [z for z in board.Zones() if z.GetNetCode() == gnd.GetNetCode() and z.GetLayer() == layer]
             for layer in (pcbnew.F_Cu, pcbnew.B_Cu)}
    existing = [v.GetPosition() for v in board.GetTracks()
                if v.Type() == pcbnew.PCB_VIA_T and v.GetNetCode() == gnd.GetNetCode()]
    edge = board.GetBoardEdgesBoundingBox()
    MM = pcbnew.FromMM
    pad_boxes = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            box = pad.GetBoundingBox()
            box.Inflate(MM(0.9))        # keep vias off pads and their holes
            pad_boxes.append(box)
    r = MM(0.75)                        # via radius + clearance, checked all around
    ring = [(int(r * dx), int(r * dy)) for dx, dy in
            [(1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)]]

    def clear_of_pads(p):
        return not any(b.Contains(p) for b in pad_boxes)

    tight = [(int(dx * 0.55 / 0.75), int(dy * 0.55 / 0.75)) for dx, dy in ring]

    def solid(layer, p, pts=None):
        pts = ring if pts is None else pts
        return any(all(z.HitTestFilledArea(layer, pcbnew.VECTOR2I(p.x + dx, p.y + dy)) for dx, dy in pts + [(0, 0)])
                   for z in pours[layer])

    added = 0

    def add_via(p):
        nonlocal added
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(p)
        via.SetWidth(MM(0.6))
        via.SetDrill(MM(0.3))
        via.SetNet(gnd)
        board.Add(via)
        existing.append(p)
        added += 1

    y = edge.GetTop() + MM(2.5)
    while y < edge.GetBottom() - MM(2.5):
        x = edge.GetLeft() + MM(2.5)
        while x < edge.GetRight() - MM(2.5):
            p = pcbnew.VECTOR2I(int(x), int(y))
            far = all((p - e).EuclideanNorm() > MM(keep) for e in existing)
            if far and clear_of_pads(p) and solid(pcbnew.F_Cu, p) and solid(pcbnew.B_Cu, p):
                add_via(p)
            x += MM(pitch)
        y += MM(pitch)

    # Any ground island still without a via gets one, so nothing is left floating
    for _ in range(3):
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        fixed = 0
        for layer, other in ((pcbnew.F_Cu, pcbnew.B_Cu), (pcbnew.B_Cu, pcbnew.F_Cu)):
            for z in pours[layer]:
                polys = z.GetFilledPolysList(layer)
                for i in range(polys.OutlineCount()):
                    outline = polys.Outline(i)
                    if any(outline.PointInside(e) for e in existing):
                        continue
                    bb = outline.BBox()
                    step = MM(0.5)
                    done = False
                    yy = bb.GetTop()
                    while yy < bb.GetBottom() and not done:
                        xx = bb.GetLeft()
                        while xx < bb.GetRight() and not done:
                            p = pcbnew.VECTOR2I(int(xx), int(yy))
                            far = all((p - e).EuclideanNorm() > MM(1.0) for e in existing)
                            if far and clear_of_pads(p) and solid(layer, p, tight) and solid(other, p, tight):
                                add_via(p)
                                fixed += 1
                                done = True
                            xx += step
                        yy += step
        if not fixed:
            break
    # Ground pads the pour couldn't reach (boxed in by traces): join each to ground copper
    # with a short trace, checked point by point so it can only run over the pad itself or
    # through existing ground fill (which already keeps clear of every other net).
    joined = 0
    for _ in range(4):
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        before = joined
        for layer, other in ((pcbnew.F_Cu, pcbnew.B_Cu), (pcbnew.B_Cu, pcbnew.F_Cu)):
            polys, main = main_pour(board, gnd, layer)
            if polys is None:
                continue
            for i in range(polys.OutlineCount()):
                if i == main:
                    continue
                island = polys.Outline(i)
                if any(island.PointInside(e) for e in existing):
                    continue
                pads = [p for fp in board.GetFootprints() for p in fp.Pads()
                        if p.GetNetCode() == gnd.GetNetCode() and p.IsOnLayer(layer)
                        and island.PointInside(p.GetPosition())]
                spot = join_island(board, gnd, layer, other, pads, polys, main)
                if spot is None:
                    spot = via_inside_island(board, gnd, layer, other, island)
                if spot is not None:
                    existing.append(spot)
                    joined += 1
        if joined == before:
            break
    print(f"Added {added} ground stitching vias, joined {joined} isolated ground pads")


def main_pour(board, gnd, layer):
    """(filled poly set, index of its biggest outline) for the ground pour on one layer."""
    for z in board.Zones():
        if z.GetNetCode() == gnd.GetNetCode() and not z.GetIsRuleArea() and z.GetLayer() == layer:
            polys = z.GetFilledPolysList(layer)
            if polys.OutlineCount():
                return polys, max(range(polys.OutlineCount()), key=lambda i: polys.Outline(i).Area())
    return None, -1


def gnd_fill_test(board, gnd):
    """in_fill(layer, point, radius): True if a disc of that radius is entirely ground fill."""
    zones = [z for z in board.Zones() if z.GetNetCode() == gnd.GetNetCode() and not z.GetIsRuleArea()]

    def in_fill(layer, p, r):
        d = int(r * 0.7)
        pts = [(0, 0), (r, 0), (-r, 0), (0, r), (0, -r), (d, d), (-d, d), (d, -d), (-d, -d)]
        return any(all(z.HitTestFilledArea(layer, pcbnew.VECTOR2I(p.x + dx, p.y + dy)) for dx, dy in pts)
                   for z in zones if z.GetLayer() == layer)
    return in_fill


def all_holes(board):
    vias = [v.GetPosition() for v in board.GetTracks() if v.Type() == pcbnew.PCB_VIA_T]
    pads = [p.GetPosition() for fp in board.GetFootprints() for p in fp.Pads() if p.HasHole()]
    return vias + pads


def add_gnd_via(board, gnd, p):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(p)
    via.SetWidth(pcbnew.FromMM(0.5))
    via.SetDrill(pcbnew.FromMM(0.25))
    via.SetNet(gnd)
    board.Add(via)


def join_island(board, gnd, layer, other, pads, polys, main):
    """Short trace from a boxed-in ground pad to the main pour (or to a via onto the other
    layer's main pour). Returns the end point, or None."""
    MM = pcbnew.FromMM
    in_fill = gnd_fill_test(board, gnd)
    other_polys, other_main = main_pour(board, gnd, other)
    holes = all_holes(board)

    # Ground pads already tied to the plane: inside the main pour, or with their own via holes
    # (e.g. an ESP32's centre pad with thermal vias)
    gnd_holes = [h for h in holes]
    anchors = []
    for fp in board.GetFootprints():
        for target in fp.Pads():
            if target.GetNetCode() != gnd.GetNetCode() or not target.IsOnLayer(layer):
                continue
            box = target.GetBoundingBox()
            if polys.Contains(target.GetPosition(), main) or any(box.Contains(h) for h in gnd_holes):
                anchors.append(target)

    for pad in pads:
        c = pad.GetPosition()
        pad_box = pad.GetBoundingBox()
        pad_box.Inflate(MM(0.3))

        # Straight trace to a nearby anchored ground pad, through fill or over the two pads
        for target in sorted(anchors, key=lambda a: (a.GetPosition() - c).EuclideanNorm()):
            end = target.GetPosition()
            dist = (end - c).EuclideanNorm()
            if dist > MM(12) or target is pad:
                continue
            target_box = target.GetBoundingBox()
            target_box.Inflate(MM(0.3))
            steps = max(1, int(dist / MM(0.1)))
            path_ok = all(
                pad_box.Contains(q) or target_box.Contains(q) or in_fill(layer, q, MM(0.25))
                for q in (pcbnew.VECTOR2I(int(c.x + (end.x - c.x) * s / steps),
                                          int(c.y + (end.y - c.y) * s / steps)) for s in range(1, steps)))
            if path_ok:
                add_track(board, gnd, layer, c, end)
                return end

        for dist in [MM(d) for d in (0.8, 1.2, 1.6, 2.0, 2.6, 3.2, 4.0, 5.0)]:
            for k in range(32):
                ang = 2 * math.pi * k / 32
                end = pcbnew.VECTOR2I(int(c.x + dist * math.cos(ang)), int(c.y + dist * math.sin(ang)))

                steps = int(dist / MM(0.1))
                path_ok = all(
                    pad_box.Contains(q) or in_fill(layer, q, MM(0.25))
                    for q in (pcbnew.VECTOR2I(int(c.x + (end.x - c.x) * s / steps),
                                              int(c.y + (end.y - c.y) * s / steps)) for s in range(1, steps + 1)))
                if not path_ok:
                    continue

                # Lands in the main pour on this layer (holes respected): a trace is enough
                if polys.Contains(end, main) and in_fill(layer, end, MM(0.25)):
                    add_track(board, gnd, layer, c, end)
                    return end

                # Otherwise drop through to the other layer's main pour
                lands_on_main = other_polys is not None and other_polys.Contains(end, other_main)
                clear_of_holes = all((end - h).EuclideanNorm() > MM(1.2) for h in holes)
                if lands_on_main and clear_of_holes and in_fill(other, end, MM(0.5)) and in_fill(layer, end, MM(0.2)):
                    add_track(board, gnd, layer, c, end)
                    add_gnd_via(board, gnd, end)
                    return end
    return None


def via_inside_island(board, gnd, layer, other, island):
    """Last resort: a small via inside the island itself, landing in the other layer's main pour."""
    MM = pcbnew.FromMM
    in_fill = gnd_fill_test(board, gnd)
    other_polys, other_main = main_pour(board, gnd, other)
    if other_polys is None:
        return None
    holes = all_holes(board)

    bb = island.BBox()
    step = MM(0.1)
    y = bb.GetTop()
    while y <= bb.GetBottom():
        x = bb.GetLeft()
        while x <= bb.GetRight():
            p = pcbnew.VECTOR2I(int(x), int(y))
            if (island.PointInside(p) and other_polys.Contains(p, other_main)
                    and all((p - h).EuclideanNorm() > MM(0.8) for h in holes)
                    and in_fill(layer, p, MM(0.25)) and in_fill(other, p, MM(0.45))):
                add_gnd_via(board, gnd, p)
                return p
            x += step
        y += step
    return None


def add_track(board, net, layer, a, b):
    tr = pcbnew.PCB_TRACK(board)
    tr.SetStart(a)
    tr.SetEnd(b)
    tr.SetWidth(pcbnew.FromMM(0.3))
    tr.SetLayer(layer)
    tr.SetNet(net)
    board.Add(tr)


def fill_and_save(board):
    board.BuildConnectivity()       # the filler needs current connectivity, or it fills stale
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(BOARD)


def drc(quiet=False):
    report = os.path.join(WORK, "drc.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--schematic-parity",
                    "--severity-error", "--severity-warning", "-o", report, BOARD], capture_output=True)
    with open(report, encoding="utf-8") as f:
        data = json.load(f)
    groups = {}
    for kind in ("violations", "unconnected_items", "schematic_parity"):
        for v in data.get(kind, []):
            key = (kind, v["severity"], v["type"])
            groups.setdefault(key, []).append(v)
    for (kind, sev, typ), items in sorted(groups.items()):
        if quiet:
            break
        print(f"  {kind:18} {sev:8} {typ:32} x{len(items)}")
        for v in items[:3]:
            print("      ", v["description"], "|", "; ".join(i["description"] for i in v["items"][:2]))
    return groups


def drc_cleanup():
    """Final pass using KiCad's own connectivity: drop any via or trace DRC calls dangling.
    Edits the board file directly (the SWIG bindings misbehave after removals), then refills
    the zones in a fresh process."""
    from sexpr import dump, parse

    for _ in range(4):
        groups = drc(quiet=True)
        flagged = (groups.get(("violations", "warning", "via_dangling"), []) +
                   groups.get(("violations", "warning", "track_dangling"), []))
        if not flagged:
            return
        spots = {(round(i["pos"]["x"], 2), round(i["pos"]["y"], 2)) for v in flagged for i in v["items"]}

        with open(BOARD, encoding="utf-8") as f:
            tree = parse(f.read())

        def at(node, key):
            for c in node:
                if isinstance(c, list) and c and c[0] == key:
                    return (round(float(c[1]), 2), round(float(c[2]), 2))
            return None

        kept = [tree[0]]
        for node in tree[1:]:
            if isinstance(node, list) and node and node[0] == "via" and at(node, "at") in spots:
                continue
            if isinstance(node, list) and node and node[0] == "segment" and (
                    at(node, "start") in spots or at(node, "end") in spots):
                continue
            kept.append(node)
        with open(BOARD, "w", encoding="utf-8", newline="\n") as f:
            f.write(dump(kept) + "\n")

        subprocess.run([sys.executable, "-c",
                        "import pcbnew; b = pcbnew.LoadBoard(r'%s'); b.BuildConnectivity(); "
                        "pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(r'%s')" % (BOARD, BOARD)],
                       capture_output=True)


def main():
    os.makedirs(WORK, exist_ok=True)
    gen_pcb.build()

    board = pcbnew.LoadBoard(BOARD)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    dsn = os.path.join(WORK, "rc.dsn")
    ses = os.path.join(WORK, "rc.ses")
    pcbnew.ExportSpecctraDSN(board, dsn)
    run_freerouting(dsn, ses)

    board = pcbnew.LoadBoard(BOARD)
    pcbnew.ImportSpecctraSES(board, ses)
    remove_dangling(board)
    add_stitching(board)
    fill_and_save(board)
    drc_cleanup()
    print("DRC:")
    drc()


if __name__ == "__main__":
    main()
