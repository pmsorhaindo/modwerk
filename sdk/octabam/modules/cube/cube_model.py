#!/usr/bin/env python3
"""CUBE's reference model: the ColdFire control math, the morph builder, the
streaming scheduler, the record the DSP reads, and the DSP block itself,
integer for integer (cube_engine.asm). The C side (cube.c) is generated
from the same tables (cube_tables.inc, written by generate.py) and mirrors
the integer steps here; the DSP gate (verify.py --dsp) runs cube_engine.asm in
cube_host and compares it with Engine.block() sample for sample.

Parameters are the raw Part bytes:
  SRC    PTCH (FLEX's: 4..124, 64 = 0 st) X Y Z FM MIX
  SETUP  FINE OCT UNI TONE MORPH SYNC
  OSC B  BX BY BZ LINK LAW BPCH
"""
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SR = 44100
INC_C4 = 261.6255653005986 / SR * (1 << 24)
MININC = math.ceil(14 / SR * (1 << 24))          # below 14 Hz the oscillator mutes
MAXINC = 0x7fffff                                 # Nyquist: half a cycle per sample
CENT = [round(INC_C4 * 256 * 2 ** (r / 1200)) for r in range(1200)]
UNIC = [0] + [max(1, round(50 * (u / 96) ** 2)) for u in range(1, 97)]   # cents, UNI 1..96
FMLIN = [round(0x400000 * (f / 127) ** 2) for f in range(128)]
MIXG = [(m * 0x400000) // 64 if m <= 64 else 0x400000 + ((m - 64) * 0x3fffff) // 63 for m in range(128)]
MASK = (0xffffff, 0xfff000, 0xff0000)
COUNTS = dict(OCT=5, TONE=3, MORPH=8, SYNC=3, LINK=4, LAW=3)
DEFAULTS = dict(PTCH=64, X=0, Y=0, Z=0, FM=0, MIX=64, FINE=64, OCT=2, UNI=0, TONE=0, MORPH=7, SYNC=1,
                BX=0, BY=0, BZ=0, LINK=0, LAW=0, BPCH=64)
SRC, SETUP, OSCB = ("PTCH", "X", "Y", "Z", "FM", "MIX"), ("FINE", "OCT", "UNI", "TONE", "MORPH", "SYNC"), \
    ("BX", "BY", "BZ", "LINK", "LAW", "BPCH")
SIG0, SIG1 = 0xCB01, 0x1E1E


def inc_of(cents):
    o = cents // 1200
    r = cents - 1200 * o
    sh = o - 8
    v = CENT[r] << sh if sh >= 0 else CENT[r] >> -sh
    return min(v, MAXINC)


def clamp(v, n):
    return v if 0 <= v < n else 0


def controls(p):
    """dict of raw bytes -> what the record carries (cube.c cube_controls)."""
    oct_ = clamp(p["OCT"], 5)
    tone, morph, sync = clamp(p["TONE"], 3), clamp(p["MORPH"], 8), clamp(p["SYNC"], 3)
    link, law = clamp(p["LINK"], 4), clamp(p["LAW"], 3)
    cents_a = (p["PTCH"] - 64) * 100 + (p["FINE"] - 64) + (oct_ - 2) * 1200
    inc_a = inc_of(cents_a)
    u = p["UNI"]
    uoct = -1200 if 97 <= u <= 111 else 1200 if u >= 112 else 0
    udet = UNIC[u] if 1 <= u <= 96 else 0
    note = cents_a if link in (0, 1) else 0
    inc_b = inc_of(note + (p["BPCH"] - 64) * 100 + uoct + udet)
    mute_a, mute_b = inc_a < MININC, inc_b < MININC
    fm = p["FM"]
    d = FMLIN[fm] if law == 0 else min(0x7fffff, (inc_a * 2 * fm) // 127) if law == 1 else 0
    if mute_b:
        d = 0
    g_b = MIXG[p["MIX"]]
    g_a = 0x7fffff - g_b
    if mute_a:
        g_a = 0
    if mute_b:
        g_b = 0
    own = link in (1, 3)
    pos_a = (p["X"], p["Y"], p["Z"], morph)
    pos_b = (p["BX"], p["BY"], p["BZ"], morph) if own else None
    return dict(inc_a=inc_a, inc_b=inc_b, d=d, g_a=g_a, g_b=g_b, mask=MASK[tone], sync=sync, own=own,
                pos_a=pos_a, pos_b=pos_b, mute_a=mute_a, mute_b=mute_b)


# ---- the morph: integer, as cube.c builds it -------------------------------------

def axis(v, on):
    """(i0, i1, t8): the two frames and the weight of the second in 1/256."""
    if not on:
        i = (v * 7 + 63) // 127
        return i, i, 0
    a = v * 7
    i0 = a // 127
    return i0, min(i0 + 1, 7), (a % 127) * 256 // 127


def lerp(a, b, t8):
    return a + (((b - a) * t8) >> 8)


def morph_samples(cube, pos, start, n):
    """samples [start, start+n) of the cycle at pos = (x, y, z, morph bits)."""
    x, y, z, m = pos
    xi0, xi1, xt = axis(x, m & 1)
    yi0, yi1, yt = axis(y, m & 2)
    zi0, zi1, zt = axis(z, m & 4)
    out = []
    for s in range(start, start + n):
        def at_z(zi):
            f = cube[zi]
            r0 = lerp(f[yi0 * 8 + xi0][s], f[yi0 * 8 + xi1][s], xt) if xt else f[yi0 * 8 + xi0][s]
            if not yt:
                return r0
            r1 = lerp(f[yi1 * 8 + xi0][s], f[yi1 * 8 + xi1][s], xt) if xt else f[yi1 * 8 + xi0][s]
            return lerp(r0, r1, yt)
        v = at_z(zi0)
        if zt:
            v = lerp(v, at_z(zi1), zt)
        out.append(v)
    return out


# ---- the stream: one 16-sample chunk per frame, A before B ------------------------

class Stream:
    """Per track (cube.c CubeTrack): which cycle each DSP buffer holds and the
    chunk in flight. A finished stream commits (the DSP flips the buffer)."""

    def __init__(self):
        self.epoch = 0
        self.last = [None, None]          # pos the front buffer holds, A / B
        self.busy = None                  # (which, pos, chunk)

    def reset(self, epoch):
        self.epoch = epoch & 0xffff
        self.last = [None, None]
        self.busy = None

    def chunk(self, ctl):
        """-> (target 0/1/2, index, commit, pos) for this frame."""
        if self.busy is None:
            if ctl["pos_a"] != self.last[0]:
                self.busy = (0, ctl["pos_a"], 0)
            elif ctl["own"] and ctl["pos_b"] != self.last[1]:
                self.busy = (1, ctl["pos_b"], 0)
        if self.busy is None:
            return 0, 0, 0, None
        which, pos, k = self.busy
        commit = k == 15
        if commit:
            self.last[which] = pos
            self.busy = None
        else:
            self.busy = (which, pos, k + 1)
        return which + 1, k, commit, pos


def record(ctl, stream, cube, trig):
    """The 34 DSP words (16-bit halves, as the transport delivers them)."""
    target, k, commit, pos = stream.chunk(ctl)
    flags = (1 if trig else 0) | (2 if ctl["own"] else 0) | (ctl["sync"] << 2)
    w = [SIG0, flags, SIG1, stream.epoch]
    for v in (ctl["inc_a"], ctl["inc_b"], ctl["d"], ctl["g_a"], ctl["g_b"], ctl["mask"]):
        w += [(v >> 8) & 0xffff, v & 0xff]
    w += [target | (4 if commit else 0) | (k << 4), 0]
    samples = morph_samples(cube, pos, k * 16, 16) if target else [0] * 16
    w += [s & 0xffff for s in samples]
    assert len(w) == 34
    return w


# ---- the DSP block, integer for integer -------------------------------------------

def s24(v):
    v &= 0xffffff
    return v - (1 << 24) if v & 0x800000 else v


VB, STATE = 0x2900, 0x3900


class Engine:
    """One core's CUBE state for one voice (cube_engine.asm). Buffers hold
    24-bit words (int16 << 8). Phases are the DSP's: logical + 2^23, so the
    reset value is $800000 and the read index is (p >> 16) ^ 0x80."""

    def __init__(self):
        self.epoch = None             # what X:STATE+0 holds: None = garbage
        self.buf = [[[0] * 256 for _ in range(2)] for _ in range(2)]   # [A/B][0/1]
        self.front = [0, 0]
        self.pa = self.pb = 0x800000
        self.last_idx = -128

    def init(self, epoch):
        self.epoch = epoch
        self.buf = [[[0] * 256 for _ in range(2)] for _ in range(2)]
        self.front = [0, 0]
        self.pa = self.pb = 0x800000
        self.last_idx = -128

    @staticmethod
    def word(w, i):
        return ((w[i] & 0xffff) << 8) | (w[i + 1] & 0xff)

    def block(self, w, trig_offset=None, frames=16):
        """w: the 34 record words; trig_offset: x:$20c when the record says trig.
        Returns 2*frames output words (L, R)."""
        assert w[0] & 0xffff == SIG0 and w[2] & 0xffff == SIG1
        flags, epoch = w[1] & 0xffff, w[3] & 0xffff
        if epoch != self.epoch:
            self.init(epoch)
        inc_a, inc_b, d, g_a, g_b, mask = (self.word(w, 4 + 2 * i) for i in range(6))
        d, g_a, g_b = s24(d), s24(g_a), s24(g_b)
        ctl = w[16] & 0xffff
        target = ctl & 3
        if target in (1, 2):
            which = target - 1
            back = self.front[which] ^ 1
            k = (ctl >> 4) & 15
            for i in range(16):
                self.buf[which][back][k * 16 + i] = s24((w[18 + i] & 0xffff) << 8)
            if ctl & 4:
                self.front[which] = back
        own = bool(flags & 2)
        sync = (flags >> 2) & 3
        bufa = self.buf[0][self.front[0]]
        bufb = self.buf[1][self.front[1]] if own else bufa
        out = []
        t = trig_offset if (flags & 1) and sync and trig_offset is not None and 0 <= trig_offset < frames else None
        segs = [(0, frames)] if t is None else [(0, t), (t, frames - t)]
        for si, (start, n) in enumerate(segs):
            if si == 1:
                self.pa = self.pb = 0x800000
            if n:
                out += self.segment(n, bufa, bufb, inc_a, inc_b, d, g_a, g_b, mask, sync == 2)
        return out

    @staticmethod
    def osc(p, buf):
        """(sample, signed index): mpy by 2^-16 puts the signed top byte in a1 and
        the low 16 bits << 8 in a0 (the unsigned frac); the buffer pointer sits
        at the cycle's centre, so the read is (index + 128) mod 256."""
        i = ((p >> 16) & 0xff) - (256 if p & 0x800000 else 0)
        j = (i + 128) & 255
        u = (p & 0xffff) << 8
        s0, s1 = buf[j], buf[(j + 1) & 255]
        h = (s1 - s0) >> 1
        acc = (s0 << 24) + 2 * h * u
        return acc >> 24, i

    def segment(self, n, bufa, bufb, inc_a, inc_b, d, g_a, g_b, mask, hard):
        yb, idx = [], []
        for _ in range(n):
            self.pb = (self.pb + inc_b) & 0xffffff
            y, i = self.osc(self.pb, bufb)
            yb.append(y)
            idx.append(i)
        out = []
        prev = self.last_idx
        for k in range(n):
            acc = (inc_a << 24) + 2 * d * yb[k]
            inc = (acc >> 24) & 0xffffff
            self.pa = (self.pa + inc) & 0xffffff
            if hard:
                if idx[k] < prev:
                    self.pa = 0x800000
                prev = idx[k]
            ya, _ = self.osc(self.pa, bufa)
            z = (2 * g_b * yb[k] + 2 * g_a * ya) >> 24
            o = (z & 0xffffff) & mask
            out += [o, o]
        if hard and n:
            self.last_idx = idx[-1]
        return out
