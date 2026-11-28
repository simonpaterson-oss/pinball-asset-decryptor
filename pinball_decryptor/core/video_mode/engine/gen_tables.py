"""Writes vm_tables.h: the engine's integer tables (PAD-1657).

The engine keeps every rule in 16.16 fixed point, so it never calls a float sine,
arctangent or power at run time: these tables are made once here, with Python's
floats, and committed. Run it again only to change a table's size.

    python gen_tables.py      (from this folder)
"""
import math
import os

ONE = 65536


def fx(v):
    return int(round(v * ONE))


def table(name, values, per_line=8):
    out = ["static const int32_t %s[%d] = {" % (name, len(values))]
    for i in range(0, len(values), per_line):
        out.append("    " + ", ".join(str(v) for v in values[i:i + per_line]) + ",")
    out.append("};")
    return "\n".join(out)


def main(path=None):
    parts = [
        "/* vm_tables.h - made by gen_tables.py; do not edit by hand (PAD-1657). */",
        "#ifndef VM_TABLES_H",
        "#define VM_TABLES_H",
        "",
        "/* sin over a quarter turn, 0..90 degrees in 256 steps, 16.16 */",
        "#define VM_SIN_STEPS 256",
        table("vm_sin_q", [fx(math.sin(math.radians(90.0 * i / 256))) for i in range(257)]),
        "",
        "/* atan(r) in degrees (16.16) for r = 0..1 in 256 steps */",
        "#define VM_ATAN_STEPS 256",
        table("vm_atan_t", [fx(math.degrees(math.atan(i / 256.0))) for i in range(257)]),
        "",
        "/* 2^-(i/64) for i = 0..64, 16.16: the fraction part of a negative power of two */",
        table("vm_exp2_neg", [fx(2.0 ** (-i / 64.0)) for i in range(65)]),
        "",
        "#endif",
        "",
    ]
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "vm_tables.h")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(parts))


if __name__ == "__main__":
    main()
