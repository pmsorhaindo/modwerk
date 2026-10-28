#!/usr/bin/env python3
"""CUBE's gate for the static-stock build (tracks 1-4, every stock effect kept), under the ColdFire port.

    python3 modules/cube/verify_static.py STEP IMAGE ELF [STOCK]

IMAGE is the built MAIN OS (out/mainos_bus.bin), ELF its platform runtime
(out/platform/runtime/runtime.elf), STOCK the user's own 1.40C MAIN OS section
(out/raw/section_3_MAIN_OS.bin), booted beside it as the reference.
Steps (comma-separated, or `all`):
  fx     every stock effect: the FX1 and FX2 choosers of T1, T4, T5 and T8 draw
         row for row what stock draws; each row selected on FX1 (T1, T5) and
         FX2 (T2, T6) of THRU tracks on both cores stores stock's effect id
  fxaudio  the same rows stepped on THRU tracks of both cores, knobs off their
         defaults: MAIN, after the effects, against stock and a stock control
         2.3 s later (rows stock repeats exactly within 2 LSB, rows that depend
         on timing within 1 dB), and every row changes MAIN from NONE
  dspmem the program memory both DSP cores booted: core 0 stock's word for
         word; core 1 stock's but the seam's two words, with CUBE above P:0x1d9f
  fxid   each FX2 row (SPRING REV included) and FX1 row selected on T3, T4,
         T7 and T8 stores the effect id stock stores
  ui     CUBE on T1: six machine rows on T1-T4; SRC PTCH FM MIX / X Y Z,
         SRC again OSC B BPCH LAW LINK / BX BY BZ, a double press SETUP
         FINE OCT UNI / TONE MORPH SYNC (never in the single-press cycle); the
         UNI push cycles A -> B -> BOTH and each target detunes its
         oscillator(s), in the control record and in the audio; the strip's
         letter; LFO PMTR names; T5-T8: stock's five rows, no CUBE, no popup,
         and a CUBE signature there is put back to FLEX
  four   CUBE on T1-T4 together: every stem sounds, the sequencer runs;
         THRU on T5-T8 beside them
  save   SAVE, change, RELOAD: T1's and T3's CUBE bytes come back
  clock  diag/repro_clock.py-style: MIDI clock and notes keep going with CUBE
Screens go to $CUBE_SHOTS (default out/cube/shots), WAVs beside them. Exit 0
when every check passes."""
import hashlib
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import port as P  # noqa: E402

SHOTS = pathlib.Path(os.environ.get("CUBE_SHOTS", ROOT / "out/cube/shots"))
PB, SU, FX, NB = 0x2A, 0x1DA, 6, 18
SETUP_WINDOW = 0x400BB7C8
TICK_ISR = 0x400A1E0C
ROW = dict(STATIC=0, FLEX=1, THRU=2, NEIGHBOR=3, PICKUP=4, CUBE=5)
# page slot order (cube.c SRC_SEM / OSCB_SEM)
SRC_PAGE = ("PTCH", "FM", "MIX", "X", "Y", "Z")
OSCB_PAGE = ("BPCH", "LAW", "LINK", "BX", "BY", "BZ")
SETUP_PAGE = ("FINE", "OCT", "UNI", "TONE", "MORPH", "SYNC")
DEFAULTS = dict(PTCH=64, X=0, Y=0, Z=0, FM=0, MIX=64, FINE=64, OCT=2, UNI=0, TONE=0, MORPH=7, SYNC=1,
                BX=0, BY=0, BZ=0, LINK=0, LAW=0, BPCH=64)
FLEX_PB, FLEX_SU = bytes((64, 0, 0, 127, 0, 79)), bytes((1, 0, 0, 0, 1, 64))
UTGT = {0: "B", 1: "BOTH", 2: "A"}
failures, passes = [], []


def check(name, ok, detail=""):
    (passes if ok else failures).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""), flush=True)


def at(t, name):
    """The Part offset of CUBE byte `name` on track t (cube.c's header)."""
    if name in SRC_PAGE:
        return PB + 30 * t + FX + SRC_PAGE.index(name)
    if name in SETUP_PAGE:
        return SU + 30 * t + FX + SETUP_PAGE.index(name)
    k = ("BX", "BY", "BZ", "LINK", "LAW", "BPCH").index(name)
    return PB + 30 * t + NB + 3 + k if k < 3 else SU + 30 * t + NB + k - 3


def utgt_at(t):
    return SU + 30 * t + NB + 3


def cube_bytes(raw, t):
    return {n: raw[at(t, n)] for n in DEFAULTS}


def signed(raw, t):
    return raw[PB + 30 * t + NB:PB + 30 * t + NB + 3] == b"CU\x01"


def boot(image, elf=None, **kw):
    work = pathlib.Path(tempfile.mkdtemp(prefix="cubes_")) / "w"
    p = P.Port(image, work, elf=elf, extra=["--audio-in", "tones"] + list(kw.pop("extra", ())), **kw)
    p.run(1500)
    p.press("NO")
    p.run(300)
    return p


def dedupe(seq):
    return [s for i, s in enumerate(seq) if i == 0 or s != seq[i - 1]]


def scr(p):
    return hashlib.sha1(repr(p.screen()).encode()).hexdigest()


def machine(p, track, row):
    """SRC SETUP on `track`, row `row` of its machine list, YES, closed."""
    p.press(track)
    p.press("FUNC", "SRC")
    p.run(300)
    for _ in range(7):
        p.press("UP")
    for _ in range(row):
        p.press("DOWN")
    p.press("YES")
    p.run(400)
    p.press("NO")
    p.run(300)


def thru(p, track):
    """THRU on `track` with INAB on input A (stock's default INAB 0 is no input)."""
    machine(p, track, ROW["THRU"])
    t = int(track[1:]) - 1
    p.cmd(f"poke {p.part() + PB + 30 * t + 12:#x} 01")


def put24(r):
    """cube.c put24's inverse: the record long -> the 24-bit value."""
    return ((r >> 16) & 0xFFFF) << 8 | (r & 0xFF)


def window(p):
    w = int.from_bytes(p.peek(0x400BCD14, 4), "big")
    return w if int.from_bytes(p.peek(w + 8, 4), "big") else 0


def where(p):
    w = window(p)
    if w:
        return "SETUP" if w == SETUP_WINDOW else f"window {w:08x}"
    page = int.from_bytes(p.peek(0x460D1684, 4), "big")
    if page != 0:
        return f"page {page}"
    return "OSCB" if p.peek(p.sym["cube_view"], 1)[0] == 2 else "SRC"


def press(p):
    p.run(700)
    p.press("SRC")
    p.run(300)


def tap(p):
    p.run(700)
    for _ in range(2):
        p.key("SRC", True, 40)
        p.key("SRC", False, 40)
    p.run(300)


def turn(p, enc, t, name, target, tries=8):
    for _ in range(tries):
        v = p.part_bytes()[at(t, name)]
        if v == target:
            return True
        p.enc(enc, max(-120, min(120, (target - v) * (4 if name in ("OCT", "TONE", "MORPH", "SYNC", "LINK", "LAW") else 1))))
    return p.part_bytes()[at(t, name)] == target


def trigs(p, tracks, steps):
    p.press("REC")
    for t in tracks:
        p.press(t)
        for s in steps:
            p.press(f"TRIG{s}")
    p.press("REC")


def stems(p, ms):
    p.cmd("audio start tracks")
    p.press("PLAY")
    p.run(ms)
    p.press("STOP")
    p.run(300)
    fr = p.audio(24)
    p.cmd("audio stop")
    return fr


def wav(path, x, ch=1):
    import struct
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(struct.pack("<h", v) for v in x)
    path.write_bytes(b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
                     struct.pack("<IHHIIHH", 16, 1, ch, 44100, 44100 * 2 * ch, 2 * ch, 16) + b"data" +
                     struct.pack("<I", len(pcm)) + pcm)


def pitch(x):
    loud = [i for i, v in enumerate(x) if abs(v) > 300]
    if not loud:
        return 0.0
    seg = x[loud[0] + 200:loud[0] + 200 + 44100]
    return sum(1 for a, b in zip(seg, seg[1:]) if a < 0 <= b) / (len(seg) / 44100) if seg else 0.0


def rms(x):
    return (sum(v * v for v in x) / max(1, len(x))) ** 0.5


# ---- effects ---------------------------------------------------------------------------

def chooser(p, slot):
    """Screens of `slot`'s effect chooser (FX1/FX2) from its top row down, until it stops moving."""
    p.press(slot)
    p.run(300)
    p.press("FUNC", slot)
    p.run(400)
    for _ in range(20):
        p.press("UP")
    shots, same = [scr(p)], 0
    while same < 2 and len(shots) < 40:
        p.press("DOWN")
        s = scr(p)
        same = same + 1 if s == shots[-1] else 0
        shots.append(s)
    p.press("NO")
    p.run(300)
    while len(shots) > 1 and shots[-1] == shots[-2]:
        shots.pop()
    return shots


def pick_fx(p, track, slot, row):
    """Row `row` of `slot`'s chooser on `track`; the Part bytes that changed {offset: value}."""
    p.press(track)
    p.press(slot)
    p.run(300)
    before = p.part_bytes()
    p.press("FUNC", slot)
    p.run(400)
    for _ in range(20):
        p.press("UP")
    for _ in range(row):
        p.press("DOWN")
    p.press("YES")
    p.run(400)
    p.press("NO")
    p.run(300)
    after = p.part_bytes()
    return {i: after[i] for i in range(len(after)) if after[i] != before[i]}


def fx_run(image, elf, tag, out):
    """Everything `fx` measures on one image, as JSON (both images run the same walk)."""
    res = dict(choosers={}, picks={}, stems={})
    p = boot(image, elf)
    try:
        for t in ("T1", "T4", "T5", "T8"):
            for slot in ("FX1", "FX2"):
                p.press(t)
                res["choosers"][f"{t} {slot}"] = chooser(p, slot)
        p.press("T1")
        p.press("FX2")
        p.press("FUNC", "FX2")
        p.run(400)
        p.shot(SHOTS / f"fx2_chooser_{tag}.png")
        for _ in range(8):
            p.press("DOWN")
        p.shot(SHOTS / f"fx2_chooser_down_{tag}.png")
        p.press("NO")
        p.run(300)
        for t in ("T1", "T2", "T5", "T6"):
            thru(p, t)
        trigs(p, ("T1", "T2", "T5", "T6"), (1, 9))
        rows = {s: len(res["choosers"][f"T1 {s}"]) for s in ("FX1", "FX2")}
        for k in range(1, max(rows.values())):
            picked = {}
            if k < rows["FX1"]:
                picked["T1 FX1"] = pick_fx(p, "T1", "FX1", k)
                picked["T5 FX1"] = pick_fx(p, "T5", "FX1", k)
            if k < rows["FX2"]:
                picked["T2 FX2"] = pick_fx(p, "T2", "FX2", k)
                picked["T6 FX2"] = pick_fx(p, "T6", "FX2", k)
            res["picks"][k] = {n: {str(o): v for o, v in d.items()} for n, d in picked.items()}
            fr = stems(p, 1500)
            res["stems"][k] = {t: [f[8 + 2 * i] for f in fr][:44100] for i, t in enumerate(
                ("T1", "T2", "T3", "T4", "T5", "T6")) if t in ("T1", "T2", "T5", "T6")}
            print(f"    {tag} row {k}: picks {res['picks'][k]}", flush=True)
    finally:
        p.quit()
    out.write_text(json.dumps(res))


def step_fx(image, elf, stock):
    print("== fx: every stock effect, both choosers, both cores, against stock 1.40C ==", flush=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="cubefx_"))
    import multiprocessing as mp
    jobs = [mp.Process(target=fx_run, args=(image, elf, "cube", work / "cube.json")),
            mp.Process(target=fx_run, args=(stock, None, "stock", work / "stock.json"))]
    [j.start() for j in jobs]
    [j.join() for j in jobs]
    c, s = (json.loads((work / f"{n}.json").read_text()) for n in ("cube", "stock"))
    for key in s["choosers"]:
        check(f"{key} chooser draws stock's {len(s['choosers'][key])} rows, row for row",
              c["choosers"][key] == s["choosers"][key],
              f"cube {len(c['choosers'][key])} rows, stock {len(s['choosers'][key])}")
    n1, n2 = len(s["choosers"]["T1 FX1"]), len(s["choosers"]["T1 FX2"])
    check(f"stock's choosers: FX1 {n1} rows, FX2 {n2} rows (NONE + the effects)", n1 > 1 and n2 > 1)
    ids = sorted({v for k in s["picks"] for d in s["picks"][k].values() for v in d.values()})
    print(f"    effect ids stock stores across both choosers: {[hex(i) for i in ids]}")
    check("0x15 (SPRING REV) is among them", 0x15 in ids)
    for k in s["picks"]:
        check(f"row {k}: every pick stores stock's bytes ({s['picks'][k]})", c["picks"].get(k) == s["picks"][k],
              f"cube {c['picks'].get(k)}")
        # (the per-track stems are taken before the FX; fxaudio compares MAIN, after them)


def onset(x, thr=200):
    return next((i for i, v in enumerate(x) if abs(v) > thr), None)


def fxaudio_run(image, elf, tag, out):
    """MAIN after each effect row: THRU on T1, T2 (core 1) and T5, T6 (core 0), FX1 row k on T1 and T5,
    FX2 row k on T2 and T6, stepped one row down the choosers from NONE, each effect's six knobs then
    turned off their defaults by the same amounts on both images."""
    res = {}
    p = boot(image, elf)
    try:
        p.run(int(os.environ.get("CUBE_FXA_SHIFT", "0")))   # a control run: the same walk, later
        for t in ("T1", "T2", "T5", "T6"):
            thru(p, t)
        trigs(p, ("T1", "T2", "T5", "T6"), (1, 9))
        rows = {}
        for t, slot in (("T1", "FX1"), ("T5", "FX1"), ("T2", "FX2"), ("T6", "FX2")):
            p.press(t)
            rows[slot] = len(chooser(p, slot))
            pick_fx(p, t, slot, 0)

        def step(t, slot):
            p.press(t)
            p.press(slot)
            p.run(200)
            p.press("FUNC", slot)
            p.run(400)
            p.press("DOWN")
            p.press("YES")
            p.run(400)
            p.press("NO")
            p.run(200)

        for k in range(0, max(rows.values())):
            if k:
                for t, slot in (("T1", "FX1"), ("T5", "FX1"), ("T2", "FX2"), ("T6", "FX2")):
                    if k < rows[slot]:
                        step(t, slot)
                        # off their defaults, where several effects are transparent on this input
                        for e, d in zip("ABCDEF", (40, -40, 50, -30, 35, 45)):
                            p.enc(e, d)
                        p.run(200)
            ids = {t: p.part_bytes()[i] for t, i in (("T1", 0), ("T5", 4), ("T2", 9), ("T6", 13))}
            fr = stems(p, 1500)
            raw = p.part_bytes()
            knobs = {t: list(raw[o:o + 6]) for t, o in (("T1", 294), ("T5", 390), ("T2", 324), ("T6", 420))}
            res[k] = dict(ids=ids, knobs=knobs, L=[f[2] for f in fr], R=[f[3] for f in fr])
            print(f"    {tag} row {k}: ids {ids} knobs {knobs}", flush=True)
    finally:
        p.quit()
    out.write_text(json.dumps(res))


def steady(a, b, n=20000, span=3000, start=20000):
    """`a` against `b` past the attack, at the lag (|lag| <= span) that matches best:
    (lag, differing samples, largest |difference|). The two images boot on different timings, so a
    trig lands at another phase of the input tones; the comparison is of the effects, not of that."""
    sb, best = b[start:start + n], None
    if len(sb) < n:
        return None
    for lag in range(-span, span + 1):
        sa = a[start + lag:start + lag + n]
        if len(sa) == n:
            nd = sum(1 for x, y in zip(sa[::16], sb[::16]) if x != y)
            if best is None or nd < best[1]:
                best = (lag, nd)
    sa = a[start + best[0]:start + best[0] + n]
    return best[0], sum(1 for x, y in zip(sa, sb) if x != y), max(abs(x - y) for x, y in zip(sa, sb))


def _fxaudio_one(name, image, elf, shift, work):
    os.environ["CUBE_FXA_SHIFT"] = str(shift)
    fxaudio_run(image, elf, name, pathlib.Path(work) / f"{name}.json")


def step_fxaudio(image, elf, stock):
    """Three runs of the same walk: this image, stock, and stock again 2.3 s later (the control). A row
    stock reproduces within 2 LSB of itself must come out within 2 LSB here; a row that depends on when
    it started (LFO phase, a reverb's history) is judged by its level, within 1 dB."""
    import math
    print("== fxaudio: MAIN after every effect row, both cores, against stock 1.40C and a stock control ==", flush=True)
    work = pathlib.Path(os.environ.get("CUBE_FXA_DIR") or tempfile.mkdtemp(prefix="cubefxa_"))
    runs = (("cube", image, elf, 0), ("stock", stock, None, 0), ("stock_shift", stock, None, 2345))
    if not all((work / f"{n}.json").exists() for n, *_ in runs):
        import multiprocessing as mp
        jobs = [mp.Process(target=_fxaudio_one, args=(*r, str(work))) for r in runs]
        [j.start() for j in jobs]
        [j.join() for j in jobs]
    else:
        print(f"    (captures from {work})")
    c, s, x = (json.loads((work / f"{n}.json").read_text()) for n, *_ in runs)
    db = lambda v: 20 * math.log10(max(v, 1e-9))
    for k in sorted(s, key=int):
        check(f"row {k}: effect ids {s[k]['ids']} and knob bytes as stock's (and the control's)",
              c[k]["ids"] == s[k]["ids"] == x[k]["ids"] and c[k]["knobs"] == s[k]["knobs"] == x[k]["knobs"],
              f"cube {c[k]['ids']} {c[k]['knobs']}")
        moved = []
        for ch in "LR":
            r = rms(s[k][ch][20000:60000])
            if r < 100:
                print(f"    row {k} MAIN {ch}: silent on stock too (rms {r:.0f}), not compared")
                continue
            ctl, got = steady(x[k][ch], s[k][ch]), steady(c[k][ch], s[k][ch])
            if ctl[2] <= 2:
                check(f"row {k} MAIN {ch}: stock repeats itself within {ctl[2]} LSB; this image within {got[2]}",
                      got[2] <= 2, f"{got}")
            else:
                dc, dx = db(rms(c[k][ch][20000:60000])) - db(r), db(rms(x[k][ch][20000:60000])) - db(r)
                check(f"row {k} MAIN {ch}: timing-dependent (stock vs itself up to {ctl[2]} LSB); level "
                      f"{dc:+.2f} dB from stock's (the control {dx:+.2f} dB)", abs(dc) <= 1.0, f"{got}")
            if k != "0":
                d = steady(s[k][ch], s["0"][ch])
                moved.append(d is not None and d[2] > 10)
        if k != "0":
            check(f"row {k}: on stock the effect changes MAIN from all-NONE (the path is after the FX)", any(moved))
        if k in ("11", "12", "13", "14"):
            wav(SHOTS / "audio" / f"fx_main_row{k}.wav", [v for pair in zip(c[k]["L"], c[k]["R"]) for v in pair], ch=2)


def step_dspmem(image, elf, stock):
    print("== dspmem: the program memory both DSP cores booted, against stock 1.40C ==", flush=True)
    mem = {}
    for tag, img, e in (("cube", image, elf), ("stock", stock, None)):
        p = boot(img, e)
        try:
            p.run(1500)
            mem[tag] = {core: p.dsp(core, "P", 0, 0x2000) for core in (0, 1)}
        finally:
            p.quit()
    c, s = mem["cube"], mem["stock"]
    # stock's own run-time P writes, `move x0,p:>$...` at A P:0x75/0x77 and B P:0x70/0x72
    # (out/dsp/payload_*.asm): state, not code, so they hold what the frames left there
    live = {0: (0x58C, 0x59B), 1: (0x371, 0x380)}
    for core in (0, 1):
        for a in live[core]:
            c[core][a] = s[core][a]
    d0 = [a for a in range(0x2000) if c[0][a] != s[0][a]]
    check(f"core 0 (tracks 5-8): P:0000-1fff is stock's word for word but stock's own run-time words 58c/59b "
          f"({len(d0)} differ)", not d0,
          " ".join(f"{a:04x}" for a in d0[:12]))
    d1 = [a for a in range(0x2000) if c[1][a] != s[1][a]]
    seam = [a for a in d1 if a in (0x1A2, 0x1A3)]
    top = [a for a in d1 if a >= 0x1D9F]
    rest = [a for a in d1 if a not in seam and a not in top]
    check(f"core 1 (tracks 1-4): every stock word below P:1d9f is stock's but the seam's two and stock's run-time 371/380 "
          f"({len(rest)} others differ; seam {[hex(a) for a in seam]})", not rest and len(seam) == 2,
          " ".join(f"{a:04x}" for a in rest[:12]))
    check(f"core 1: P:1d9f.. holds CUBE ({len(top)} words differ from stock's empty top) and the seam jumps there",
          len(top) > 400 and c[1][0x1A2] == 0x0BF080 and c[1][0x1A3] == 0x1D9F)
    check("core 1: stock's own empty top is zero above P:1d9f on stock", all(v == 0 for v in s[1][0x1D9F:]))


def fxid_run(image, elf, tag, out):
    """Every row of both choosers on T3, T4, T7 and T8, stepped one row down from NONE: the bytes each stores."""
    got = {}
    p = boot(image, elf)
    try:
        rows = {s: len(chooser(p, s)) for s in ("FX1", "FX2")}
        for t in ("T3", "T4", "T7", "T8"):
            for slot in ("FX1", "FX2"):
                pick_fx(p, t, slot, 0)
                for k in range(1, rows[slot]):
                    p.press(t)
                    p.press(slot)
                    p.run(200)
                    before = p.part_bytes()
                    p.press("FUNC", slot)
                    p.run(400)
                    p.press("DOWN")
                    p.press("YES")
                    p.run(400)
                    p.press("NO")
                    p.run(200)
                    after = p.part_bytes()
                    got[f"{t} {slot} {k}"] = {str(i): after[i] for i in range(len(after)) if after[i] != before[i]}
            print(f"    {tag} {t} done", flush=True)
    finally:
        p.quit()
    out.write_text(json.dumps(got))


def step_fxid(image, elf, stock):
    print("== fxid: each chooser row on T3, T4, T7, T8 stores stock's effect id ==", flush=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="cubefxid_"))
    import multiprocessing as mp
    jobs = [mp.Process(target=fxid_run, args=(image, elf, "cube", work / "cube.json")),
            mp.Process(target=fxid_run, args=(stock, None, "stock", work / "stock.json"))]
    [j.start() for j in jobs]
    [j.join() for j in jobs]
    c, s = (json.loads((work / f"{n}.json").read_text()) for n in ("cube", "stock"))
    for k, v in s.items():
        check(f"{k}: {v}", c.get(k) == v and bool(v), f"cube {c.get(k)}")


# ---- CUBE's own pages ------------------------------------------------------------------------

def step_ui(image, elf, stock):
    print("== ui: CUBE on T1 (core 1), its pages, UNI, letter, PMTR; T5-T8 without CUBE ==", flush=True)
    s = boot(stock)
    try:
        stock_t5 = []
        for t in ("T1", "T5"):
            s.press(t)
            s.press("FUNC", "SRC")
            s.run(300)
            for _ in range(7):
                s.press("UP")
            seq = [scr(s)]
            for _ in range(7):
                s.press("DOWN")
                seq.append(scr(s))
            stock_t5.append(seq)
            s.press("NO")
            s.run(300)
    finally:
        s.quit()
    p = boot(image, elf)
    try:
        # T5-T8 first, on a fresh Part
        for i, t in enumerate(("T1", "T5")):
            p.press(t)
            p.press("FUNC", "SRC")
            p.run(300)
            for _ in range(7):
                p.press("UP")
            seq = [scr(p)]
            for _ in range(7):
                p.press("DOWN")
                seq.append(scr(p))
            if t == "T5":
                check("T5's SRC SETUP machine list draws exactly stock's (five rows, no CUBE)", seq == stock_t5[1])
                p.shot(SHOTS / "10_t5_machine_list_bottom.png")
                p.press("YES")
                p.run(600)
                raw = p.part_bytes()
                check("T5: DOWN past the last row and YES leaves no CUBE signature, and no popup window",
                      not signed(raw, 4) and window(p) in (0, SETUP_WINDOW), f"window {window(p):08x}")
            else:
                rows_c, rows_s = len(dedupe(seq)), len(dedupe(stock_t5[0]))
                check(f"T1's SRC SETUP list has a sixth row, CUBE ({rows_c} cursor rows; stock {rows_s})",
                      rows_c == 6 and rows_s == 5)
                p.shot(SHOTS / "01_t1_machine_list_cube_row.png")
            p.press("NO")
            p.run(300)
        for t in ("T5", "T8"):
            p.press(t)
            p.press("FUNC", "SRC")
            p.run(300)
            for _ in range(8):
                p.press("DOWN")
            p.press("YES")
            p.run(400)
            p.press("NO")
            p.run(300)
        raw = p.part_bytes()
        check("T5 and T8 after picking their last row: no signature, machine stays a stock type",
              not signed(raw, 4) and not signed(raw, 7) and raw[0x22 + 4] < 5 and raw[0x22 + 7] < 5,
              f"types {raw[0x22 + 4]} {raw[0x22 + 7]}")
        # a CUBE signature planted on T6 (a pasted track, a CUBE1 Part) goes back to FLEX
        part = p.part()
        p.cmd(f"poke {part + 0x22 + 5:#x} 01")
        for k, v in enumerate(b"CU\x01"):
            p.cmd(f"poke {part + PB + 30 * 5 + NB + k:#x} {v:02x}")
        p.cmd(f"poke {part + PB + 30 * 5 + FX + 5:#x} 7f")
        p.run(600)
        raw = p.part_bytes()
        check("a CUBE signature planted on T6 is put back to FLEX's defaults within a UI tick",
              not signed(raw, 5) and raw[PB + 150 + FX:PB + 156 + FX] == FLEX_PB and raw[SU + 150 + FX:SU + 156 + FX] == FLEX_SU,
              f"{list(raw[PB + 150 + FX:PB + 156 + FX])}")

        # CUBE on T1
        machine(p, "T1", ROW["CUBE"])
        raw = p.part_bytes()
        check("T1: CUBE assigned (FLEX + CU\\x01) with CUBE's defaults", signed(raw, 0) and cube_bytes(raw, 0) == DEFAULTS,
              f"{cube_bytes(raw, 0)}")
        live = list(p.peek(0x80000810 + 0x20, 6))
        check("before any PLAY, T1's live SETUP copy holds CUBE's SETUP defaults (FINE 64 OCT 2 UNI 0 TONE 0 MORPH 7 SYNC 1)",
              live == [64, 2, 0, 0, 7, 1], f"{live}")
        p.press("T1")
        press(p)
        if where(p) != "SRC":
            press(p)
        check("T1 on its SRC page", where(p) == "SRC", where(p))
        p.shot(SHOTS / "02_src_page.png")
        tgt = dict(PTCH=70, FM=10, MIX=40, X=20, Y=30, Z=50)
        before = cube_bytes(p.part_bytes(), 0)
        ok = all(turn(p, "ABCDEF"[i], 0, n, tgt[n]) for i, n in enumerate(SRC_PAGE))
        after = cube_bytes(p.part_bytes(), 0)
        check("SRC knobs A-F set PTCH FM MIX / X Y Z", ok and all(after[n] == tgt[n] for n in SRC_PAGE), f"{after}")
        check("... and nothing else", all(after[n] == before[n] for n in DEFAULTS if n not in SRC_PAGE))
        p.shot(SHOTS / "03_src_page_edited.png")
        press(p)
        check("SRC again: OSC B", where(p) == "OSCB", where(p))
        p.shot(SHOTS / "04_oscb_page.png")
        tgt = dict(BPCH=76, LAW=1, LINK=2, BX=50, BY=60, BZ=90)
        before = cube_bytes(p.part_bytes(), 0)
        ok = all(turn(p, "ABCDEF"[i], 0, n, tgt[n]) for i, n in enumerate(OSCB_PAGE))
        after = cube_bytes(p.part_bytes(), 0)
        check("OSC B knobs A-F set BPCH LAW LINK / BX BY BZ", ok and all(after[n] == tgt[n] for n in OSCB_PAGE), f"{after}")
        check("... and nothing else", all(after[n] == before[n] for n in DEFAULTS if n not in OSCB_PAGE))
        p.shot(SHOTS / "05_oscb_page_edited.png")
        seen = [where(p)]
        for _ in range(5):
            press(p)
            seen.append(where(p))
        check("single SRC presses alternate SRC and OSC B and never open SETUP", "SETUP" not in seen and
              seen == ["OSCB", "SRC", "OSCB", "SRC", "OSCB", "SRC"], " ".join(seen))
        tap(p)
        check("a double press of SRC opens SETUP", where(p) == "SETUP", where(p))
        p.shot(SHOTS / "06_setup_page.png")
        tgt = dict(FINE=70, OCT=3, UNI=40, TONE=1, MORPH=5, SYNC=0)
        before = cube_bytes(p.part_bytes(), 0)
        ok = all(turn(p, "ABCDEF"[i], 0, n, tgt[n]) for i, n in enumerate(SETUP_PAGE))
        after = cube_bytes(p.part_bytes(), 0)
        check("SETUP knobs A-F set FINE OCT UNI / TONE MORPH SYNC", ok and all(after[n] == tgt[n] for n in SETUP_PAGE),
              f"{after}")
        check("... and nothing else", all(after[n] == before[n] for n in DEFAULTS if n not in SETUP_PAGE))
        p.shot(SHOTS / "07_setup_page_edited.png")
        p.press("NO")
        p.run(300)
        p.press("FUNC", "SRC")
        p.run(400)
        check("FUNC+SRC opens SETUP too", where(p) == "SETUP", where(p))
        # UNI's target: the encoder push, A -> B -> BOTH
        cyc = [UTGT[p.part_bytes()[utgt_at(0)]]]
        for i in range(3):
            p.push("C")
            p.run(1500)                     # the label redraws on the page's own refresh
            cyc.append(UTGT[p.part_bytes()[utgt_at(0)]])
            p.shot(SHOTS / f"08_setup_uni_{cyc[-1].lower()}.png")
        check("UNI encoder push cycles its target A -> B -> BOTH -> A (from B: BOTH, A, B)",
              cyc == ["B", "BOTH", "A", "B"] and p.part_bytes()[at(0, "UNI")] == 40, " ".join(cyc))
        p.press("NO")
        p.run(300)
        # UNI really moves the oscillator(s) it names: the control record and the
        # sound, through the panel (UNI 40 from the SETUP knobs above; the target by
        # the push, from SETUP), a PLAY each
        part = p.part()
        trigs(p, ("T1",), (1, 5, 9, 13))
        rec, snd = {}, {}

        def play(label):
            p.cmd("audio start tracks")
            p.press("PLAY")
            p.run(1500)
            rec[label] = tuple(put24(int.from_bytes(p.peek(p.sym["cube_last_record"] + 4 * i, 4), "big"))
                               for i in (2, 3))
            p.press("STOP")
            p.run(300)
            snd[label] = [f[8] for f in p.audio(24)][2000:2000 + 30000]
            p.cmd("audio stop")
            wav(SHOTS / "audio" / f"uni_{label.lower()}.wav", snd[label])

        for _ in range(4):
            p.press("FUNC", "SRC")
            p.run(400)
            label = UTGT[p.part_bytes()[utgt_at(0)]]
            p.press("NO")
            p.run(300)
            if label not in rec:
                play(label)
            p.press("FUNC", "SRC")
            p.run(400)
            p.push("C")
            p.run(400)
            p.press("NO")
            p.run(300)
        p.press("FUNC", "SRC")
        p.run(400)
        turn(p, "C", 0, "UNI", 0)
        p.press("NO")
        p.run(300)
        play("off")
        print(f"    (inc_a, inc_b) at UNI 40 by target, and UNI 0: {rec}")
        off = rec["off"]
        check("UNI on A raises oscillator A's increment only", rec["A"][0] > off[0] and rec["A"][1] == off[1], f"{rec}")
        check("UNI on B raises oscillator B's increment only", rec["B"][0] == off[0] and rec["B"][1] > off[1], f"{rec}")
        check("UNI on BOTH moves both increments (A down, B up)", rec["BOTH"][0] < off[0] and rec["BOTH"][1] > off[1],
              f"{rec}")
        check("the four renders (A, B, BOTH, UNI 0) differ from each other and all sound",
              len({tuple(v) for v in snd.values()}) == 4 and all(rms(v) > 300 for v in snd.values()))
        # the strip's letter: AMP page, T1 CUBE vs T1 FLEX
        p.press("T1")
        p.press("AMP")
        p.run(400)
        rows_c = p.screen()
        p.shot(SHOTS / "09_track_letter_c.png")
        p.cmd(f"poke {part + PB + NB:#x} 00")
        p.run(400)
        rows_f = p.screen()
        p.cmd(f"poke {part + PB + NB:#x} 43")
        p.run(400)
        diff = [(y, x) for y, (a, b) in enumerate(zip(rows_c, rows_f)) for x, (u, v) in enumerate(zip(a, b)) if u != v]
        box = (max(y for y, _ in diff) - min(y for y, _ in diff) + 1, max(x for _, x in diff) - min(x for _, x in diff) + 1) if diff else (0, 0)
        check(f"AMP page: CUBE vs FLEX on T1 differ only in a glyph-sized box {box} (the strip letter)",
              diff and box[0] <= 10 and box[1] <= 10, f"{len(diff)} px")
        # LFO SETUP PMTR: CUBE's names
        p.press("LFO")
        p.run(300)
        p.press("FUNC", "LFO")
        p.run(500)
        shots = {}
        for label, sig in (("cube", 0x43), ("flex", 0x00)):
            p.cmd(f"poke {part + PB + NB:#x} {sig:02x}")
            p.run(500)
            p.enc("A", 1)
            p.enc("A", -1)
            p.run(400)
            shots[label] = scr(p)
            p.shot(SHOTS / f"11_lfo_pmtr_{label}.png")
        check("LFO SETUP's PMTR row draws differently for CUBE than for FLEX (CUBE's own names)",
              shots["cube"] != shots["flex"])
        p.press("NO")
        p.run(300)
        check("the port never stopped the DSP frames", p.long("cube_render_calls") > 0)
    finally:
        p.quit()


def step_four(image, elf, stock):
    print("== four: CUBE on T1-T4 (core 1), THRU on T5-T8 (core 0) ==", flush=True)
    p = boot(image, elf)
    try:
        for t in range(4):
            machine(p, f"T{t + 1}", ROW["CUBE"])
        for t in range(4, 8):
            thru(p, f"T{t + 1}")
        raw = p.part_bytes()
        check("T1-T4 are CUBE, T5-T8 THRU", all(signed(raw, t) for t in range(4)) and
              all(raw[0x22 + t] == ROW["THRU"] and not signed(raw, t) for t in range(4, 8)))
        part = p.part()
        for t in range(4):
            p.cmd(f"poke {part + at(t, 'PTCH'):#x} {52 + 4 * t:02x}")
            p.cmd(f"poke {part + at(t, 'X'):#x} {30 * t:02x}")
        trigs(p, [f"T{t + 1}" for t in range(8)], (1, 5, 9, 13))
        p.cmd(f"watch {TICK_ISR:#x}")
        p.cmd("hits", b"hits")
        fr = stems(p, 3000)
        hits = len(p.cmd("hits", b"hits").split()[2:])
        p.cmd("watch off")
        peaks = [max(abs(f[8 + 2 * t]) for f in fr) for t in range(8)]
        check(f"every stem sounds {peaks}", all(v > 300 for v in peaks))
        hz = [round(pitch([f[8 + 2 * t] for f in fr]), 1) for t in range(4)]
        check(f"the four CUBE voices play their own notes {hz}", len(set(round(h) for h in hz)) == 4)
        check(f"the sequencer runs: {hits} tick ISRs in 3 s of PLAY", hits > 500)
        wav(SHOTS / "audio" / "four_main.wav", [v for f in fr for v in f[2:4]], ch=2)
        p.press("T1")
        p.run(300)
        p.shot(SHOTS / "12_four_cube_tracks.png")
    finally:
        p.quit()


def step_save(image, elf, stock):
    print("== save: SAVE, change, RELOAD on a writable card ==", flush=True)
    p = boot(image, elf, writable=True)
    try:
        P.project_menu(p, 6)
        p.press("YES")
        p.run(1000)
        for _ in range(5):
            p.press("YES")
            p.run(2500)
        P.settle_card(p, at_least_ms=25000)
        p.press("NO")
        machine(p, "T1", ROW["CUBE"])
        machine(p, "T3", ROW["CUBE"])
        part = p.part()
        want = {0: dict(PTCH=70, X=33, Z=99, MIX=20, FINE=80, OCT=3, UNI=105, MORPH=5, BX=11, LINK=1, BPCH=52),
                2: dict(PTCH=58, Y=77, FM=60, FINE=50, TONE=2, SYNC=2, BY=66, BZ=7, LAW=1)}
        p.press("T1")
        press(p)
        if where(p) != "SRC":
            press(p)
        ok = turn(p, "A", 0, "PTCH", 70) and turn(p, "D", 0, "X", 33)
        check("T1's SRC knobs move its bytes on a new project", ok)
        for t, w in want.items():
            for n, v in w.items():
                p.cmd(f"poke {part + at(t, n):#x} {v:02x}")
        p.cmd(f"poke {part + utgt_at(0):#x} 01")
        p.run(400)
        raw = p.part_bytes()
        saved = {t: cube_bytes(raw, t) for t in (0, 2)}
        P.project_menu(p, 1)
        p.press("YES")
        P.settle_card(p, at_least_ms=20000)
        p.press("NO")
        for t in (0, 2):
            p.cmd(f"poke {part + at(t, 'X'):#x} 05")
            p.cmd(f"poke {part + at(t, 'BX'):#x} 78")
        p.cmd(f"poke {part + utgt_at(0):#x} 02")
        raw = p.part_bytes()
        check("after SAVE the bytes were changed", cube_bytes(raw, 0) != saved[0] and cube_bytes(raw, 2) != saved[2])
        P.project_menu(p, 2)
        p.press("YES")
        P.settle_card(p, at_least_ms=25000)
        p.press("NO")
        raw = p.part_bytes()
        check("RELOAD brings back T1's and T3's bytes and signatures, and T1's UNI target BOTH",
              all(cube_bytes(raw, t) == saved[t] and signed(raw, t) for t in (0, 2)) and raw[utgt_at(0)] == 1,
              f"{ {t: cube_bytes(raw, t) for t in (0, 2)} } utgt {raw[utgt_at(0)]}")
        check("T2, T4-T8 are not CUBE", not any(signed(raw, t) for t in (1, 3, 4, 5, 6, 7)))
        machine(p, "T3", ROW["FLEX"])
        raw = p.part_bytes()
        check("FLEX on T3: signature gone, FLEX's defaults back, NEIGHBOR bytes zero",
              not signed(raw, 2) and raw[PB + 60 + FX:PB + 66 + FX] == FLEX_PB and raw[SU + 60 + FX:SU + 66 + FX] == FLEX_SU
              and raw[PB + 60 + NB:PB + 66 + NB] == bytes(6) and raw[SU + 60 + NB:SU + 66 + NB] == bytes(6))
    finally:
        p.quit()
    banks = {k: v for k, v in p.card_files().items() if k.lower().endswith("bank01.work")}
    check(f"bank01.work on the card carries the signature ({', '.join(banks) or 'none'})",
          bool(banks) and next(iter(banks.values())).count(b"CU\x01") >= 2)


def step_clock(image, elf, stock):
    print("== clock: MIDI clock and notes with CUBE playing on T1 ==", flush=True)
    p = boot(image, elf)
    try:
        machine(p, "T1", ROW["CUBE"])
        trigs(p, ("T1",), (1, 5, 9, 13))
        p.cmd(f"watch {TICK_ISR:#x}")
        p.cmd("hits", b"hits")
        fr = stems(p, 2000)
        hits = len(p.cmd("hits", b"hits").split()[2:])
        p.cmd("watch off")
        t1 = [f[8] for f in fr]
        hz = pitch(t1)
        check(f"T1 at defaults plays C4: {hz:.1f} Hz (261.6)", abs(hz - 261.6) < 3)
        check(f"frames and the sequencer tick run: {hits} tick ISRs in 2 s", hits > 300)
        wav(SHOTS / "audio" / "t1_c4.wav", t1)
    finally:
        p.quit()


STEPS = dict(fx=step_fx, fxaudio=step_fxaudio, fxid=step_fxid, dspmem=step_dspmem, ui=step_ui, four=step_four, save=step_save, clock=step_clock)

if __name__ == "__main__":
    steps = list(STEPS) if sys.argv[1] == "all" else sys.argv[1].split(",")
    image, elf = sys.argv[2], sys.argv[3]
    stock = sys.argv[4] if len(sys.argv) > 4 else str(ROOT / "out/raw/section_3_MAIN_OS.bin")
    SHOTS.mkdir(parents=True, exist_ok=True)
    for st in steps:
        STEPS[st](image, elf, stock)
    print(f"cube static gate: {len(passes)} PASS, {len(failures)} FAIL" + (f": {failures}" if failures else ""))
    sys.exit(1 if failures else 0)
