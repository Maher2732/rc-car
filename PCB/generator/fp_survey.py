"""Prints the size and pad names of every footprint used (planning aid)."""

import pcbnew

from pcb_common import board_parts, load_footprint, pad_nets

seen = {}
for p in board_parts():
    fp_id = p["footprint"]
    nets = pad_nets(p)
    if fp_id not in seen:
        fp = load_footprint(fp_id)
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else fp.GetBoundingBox(False)
        pads = sorted({pad.GetNumber() for pad in fp.Pads()})
        seen[fp_id] = (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()), pads,
                       pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()))
    w, h, pads, x, y = seen[fp_id]
    missing = [n for n in pads if n and n not in nets]
    unknown = [n for n in nets if n not in pads]
    if p["ref"][0] in "UJQFSLD" or missing or unknown:
        print(f"{p['ref']:5} {fp_id.split(':')[1][:52]:52} {w:6.1f} x {h:5.1f}  origin-offset ({x:.1f},{y:.1f})"
              + (f"  UNCONNECTED PADS {missing}" if missing else "")
              + (f"  NO SUCH PAD {unknown}" if unknown else ""))
