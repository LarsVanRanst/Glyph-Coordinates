import argparse
import glob
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
CHUNK_MAGIC = b"WFCK"
CHUNK = ">4sHHI32s" 
CHUNK_SIZE = struct.calcsize(CHUNK)

def load_font(path):
    font = TTFont(path)
    if "glyf" not in font:
        sys.exit("error: this needs a TrueType font (with a 'glyf' table), not CFF/OTF.")
    if "fvar" in font:
        sys.exit("error: variable fonts are not supported, pick a static font.")
    return font


def slots(font):
    """Yield (glyph, point_index, axis) in a fixed order. Axis 0 = x, 1 = y.
    Composite and empty glyphs have no coordinates of their own and are skipped.
    The number of slots does not depend on the coordinate values, so the
    encoder and the decoder always walk the same path."""
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

def write_bits(font, data):
    bits = ((b >> k) & 1 for b in data for k in range(7, -1, -1))
    for (g, i, axis), bit in zip(slots(font), bits):
        set_bit(g, i, axis, bit)


def chunk_names(out, n):
    out = Path(out)
    if n == 1:
        return [out]
    return [out.with_name(f"{out.stem}_{i + 1:03d}of{n:03d}{out.suffix}") for i in range(n)]


def encode(src, font_path, out):
    blob, sha = pack(src)
    room = capacity_bytes(load_font(font_path)) - CHUNK_SIZE
    if room <= 0:
        sys.exit("error: this font is too small to hold anything.")
    pieces = [blob[i:i + room] for i in range(0, len(blob), room)]
    n = len(pieces)
    group = hashlib.sha256(blob).digest()
    for idx, (piece, name) in enumerate(zip(pieces, chunk_names(out, n))):
        font = load_font(font_path)
        write_bits(font, struct.pack(CHUNK, CHUNK_MAGIC, idx, n, len(piece), group) + piece)
        font.save(name)
        print(f"chunk {idx + 1}/{n}: {name}")
    print(f"stored {len(blob)} bytes in {n} font(s) ({room} bytes per font)")
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


def read_chunk(font_path):
    r = BitReader(load_font(font_path))
    magic, idx, total, plen, group = struct.unpack(CHUNK, r.read(CHUNK_SIZE))
    if magic != CHUNK_MAGIC:
        raise ValueError(f"{font_path} doesn't hide anything of ours")
    return idx, total, group, r.read(plen)


def unpack(blob):
    if len(blob) < HEAD_SIZE:
        raise ValueError("the file got cut off")
    magic, flags, name_len, stored_len, sha = struct.unpack(HEAD, blob[:HEAD_SIZE])
    if magic != MAGIC:
        raise ValueError("this isn't one of ours!")
    name = blob[HEAD_SIZE:HEAD_SIZE + name_len].decode(errors="replace")
    data = blob[HEAD_SIZE + name_len:HEAD_SIZE + name_len + stored_len]
    if len(data) != stored_len:
        raise ValueError("the file got cut off")
    if flags & FLAG_ZLIB:
        data = zlib.decompress(data)
    if hashlib.sha256(data).digest() != sha:
        raise ValueError("hash mismatch: the data is damaged")
    return name, data


def decode(font_paths, outdir):
    if isinstance(font_paths, (str, Path)):
        font_paths = [font_paths]
    if not font_paths:
        raise ValueError("no fonts given")
    chunks, total, group = {}, None, None
    for p in font_paths:
        idx, t, g, piece = read_chunk(p)
        if total is None:
            total, group = t, g
        elif (t, g) != (total, group):
            raise ValueError(f"{p} belongs to a different file")
        chunks[idx] = piece
    missing = [str(i + 1) for i in range(total) if i not in chunks]
    if missing:
        raise ValueError(f"missing chunk(s) {', '.join(missing)} of {total}")
    blob = b"".join(chunks[i] for i in range(total))
    if hashlib.sha256(blob).digest() != group:
        raise ValueError("the chunks don't fit together")
    name, data = unpack(blob)
    outdir = Path(outdir)
    outdir.mkdir(exist_ok=True)
    target = outdir / Path(name).name
    target.write_bytes(data)
    print(f"recovered {target} ({len(data)} bytes) from {total} font(s)")
    print("sha256 recovered:", hashlib.sha256(data).hexdigest())


def expand(args):
    """Turn folders and wildcards (PowerShell doesn't expand them) into a list of fonts."""
    out = []
    for a in args:
        if Path(a).is_dir():
            out += sorted(str(p) for p in Path(a).glob("*.ttf"))
        elif any(c in a for c in "*?["):
            out += sorted(glob.glob(a))
        else:
            out.append(a)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capacity", help="how many bytes fit in this font")
    c.add_argument("font")
    e = sub.add_parser("encode", help="hide a file in a font (or in several fonts if it is big)")
    e.add_argument("file")
    e.add_argument("font")
    e.add_argument("-o", "--out", default="hidden.ttf")
    d = sub.add_parser("decode", help="get the file back out of one or more fonts")
    d.add_argument("fonts", nargs="+", help="font files, a folder, or a pattern like \"hidden_*.ttf\"")
    d.add_argument("-d", "--outdir", default="recovered")
    a = p.parse_args()
    try:
        if a.cmd == "capacity":
            print(capacity_bytes(load_font(a.font)), "bytes")
        elif a.cmd == "encode":
            encode(a.file, a.font, a.out)
        else:
            decode(expand(a.fonts), a.outdir)
    except ValueError as err:
        sys.exit(f"error: {err}")


if __name__ == "__main__":
    main()
