"""Writes everything PCBWay needs into PCB/fab/, plus renders into PCB/images/.

Run with KiCad's Python after route.py:
    gerbers + drill  -> fab/rc_mainboard_gerbers.zip   (upload for the bare board)
    bom              -> fab/rc_mainboard_bom.csv        (PCBWay assembly BOM)
    pick and place   -> fab/rc_mainboard_centroid.csv   (PCBWay assembly)
    schematic PDF    -> fab/rc_mainboard_schematic.pdf
"""

import csv
import os
import shutil
import subprocess
import sys
import zipfile
from collections import OrderedDict

import design

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
BOARD = os.path.join(ROOT, "mainboard", "rc_mainboard.kicad_pcb")
SCHEMATIC = os.path.join(ROOT, "mainboard", "rc_mainboard.kicad_sch")
FAB = os.path.join(ROOT, "fab")
IMAGES = os.path.join(ROOT, "images")
KICAD_CLI = os.path.join(os.path.dirname(sys.executable), "kicad-cli.exe")

THROUGH_HOLE = ("PinHeader", "PinSocket", "JST_XH", "AMASS", "FuseHolder", "SW_Slide", "MountingHole")

MANUFACTURERS = {
    "ESP32-WROOM-32E-N4": "Espressif", "CH340C": "WCH", "SN65HVD230DR": "Texas Instruments",
    "TPS54560BDDAR": "Texas Instruments", "AP63205WU-7": "Diodes Inc", "AMS1117-3.3": "Advanced Monolithic",
    "SQJ409EP-T1_GE3": "Vishay", "AO3401A": "Alpha & Omega", "USBLC6-2SC6": "STMicroelectronics",
    "MMBT3904": "onsemi", "B560C-13-F": "Diodes Inc", "SS34": "onsemi", "B5819W": "Diodes Inc",
    "PESD2CAN,215": "Nexperia", "TYPE-C-31-M-12": "Korean Hroparts", "OS102011MA1QN1": "C&K",
    "B3B-XH-A": "JST", "XT60PW-M": "AMASS", "XT60PW-F": "AMASS", "Littelfuse 178.6165": "Littelfuse",
    "SRP1038C-4R7M": "Bourns", "SRN4018-4R7M": "Bourns",
}


def cli(*args):
    result = subprocess.run([KICAD_CLI, *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)


def gerbers():
    out = os.path.join(FAB, "gerbers")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    layers = "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
    cli("pcb", "export", "gerbers", "--layers", layers, "--subtract-soldermask",
        "--use-drill-file-origin", "-o", out + os.sep, BOARD)
    cli("pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
        "--generate-map", "--map-format", "pdf", "-o", out + os.sep, BOARD)
    zip_path = os.path.join(FAB, "rc_mainboard_gerbers.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(out)):
            z.write(os.path.join(out, name), name)
    shutil.rmtree(out)
    return zip_path


def ref_sort_key(ref):
    """R2 before R10."""
    prefix = ref.rstrip("0123456789")
    return prefix, int(ref[len(prefix):])


def bom():
    groups = OrderedDict()
    for p in design.PARTS:
        if not p["footprint"] or p["ref"].startswith("H"):
            continue
        key = (p["value"], p["footprint"], p["mpn"])
        groups.setdefault(key, []).append(p["ref"])

    path = os.path.join(FAB, "rc_mainboard_bom.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Item #", "Designator", "Qty", "Manufacturer", "Mfg Part #",
                    "Description / Value", "Package/Footprint", "Type"])
        for i, ((value, fp, mpn), refs) in enumerate(groups.items(), 1):
            package = fp.split(":")[1]
            kind = "THT" if any(t in package for t in THROUGH_HOLE) else "SMD"
            designators = ",".join(sorted(refs, key=ref_sort_key))
            w.writerow([i, designators, len(refs), MANUFACTURERS.get(mpn, ""), mpn, value, package, kind])
    return path


def centroid():
    path = os.path.join(FAB, "rc_mainboard_centroid.csv")
    cli("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
        "--use-drill-file-origin", "-o", path, BOARD)
    return path


def renders():
    os.makedirs(IMAGES, exist_ok=True)
    for side in ("top", "bottom"):
        cli("pcb", "render", "--side", side, "--width", "1800", "--height", "1350", "--quality", "high",
            "--background", "opaque", "-o", os.path.join(IMAGES, f"mainboard_{side}.png"), BOARD)
    cli("pcb", "render", "--side", "top", "--rotate", "-35,0,25", "--zoom", "0.9", "--width", "1800",
        "--height", "1350", "--quality", "high", "--background", "opaque",
        "-o", os.path.join(IMAGES, "mainboard_angle.png"), BOARD)


def main():
    os.makedirs(FAB, exist_ok=True)
    print(gerbers())
    print(bom())
    print(centroid())
    cli("sch", "export", "pdf", "-o", os.path.join(FAB, "rc_mainboard_schematic.pdf"), SCHEMATIC)
    renders()
    print("renders ->", IMAGES)


if __name__ == "__main__":
    main()
