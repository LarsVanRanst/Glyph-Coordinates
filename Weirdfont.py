import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

from fontTools.ttLib import TTFont

MAGIC = b"WFNT"
HEAD = ">4sBBI32s"
HEAD_SIZE = struct.calcsize(HEAD)
FLAG_ZLIB = 1

def load_font(path):
    font = TTFont(path)
    if "glyf" not in font:
        sys.exit("error: this needs a TrueType font (with a 'glyf' table), not CFF/OTF.")
    if "fvar" in font:
        sys.exit("error: variable fonts are not supported, pick a static font.")
    return font


def slots(font):
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        g = glyf[name]
        if g.numberOfContours <= 0:
            continue
        for i in range(len(g.coordinates)):
            yield g, i, 0
            yield g, i, 1


def capacity_bytes(font):
    return sum(1 for _ in slots(font)) // 8


def set_bit(g, i, axis, bit):
    x, y = g.coordinates[i]
    x, y = int(x), int(y)
    if axis == 0:
        x = (x & ~1) | bit
    else:
        y = (y & ~1) | bit
    g.coordinates[i] = (x, y)


def get_bit(g, i, axis):
    return int(g.coordinates[i][axis]) & 1

def pack(path):
    data = Path(path).read_bytes()
    sha = hashlib.sha256(data).digest()
    stored, flags = data, 0
    packed = zlib.compress(data, 9)
    if len(packed) < len(data):
        stored, flags = packed, FLAG_ZLIB
    name = Path(path).name.encode()[:255]
    head = struct.pack(HEAD, MAGIC, flags, len(name), len(stored), sha)
    return head + name + stored, sha

def encode(src, font_path, out):
    font = load_font(font_path)
    blob, sha = pack(src)
    cap = capacity_bytes(font)
    if len(blob) > cap:
        sys.exit(f"error: {len(blob)} bytes needed (after compression + header), "
                 f"but this font only holds {cap}. Try a bigger font.")
    bits = ((b >> k) & 1 for b in blob for k in range(7, -1, -1))
    for (g, i, axis), bit in zip(slots(font), bits):
        set_bit(g, i, axis, bit)
    font.save(out)
    print(f"stored {len(blob)} of {cap} bytes in {out}")
    print("sha256 original :", sha.hex())


class BitReader:
    def __init__(self, font):
        self.it = slots(font)

    def read(self, n):
        out = bytearray()
        for _ in range(n):
            v = 0
            for _ in range(8):
                try:
                    g, i, axis = next(self.it)
                except StopIteration:
                    raise ValueError("the font is too small, the file got cut off")
                v = (v << 1) | get_bit(g, i, axis)
            out.append(v)
        return bytes(out)


def decode(font_path, outdir):
    font = load_font(font_path)
    r = BitReader(font)
    magic, flags, name_len, stored_len, sha = struct.unpack(HEAD, r.read(HEAD_SIZE))
    if magic != MAGIC:
        raise ValueError("this font doesn't hide anything of ours")
    name = r.read(name_len).decode(errors="replace")
    data = r.read(stored_len)
    if flags & FLAG_ZLIB:
        data = zlib.decompress(data)
    if hashlib.sha256(data).digest() != sha:
        raise ValueError("hash mismatch: the data is damaged")
    outdir = Path(outdir)
    outdir.mkdir(exist_ok=True)
    target = outdir / Path(name).name
    target.write_bytes(data)
    print(f"recovered {target} ({len(data)} bytes)")
    print("sha256 recovered:", hashlib.sha256(data).hexdigest())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capacity", help="how many bytes fit in this font")
    c.add_argument("font")
    e = sub.add_parser("encode", help="hide a file in a font")
    e.add_argument("file")
    e.add_argument("font")
    e.add_argument("-o", "--out", default="hidden.ttf")
    d = sub.add_parser("decode", help="get the file back out")
    d.add_argument("font")
    d.add_argument("-d", "--outdir", default="recovered")
    a = p.parse_args()
    try:
        if a.cmd == "capacity":
            print(capacity_bytes(load_font(a.font)), "bytes")
        elif a.cmd == "encode":
            encode(a.file, a.font, a.out)
        else:
            decode(a.font, a.outdir)
    except ValueError as err:
        sys.exit(f"error: {err}")

if __name__ == "__main__":
    main()
