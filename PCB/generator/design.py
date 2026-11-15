"""RC car mainboard: every part and every connection, in one place.

Both the schematic and the PCB are generated from this file, so they can't drift apart.
Pin keys are pin names from the KiCad symbol (or pin numbers); "NC" marks no-connect.

Firmware pin map (must match firmware/main/drive/config.h, telemetry/config.h, menuconfig):
  Drive ESP32     IO18 servo, IO25 RPWM, IO26 LPWM, IO33 motor enable, IO4/IO5 CAN
  Telemetry ESP32 IO34 battery, IO4/IO5 CAN,
                  display SPI: IO18 SCK, IO23 MOSI, IO19 MISO, IO13 LCD_CS, IO21 LCD_DC,
                  IO22 LCD_RST, IO32 backlight, IO14 touch CS, IO35 touch IRQ
"""

from collections import Counter, defaultdict

# ---------- Footprints ----------
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"

PARTS = []


def part(prefix, lib_id, value, footprint, nets, block, mpn="", ref=None):
    """ref=None gets the next free number for its prefix once the design is complete."""
    PARTS.append(dict(ref=ref, prefix=prefix, lib_id=lib_id, value=value, footprint=footprint,
                      nets=nets, block=block, mpn=mpn))


def R(value, a, b, block, fp=R0603):
    return part("R", "Device:R", value, fp, {"1": a, "2": b}, block)


def C(value, a, b, block, fp=C0603):
    return part("C", "Device:C", value, fp, {"1": a, "2": b}, block)


def pwr_flag(net, block):
    part("#FLG", "power:PWR_FLAG", "PWR_FLAG", "", {"1": net}, block)


# =====================================================================
# POWER INPUT, ON/OFF SWITCH, PROTECTION
# =====================================================================
B = "Power input & switch"

part("J", "Connector:Screw_Terminal_01x02", "BATTERY 2S (XT60)",
     "Connector_AMASS:AMASS_XT60PW-M_1x02_P7.20mm_Horizontal",
     {"1": "VBAT_IN", "2": "GND"}, B, "XT60PW-M", ref="J1")
part("F", "Device:Fuse", "30A ATO blade",
     "Fuse:FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165",
     {"1": "VBAT_IN", "2": "VBAT_F"}, B, "Littelfuse 178.6165", ref="F1")

# Q1: reverse-polarity protection (body diode conducts first, then the gate turns it fully on)
part("Q", "Transistor_FET:SQJ409EP", "SQJ409EP", "Package_SO:PowerPAK_SO-8L_Single",
     {"D": "VBAT_F", "S": "VBAT_RP", "G": "Q1_G"}, B, "SQJ409EP-T1_GE3", ref="Q1")
R("10k", "Q1_G", "GND", B)

# Q2: soft power switch. SW1 pulls the gate low -> car on. Back-to-back with Q1, so
# no body diode path exists when off.
part("Q", "Transistor_FET:SQJ409EP", "SQJ409EP", "Package_SO:PowerPAK_SO-8L_Single",
     {"S": "VBAT_RP", "D": "VBAT_SW", "G": "PWR_GATE"}, B, "SQJ409EP-T1_GE3", ref="Q2")
R("47k", "PWR_GATE", "VBAT_RP", B)              # default off
C("1uF", "PWR_GATE", "VBAT_RP", B, C0805)       # ~10 ms soft start, limits inrush
R("10k", "PWR_GATE", "SW_COM", B)
part("SW", "Switch:SW_SPDT", "POWER",
     "Button_Switch_THT:SW_Slide_SPDT_Angled_CK_OS102011MA1Q",
     {"A": "GND", "B": "SW_COM", "C": "NC"}, B, "OS102011MA1QN1", ref="SW1")

part("J", "Connector:Screw_Terminal_01x02", "TO BTS7960 B+/B- (XT60)",
     "Connector_AMASS:AMASS_XT60PW-F_1x02_P7.20mm_Horizontal",
     {"1": "VBAT_SW", "2": "GND"}, B, "XT60PW-F", ref="J2")
pwr_flag("VBAT_IN", B)
pwr_flag("GND", B)

# Logic branch gets its own resettable fuse
part("F", "Device:Polyfuse", "3A hold", "Fuse:Fuse_2920_7451Metric",
     {"1": "VBAT_SW", "2": "VBAT_LOG"}, B, "PTC 2920 3A hold", ref="F2")
pwr_flag("VBAT_LOG", B)


# =====================================================================
# SERVO SUPPLY: TPS54560B, 5 V / 5 A
# =====================================================================
B = "Servo 5V / 5A"

part("U", "Regulator_Switching:TPS54560BDDA", "TPS54560B",
     "Package_SO:Texas_R-PDSO-G8_EP2.95x4.9mm_Mask2.4x3.1mm_ThermalVias",
     {"VIN": "VBAT_LOG", "EN": "NC", "RT/CLK": "SRV_RT", "FB": "SRV_FB",
      "COMP": "SRV_COMP", "GND": "GND", "SW": "SRV_SW", "BOOT": "SRV_BOOT"},
     B, "TPS54560BDDAR", ref="U3")
C("10uF 25V", "VBAT_LOG", "GND", B, C1206)
C("10uF 25V", "VBAT_LOG", "GND", B, C1206)
C("100nF", "VBAT_LOG", "GND", B)
C("100nF", "SRV_BOOT", "SRV_SW", B)
R("200k", "SRV_RT", "GND", B)                    # ~490 kHz
R("16.9k", "SRV_COMP", "SRV_CZ", B)
C("4.7nF", "SRV_CZ", "GND", B)
C("47pF", "SRV_COMP", "GND", B)
part("D", "Device:D_Schottky", "B560C", "Diode_SMD:D_SMC",
     {"1": "SRV_SW", "2": "GND"}, B, "B560C-13-F")
part("L", "Device:L", "4.7uH 8A", "Inductor_SMD:L_Bourns_SRP1038C_10.0x10.0mm",
     {"1": "SRV_SW", "2": "5V_SERVO"}, B, "SRP1038C-4R7M")
R("52.3k", "5V_SERVO", "SRV_FB", B)              # Vout = 0.8 * (1 + 52.3/10) = 4.98 V
R("10k", "SRV_FB", "GND", B)
C("47uF 10V", "5V_SERVO", "GND", B, C1206)
C("47uF 10V", "5V_SERVO", "GND", B, C1206)
C("47uF 10V", "5V_SERVO", "GND", B, C1206)


# =====================================================================
# LOGIC SUPPLY: AP63205 5 V, USB OR-ing, AMS1117 3.3 V
# =====================================================================
B = "Logic 5V / 3.3V"

part("U", "Regulator_Switching:AP63205WU", "AP63205", "Package_TO_SOT_SMD:TSOT-23-6",
     {"IN": "VBAT_LOG", "EN": "VBAT_LOG", "GND": "GND", "FB": "5V_LOG",
      "SW": "LOG_SW", "BST": "LOG_BST"}, B, "AP63205WU-7", ref="U4")
C("10uF 25V", "VBAT_LOG", "GND", B, C1206)
C("100nF", "LOG_BST", "LOG_SW", B)
part("L", "Device:L", "4.7uH 3A", "Inductor_SMD:L_Bourns-SRN4018",
     {"1": "LOG_SW", "2": "5V_LOG"}, B, "SRN4018-4R7M")
C("22uF 10V", "5V_LOG", "GND", B, C0805)
C("22uF 10V", "5V_LOG", "GND", B, C0805)

# Battery, USB A and USB B can each power the logic; diodes stop back-feeding
part("D", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", {"1": "5V_SYS", "2": "5V_LOG"}, B, "SS34")
part("D", "Device:D_Schottky", "B5819W", "Diode_SMD:D_SOD-123", {"1": "5V_SYS", "2": "VBUS_A"}, B, "B5819W")
part("D", "Device:D_Schottky", "B5819W", "Diode_SMD:D_SOD-123", {"1": "5V_SYS", "2": "VBUS_B"}, B, "B5819W")
pwr_flag("5V_SYS", B)

part("U", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
     {"VI": "5V_SYS", "VO": "+3V3", "GND": "GND"}, B, "AMS1117-3.3", ref="U5")
C("10uF", "5V_SYS", "GND", B, C0805)
C("22uF", "+3V3", "GND", B, C0805)
C("100nF", "+3V3", "GND", B)

R("1k", "+3V3", "LED_PWR", B)
part("D", "Device:LED", "PWR green", "LED_SMD:LED_0603_1608Metric",
     {"1": "GND", "2": "LED_PWR"}, B)


# =====================================================================
# ESP32 + USB-C + CH340C (one copy per node)
# =====================================================================

ESP32_USED = {
    "A": {"IO18": "SERVO_PWM", "IO25": "MOT_RPWM", "IO26": "MOT_LPWM", "IO33": "MOT_EN",
          "IO4": "CANA_TXD", "IO5": "CANA_RXD"},
    "B": {"IO34": "VBAT_SENSE",
          "IO4": "CANB_TXD", "IO5": "CANB_RXD",
          "IO18": "SPI_SCK", "IO23": "SPI_MOSI", "IO19": "SPI_MISO",
          "IO13": "LCD_CS", "IO21": "LCD_DC", "IO22": "LCD_RST", "IO32": "LCD_BL",
          "IO14": "TP_CS", "IO35": "TP_IRQ"},
}

ESP32_ALL_IO = ["SENSOR_VP", "SENSOR_VN", "IO34", "IO35", "IO32", "IO33", "IO25", "IO26", "IO27",
                "IO14", "IO12", "IO13", "IO15", "IO2", "IO4", "IO16", "IO17", "IO5", "IO18",
                "IO19", "IO21", "IO22", "IO23", "NC"]


def esp32_node(n, label, esp_ref, usb_ref, ch_ref):
    b = f"{label} ESP32 ({n})"
    nets = {"VDD": "+3V3", "GND": "GND", "EN": f"EN_{n}", "IO0": f"IO0_{n}",
            "TXD0/IO1": f"TXD_{n}", "RXD0/IO3": f"RXD_{n}"}
    for io in ESP32_ALL_IO:
        nets.setdefault(io, "NC")
    nets.update(ESP32_USED[n])
    part("U", "RF_Module:ESP32-WROOM-32E", f"ESP32-WROOM-32E ({label})",
         "RF_Module:ESP32-WROOM-32E", nets, b, "ESP32-WROOM-32E-N4", ref=esp_ref)
    C("10uF", "+3V3", "GND", b, C0805)
    C("100nF", "+3V3", "GND", b)
    R("10k", "+3V3", f"EN_{n}", b)
    C("1uF", f"EN_{n}", "GND", b)
    R("10k", "+3V3", f"IO0_{n}", b)

    # USB-C, device only: 5.1k on CC1/CC2 asks the host for 5 V
    part("J", "Connector:USB_C_Receptacle_USB2.0_16P", f"USB-C {label}",
         "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         {"VBUS": f"VBUS_{n}", "GND": "GND", "SHIELD": "GND", "CC1": f"CC1_{n}",
          "CC2": f"CC2_{n}", "D+": f"USB_DP_{n}", "D-": f"USB_DM_{n}",
          "SBU1": "NC", "SBU2": "NC"}, b, "TYPE-C-31-M-12", ref=usb_ref)
    R("5.1k", f"CC1_{n}", "GND", b)
    R("5.1k", f"CC2_{n}", "GND", b)
    part("U", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
         {"I/O1": f"USB_DP_{n}", "I/O2": f"USB_DM_{n}", "VBUS": f"VBUS_{n}", "GND": "GND"},
         b, "USBLC6-2SC6")
    pwr_flag(f"VBUS_{n}", b)

    # CH340C runs at 3.3 V so its TXD can't over-drive the ESP32
    part("U", "Interface_USB:CH340C", "CH340C", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
         {"VCC": "+3V3", "V3": f"V3_{n}", "GND": "GND", "UD+": f"USB_DP_{n}", "UD-": f"USB_DM_{n}",
          "TXD": f"RXD_{n}", "RXD": f"TXD_{n}", "~{DTR}": f"DTR_{n}", "~{RTS}": f"RTS_{n}",
          "R232": "GND", "~{CTS}": "NC", "~{DSR}": "NC", "~{RI}": "NC", "~{DCD}": "NC"},
         b, "CH340C", ref=ch_ref)
    R("0", f"V3_{n}", "+3V3", b)                # V3 tied to VCC for 3.3 V operation
    C("100nF", "+3V3", "GND", b)

    # Auto-program: the classic two-transistor DTR/RTS reset circuit
    part("Q", "Transistor_BJT:MMBT3904", "MMBT3904", SOT23,
         {"B": f"QB1_{n}", "E": f"RTS_{n}", "C": f"EN_{n}"}, b, "MMBT3904")
    R("10k", f"DTR_{n}", f"QB1_{n}", b)
    part("Q", "Transistor_BJT:MMBT3904", "MMBT3904", SOT23,
         {"B": f"QB2_{n}", "E": f"DTR_{n}", "C": f"IO0_{n}"}, b, "MMBT3904")
    R("10k", f"RTS_{n}", f"QB2_{n}", b)


esp32_node("A", "Drive", "U1", "J3", "U6")
esp32_node("B", "Telemetry", "U2", "J4", "U7")


# =====================================================================
# CAN BUS: two SN65HVD230 on-board, connector to the Raspberry Pi
# =====================================================================
B = "CAN bus"

for n, ref in (("A", "U8"), ("B", "U9")):
    part("U", "Interface_CAN_LIN:SN65HVD230", f"SN65HVD230 ({n})", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
         {"D": f"CAN{n}_TXD", "R": f"CAN{n}_RXD", "VCC": "+3V3", "GND": "GND",
          "Rs": "GND", "Vref": "NC", "CANH": "CAN_H", "CANL": "CAN_L"}, B, "SN65HVD230DR", ref=ref)
    C("100nF", "+3V3", "GND", B)

# Split termination (2 x 60R + 4.7nF): this board is one end of the bus.
# Cut JP1 if another node is placed after this board.
part("JP", "Jumper:SolderJumper_2_Bridged", "TERM", "Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm",
     {"1": "CAN_H", "2": "CAN_TERM"}, B, ref="JP1")
R("60.4", "CAN_TERM", "CAN_MID", B)
R("60.4", "CAN_MID", "CAN_L", B)
C("4.7nF", "CAN_MID", "GND", B)
part("D", "Device:D_TVS_Dual_AAC", "PESD2CAN", SOT23,
     {"A1": "CAN_H", "A2": "CAN_L", "common": "GND"}, B, "PESD2CAN,215")
part("J", "Connector_Generic:Conn_01x03", "CAN to Pi", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
     {"1": "CAN_H", "2": "CAN_L", "3": "GND"}, B, "B3B-XH-A", ref="J5")


# =====================================================================
# MOTOR DRIVER, SERVO, SENSORS
# =====================================================================
B = "Motor, servo, battery sense"

# 1:1 with the BTS7960 module header, so a straight 8-wire ribbon connects them
part("J", "Connector_Generic:Conn_01x08", "BTS7960", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
     {"1": "MOT_RPWM", "2": "MOT_LPWM", "3": "MOT_EN", "4": "MOT_EN", "5": "NC", "6": "NC",
      "7": "+3V3", "8": "GND"}, B, ref="J6")
R("10k", "MOT_RPWM", "GND", B)                  # motor stays off while the ESP32 boots
R("10k", "MOT_LPWM", "GND", B)
R("10k", "MOT_EN", "GND", B)

part("J", "Connector_Generic:Conn_01x03", "SERVO", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
     {"1": "SERVO_SIG", "2": "5V_SERVO", "3": "GND"}, B, ref="J7")
R("100", "SERVO_PWM", "SERVO_SIG", B)
part("C", "Device:C_Polarized", "470uF 10V", "Capacitor_SMD:CP_Elec_8x10",
     {"1": "5V_SERVO", "2": "GND"}, B)

R("100k", "VBAT_LOG", "VBAT_SENSE", B)          # 8.4 V -> 2.08 V
R("33k", "VBAT_SENSE", "GND", B)
C("100nF", "VBAT_SENSE", "GND", B)


# =====================================================================
# DISPLAY: 3.5" ILI9488 + XPT2046 touch, 14-pin header
# =====================================================================
B = "Display"

part("J", "Connector_Generic:Conn_01x14", "LCD ILI9488 3.5in", "Connector_PinSocket_2.54mm:PinSocket_1x14_P2.54mm_Vertical",
     {"1": "5V_SYS", "2": "GND", "3": "LCD_CS", "4": "LCD_RST", "5": "LCD_DC", "6": "SPI_MOSI",
      "7": "SPI_SCK", "8": "LCD_LED",
      "9": "NC",                                # LCD SDO: the ILI9488 never releases it, so leave it off the shared bus
      "10": "SPI_SCK", "11": "TP_CS", "12": "SPI_MOSI", "13": "SPI_MISO", "14": "TP_IRQ"},
     B, ref="J8")

# Backlight high-side switch. Gate pulled low = backlight on by default; IO32 high turns it off.
part("Q", "Transistor_FET:AO3401A", "AO3401A", SOT23,
     {"S": "+3V3", "D": "LCD_LED", "G": "LCD_BL"}, B, "AO3401A", ref="Q7")
R("10k", "LCD_BL", "GND", B)
R("10k", "+3V3", "TP_CS", B)                    # keep touch deselected during boot
R("10k", "+3V3", "LCD_CS", B)


# =====================================================================
# MECHANICAL
# =====================================================================
B = "Mechanical"
for i in range(4):
    part("H", "Mechanical:MountingHole_Pad", "M3", "MountingHole:MountingHole_3.2mm_M3_Pad_Via",
         {"1": "GND"}, B)


# =====================================================================
# Helpers used by the generators
# =====================================================================

def _number_parts():
    taken = {p["ref"] for p in PARTS if p["ref"]}
    counters = Counter()
    for p in PARTS:
        if p["ref"]:
            continue
        while True:
            counters[p["prefix"]] += 1
            ref = f"{p['prefix']}{counters[p['prefix']]}"
            if ref not in taken:
                break
        p["ref"] = ref
        taken.add(ref)
    refs = [p["ref"] for p in PARTS]
    dupes = {r for r in refs if refs.count(r) > 1}
    assert not dupes, f"duplicate references {dupes}"


_number_parts()


def blocks():
    out = defaultdict(list)
    for p in PARTS:
        out[p["block"]].append(p)
    return out


def all_nets():
    nets = set()
    for p in PARTS:
        nets.update(v for v in p["nets"].values() if v != "NC")
    return sorted(nets)


if __name__ == "__main__":
    print(len(PARTS), "parts,", len(all_nets()), "nets")
    for b, ps in blocks().items():
        print(f"  {b}: {len(ps)}")
