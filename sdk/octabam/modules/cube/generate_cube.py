#!/usr/bin/env python3
"""CUBE's built-in wavetable cube: one original 8 x 8 x 8 set, generated here.

    python3 modules/cube/generate_cube.py [--wav DIR] [--check]

Layout (the published 3D-wavetable file layout, not anyone's content): eight
files, Z = 0..7; each 64 single cycles of 256 samples, 16-bit, frame
Y * 8 + X. Every cycle is synthesised from first principles below; nothing is
sampled, imported or copied from a factory bank. Each cycle has its mean
removed (no reset thump) and is peak-normalised to 0.95 full scale.

Outputs:
  out/cube/cube.bin     262,144 bytes, big-endian int16 in Z, Y, X, sample
                        order: the ColdFire reads it directly (cube.s
                        .incbin's it into the DRAM runtime)
  DIR/1.wav .. 8.wav    the same cycles as mono 16-bit little-endian WAVs,
                        one per Z, for listening and for any wavetable editor
                        that reads 64 x 256-sample files
--check exits 1 if out/cube/cube.bin differs from a fresh generation.

The banks (all original, all band-unlimited where that is the point):
  Z0 ADDITIVE   X: number of partials 1..8 (as 1,2,3,5,8,12,20,32), Y: spectral
                tilt from 1/n^2 (soft) to 1/sqrt(n) (bright), odd+even
  Z1 SHAPES     X: sine -> triangle -> saw -> square -> pulse morph steps,
                Y: pulse width / skew 50%..6%
  Z2 SYNC SAW   X: hard-sync ratio 1..4.5 (a slave saw reset by the cycle),
                Y: a cosine window depth over the cycle
  Z3 PHASE DIST X: phase-distortion knee, Y: resonance-like harmonic ratio
  Z4 FOLD       X: wavefolder gain 1..8, Y: DC bias before the fold
  Z5 STEPS      X: number of stair steps 64..2, Y: duty of a stepped pulse
  Z6 FM PAIRS   X: modulation index 0..7, Y: modulator ratio 1..8
  Z7 DRIFT      seeded value noise (an LFSR of our own) smoothed per Y,
                evolving along X: a sequence, not a recording
"""
import math
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "out/cube/cube.bin"
N = 256
TAU = 2 * math.pi


def norm(cyc):
    m = sum(cyc) / N
    cyc = [v - m for v in cyc]
    peak = max(abs(v) for v in cyc) or 1.0
    return [round(32767 * 0.95 * v / peak) for v in cyc]


def additive(x, y):
    counts = (1, 2, 3, 5, 8, 12, 20, 32)
    tilt = 2.0 - 1.5 * y / 7          # exponent 2.0 .. 0.5
    k = counts[x]
    return [sum(math.sin(TAU * n * i / N) / n ** tilt for n in range(1, k + 1)) for i in range(N)]


def shapes(x, y):
    width = 0.5 - 0.44 * y / 7        # 50% .. 6%
    out = []
    for i in range(N):
        t = i / N
        sine = math.sin(TAU * t)
        tri = 1 - 4 * abs(((t + 0.25) % 1) - 0.5)
        saw = 2 * ((t + 0.5) % 1) - 1
        sq = 1.0 if t < width else -1.0
        steps = (sine, tri, saw, sq)
        a = x / 7 * 3                 # 0..3 across the four shapes
        j = min(int(a), 2)
        f = a - j
        out.append(steps[j] * (1 - f) + steps[j + 1] * f)
    return out


def sync_saw(x, y):
    ratio = 1 + 3.5 * x / 7
    depth = y / 7
    out = []
    for i in range(N):
        t = i / N
        slave = 2 * ((t * ratio) % 1) - 1
        win = 1 - depth * 0.5 * (1 - math.cos(TAU * t))
        out.append(slave * win)
    return out


def phase_dist(x, y):
    knee = 0.5 - 0.47 * x / 7         # 0.5 (sine) .. 0.03
    ratio = 1 + y                     # 1..8
    out = []
    for i in range(N):
        t = i / N
        p = 0.5 * t / knee if t < knee else 0.5 + 0.5 * (t - knee) / (1 - knee)
        out.append(math.cos(TAU * p * ratio) * (1 - t) if y else -math.cos(TAU * p))
    return out


def fold(x, y):
    gain = 1 + x
    bias = 0.6 * y / 7
    out = []
    for i in range(N):
        v = gain * math.sin(TAU * i / N) + bias
        # a triangle fold into -1..1
        v = abs(((v + 1) % 4) - 2) - 1
        out.append(v)
    return out


def stairs(x, y):
    levels = (64, 32, 16, 12, 8, 6, 4, 2)[x]
    duty = 0.5 - 0.4 * y / 7
    out = []
    for i in range(N):
        t = i / N
        s = math.sin(TAU * t) if y < 4 else (1.0 if t < duty else -1.0) * (0.5 + 0.5 * math.sin(TAU * t))
        out.append(round(s * levels / 2) / (levels / 2))
    return out


def fm_pair(x, y):
    index = float(x)
    ratio = 1 + y
    return [math.sin(TAU * i / N + index * math.sin(TAU * ratio * i / N)) for i in range(N)]


def drift(x, y):
    # a 16-bit Galois LFSR of our own taps, seeded per X: 32 control points
    state = 0xACE1 ^ (x * 0x1F35 + 1)
    points = []
    for _ in range(32):
        for _ in range(16):
            lsb = state & 1
            state >>= 1
            if lsb:
                state ^= 0xB400
        points.append(state / 32767.5 - 1)
    smooth = 1 + y                    # neighbours averaged
    pts = [sum(points[(j + k) % 32] for k in range(smooth)) / smooth for j in range(32)]
    out = []
    for i in range(N):
        a = i * 32 / N
        j = int(a)
        f = a - j
        f = f * f * (3 - 2 * f)
        out.append(pts[j] * (1 - f) + pts[(j + 1) % 32] * f)
    return out


BANKS = (additive, shapes, sync_saw, phase_dist, fold, stairs, fm_pair, drift)


def cube():
    """[z][y*8+x] -> 256 int16."""
    return [[norm(BANKS[z](f % 8, f // 8)) for f in range(64)] for z in range(8)]


def to_bin(c):
    return b"".join(struct.pack(">256h", *c[z][f]) for z in range(8) for f in range(64))


def wav(path, cycles):
    pcm = b"".join(struct.pack("<256h", *cyc) for cyc in cycles)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 44100, 88200, 2, 16) \
        + b"data" + struct.pack("<I", len(pcm))
    path.write_bytes(hdr + pcm)


def main():
    c = cube()
    blob = to_bin(c)
    assert len(blob) == 262144
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_bytes() != blob:
            raise SystemExit(f"stale: {OUT} (run modules/cube/generate_cube.py)")
        print("cube: out/cube/cube.bin matches the generator")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(blob)
    if "--wav" in sys.argv:
        d = pathlib.Path(sys.argv[sys.argv.index("--wav") + 1])
        d.mkdir(parents=True, exist_ok=True)
        for z in range(8):
            wav(d / f"{z + 1}.wav", c[z])
    print(f"cube: {OUT} ({len(blob):,} B)" + (" + 8 WAVs" if "--wav" in sys.argv else ""))


if __name__ == "__main__":
    main()
