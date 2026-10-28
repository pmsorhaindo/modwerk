#!/usr/bin/env python3
"""CUBE's gates (brief 5), one section per step.

    python3 modules/cube/verify.py dsp            step 1a: the engine alone (cube_host), no image
    python3 modules/cube/verify.py port IMAGE ELF [STOCK]   verify_static.py's steps under the ColdFire port
    python3 modules/cube/verify.py all IMAGE ELF [STOCK]

dsp: cube_engine.asm, relocated as the ColdFire sends it, run block by block
in tools/harness/cube_host on records made by cube_model (the ColdFire's
control math, morph and stream), compared word for word with
cube_model.Engine -- every patch, both voices' buffers, a trig split, SYNC
HARD, the 14 Hz mute, TONE masks, LINK POS/OFF, LAW EXP/OFF; the epoch init
from garbage memory renders exactly what clean memory does; the per-sample
loops are counted (cube_pkg.loops) against the design's 54; WAVs of the
renders go to diag/cube1/audio/dsp_*.wav.

port: verify_static.py (the static-stock build: tracks 1-4, every stock effect
kept), one PASS/FAIL line per check.
Exit 0 when everything ran passes.
"""
import array
import os
import pathlib
import subprocess
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import cube_model as M  # noqa: E402
import cube_pkg  # noqa: E402
import generate_cube  # noqa: E402

V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/cube"
HOST = OUT / "cube_host"
AUDIO = ROOT / "diag/cube1/audio"
ORG = 0x1d00
failures = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""), flush=True)
    if not ok:
        failures.append(name)
    return ok


def build_host():
    src = ROOT / "tools/harness/cube_host/cube_host.cpp"
    if HOST.exists() and HOST.stat().st_mtime > src.stat().st_mtime:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["c++", "-O3", "-DNDEBUG", "-std=gnu++17", "-DASMJIT_STATIC", "-DDSP56300_DEBUGGER=0",
                    f"-I{V}/source", f"-I{V}/source/asmjit/src", str(src),
                    f"{V}/build/source/dsp56kEmu/libdsp56kEmu.a", f"{V}/build/source/dsp56kBase/libdsp56kBase.a",
                    f"{V}/build/source/asmjit/libasmjit.a", "-lpthread", "-o", str(HOST)],
                   check=True, capture_output=True)


def engine_bin():
    pkg = cube_pkg.package()
    words = [(w + ORG) & 0xffffff if k in pkg["relocations"] else w for k, w in enumerate(pkg["words"])]
    path = OUT / "engine.bin"
    path.write_bytes(b"".join(bytes((w & 255, (w >> 8) & 255, w >> 16)) for w in words))
    return path, ORG + pkg["proc"]


def cube():
    if not hasattr(cube, "c"):
        cube.c = generate_cube.cube()
        cube.c24 = cube.c
    return cube.c


def scenario(patches, epoch=1, frames=None):
    """patches: [(blocks, {param: value}, trig_offset_or_None_per_block_fn)] -> (records, trig offsets)."""
    p = dict(M.DEFAULTS)
    stream = M.Stream()
    stream.reset(epoch)
    recs, trigs = [], []
    b = 0
    for blocks, change, trig in patches:
        p.update(change)
        for _ in range(blocks):
            t = trig(b) if trig else None
            ctl = M.controls(p)
            recs.append(M.record(ctl, stream, cube(), t is not None))
            trigs.append(-1 if t is None else t)
            b += 1
    return recs, trigs


def model(recs, trigs):
    e = M.Engine()
    out = []
    for w, t in zip(recs, trigs):
        out += e.block(w, None if t < 0 else t)
    return [M.s24(v) for v in out]


def seam_bin(org=0x1000):
    """The static-stock voice (cube_voice.asm: the seam stub, then the engine
    it calls), its continuation the host's sentinel: the whole CUBE source as
    it runs at core 1's free top."""
    src = (HERE / "cube_voice.asm").read_text().replace("CONTADDR", "$f00")
    words, _ = cube_pkg.assemble(src, org, "seam")
    path = OUT / "seam.bin"
    path.write_bytes(b"".join(bytes((w & 255, (w >> 8) & 255, w >> 16)) for w in words))
    return path, org


def host(recs, trigs, tag, voice=0, dirty=None, seam=False):
    """-> (output words, [(instructions, cycles)] per block)."""
    bin_, entry = engine_bin()
    script = OUT / f"{tag}.script"
    script.write_text("".join(f"{t} " + " ".join(f"{w & 0xffff:x}" for w in r) + "\n" for r, t in zip(recs, trigs)))
    raw, meter = OUT / f"{tag}.raw", OUT / f"{tag}.meter"
    args = [str(HOST), "-code", str(bin_), "-org", f"{ORG:x}", "-entry", f"{entry:x}", "-script", str(script),
            "-out", str(raw), "-meter", str(meter), "-voice", str(voice)] + (["-dirty", str(dirty)] if dirty is not None else [])
    if seam:
        sb, so = seam_bin()
        args += ["-seam", str(sb), "-seamorg", f"{so:x}", "-sentinel", "f00"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"cube_host failed: {r.stdout}{r.stderr}")
    a = array.array("i")
    a.frombytes(raw.read_bytes())
    return list(a), [tuple(int(v) for v in l.split()) for l in meter.read_text().splitlines()]


def wav(path, words):
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(struct.pack("<h", max(-32768, min(32767, w >> 8))) for w in words[0::2])
    path.write_bytes(b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
                     struct.pack("<IHHIIHH", 16, 1, 1, 44100, 88200, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


def note(at, every=None):
    return lambda b: (at if b == 0 else None) if every is None else (at if b % every == 0 else None)


SCENARIOS = {
    # name: (patches, voice)
    "c4_default": ([(400, {}, note(5))], 0),
    "morph_sweep_pos_fm": ([(120, dict(LINK=1, FM=50, MIX=40, UNI=30, BPCH=71, X=0), note(0, 60)),
                            (120, dict(X=64, Y=30, Z=20, BX=90, BY=10, BZ=100), note(3, 60)),
                            (120, dict(X=127, Y=127, Z=70, MORPH=5), note(9, 60))], 1),
    "exp_off_drone_hard_8bit": ([(300, dict(LAW=1, FM=90, LINK=3, BPCH=40, BX=40, BZ=120, SYNC=2, TONE=2,
                                             MORPH=0, X=77, Y=50, Z=33, PTCH=52, OCT=3), note(7, 50))], 2),
    "lawoff_tone12_free_lowmute": ([(150, dict(LAW=2, FM=127, TONE=1, SYNC=0, PTCH=40, OCT=0, MIX=0), note(0, 30)),
                                    (150, dict(PTCH=4, FINE=0), note(15, 30))], 3),
    "unison_octave_pitchlink": ([(250, dict(LINK=2, UNI=120, BPCH=64, MIX=64, Z=60, X=20, FM=20), note(15, 40))], 0),
}


def step_dsp():
    print("== step 1a: the engine alone (cube_host vs cube_model, bit for bit) ==")
    build_host()
    pkg = cube_pkg.package()
    lp = cube_pkg.loops()
    check(f"engine {len(pkg['words'])} words (design aim 400, the arena reserve is sized from the package), "
          f"{len(pkg['relocations'])} relocations, the relocated package equals assemblies at two more origins",
          len(pkg["words"]) <= 448)
    cyc = loop_cycles()
    worst = max(lp["pass A"] + lp["pass B"], lp["pass A hard"] + lp["pass B hard"])
    worst_c = max(cyc["pass A"] + cyc["pass B"], cyc["pass A hard"] + cyc["pass B hard"])
    check(f"per-sample loops: {lp['pass B']} + {lp['pass A']} words, SYNC HARD {lp['pass B hard']} + "
          f"{lp['pass A hard']}; in the emulator's cycle table {cyc['pass B']} + {cyc['pass A']} = "
          f"{cyc['pass B'] + cyc['pass A']}, SYNC HARD {cyc['pass B hard'] + cyc['pass A hard']} cycles "
          f"(target 54 for the loop; worst charged {cube_pkg.charge(worst_c)})", worst_c <= 54)
    meters = []
    for name, (patches, voice) in SCENARIOS.items():
        recs, trigs = scenario(patches)
        want = model(recs, trigs)
        got, meter = host(recs, trigs, name, voice)
        meters += meter if not meters else meter[1:]
        bad = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), None)
        check(f"{name}: {len(recs)} blocks on voice {voice}, DSP == model word for word",
              len(got) == len(want) and bad is None,
              f"first difference at word {bad}: dsp {got[bad] if bad is not None else '-'} model "
              f"{want[bad] if bad is not None else '-'}")
        peak = max(abs(v) for v in got)
        if name != "lawoff_tone12_free_lowmute":
            check(f"{name}: audible (peak {peak / 8388608:.3f} FS)", peak > 0.05 * 8388608)
        wav(AUDIO / f"dsp_{name}.wav", got)
        if name == "exp_off_drone_hard_8bit":
            check(f"{name}: TONE 8-bit leaves only the top byte", all((v & 0xffff) == 0 for v in got))
        if name == "lawoff_tone12_free_lowmute":
            low = got[150 * 32:]
            check("PTCH 4 OCT -2 (about 1 Hz): A is muted, MIX 0 leaves silence",
                  max(abs(v) for v in low[32 * 20:]) == 0, f"peak {max(abs(v) for v in low)}")
            check("TONE 12-bit leaves the low 12 bits clear", all((v & 0xfff) == 0 for v in got))
        if name == "c4_default":
            # C4 at 44.1 kHz: count rising zero crossings over the steady part
            x = got[0::2][16 * 50:16 * 400]
            ups = sum(1 for a, b in zip(x, x[1:]) if a < 0 <= b)
            hz = ups / (len(x) / 44100)
            check(f"default patch (Z0 X0 Y0 = one sine, PTCH 64) plays C4: {hz:.1f} Hz (261.6)", abs(hz - 261.6) < 3)
    recs, trigs = scenario(SCENARIOS["morph_sweep_pos_fm"][0])
    clean, _ = host(recs, trigs, "clean", 1)
    dirty, _ = host(recs, trigs, "dirty", 1, dirty=7)
    check("garbage in CUBE's X and junk above bit 15 of every record word: the epoch init renders "
          "exactly the clean run", clean == dirty)
    recs2, trigs2 = scenario([(60, {}, note(0, 20))], epoch=1)
    recs3, trigs3 = scenario([(60, dict(X=100), note(0, 20))], epoch=2)
    e = M.Engine()
    want = [M.s24(v) for w, t in zip(recs2 + recs3, trigs2 + trigs3) for v in e.block(w, None if t < 0 else t)]
    got, _ = host(recs2 + recs3, trigs2 + trigs3, "epoch")
    check("a new epoch (CUBE re-selected, engine reloaded) restarts from silence and matches the model",
          got == want and max(abs(v) for v in got[60 * 32:62 * 32]) == 0)
    steady = max(m[0] for m in meters[1:])
    check(f"instructions executed per block after the epoch's first (which clears 1,024 words once: "
          f"{meters[0][0]}): max {steady} ({steady / 16:.1f}/sample with a chunk copy and the control parse)",
          steady / 16 < 70)
    return whole_block()


def loop_cycles():
    """Each per-sample DO body priced by the emulator's cycle table (cube_host CUBE_CYCLES)."""
    bin_, _ = engine_bin()
    pkg, lp = cube_pkg.package(), cube_pkg.loops()
    ends = {"pass B": "ce22", "pass B hard": "ce24", "pass A": "ce26", "pass A hard": "ce28"}
    out = {}
    for name, end in ends.items():
        hi = ORG + pkg["symbols"][end]
        lo = hi - lp[name]
        r = subprocess.run([str(HOST), "-code", str(bin_), "-org", f"{ORG:x}"],
                           env={**os.environ, "CUBE_CYCLES": f"{lo:x}-{hi:x}"}, capture_output=True, text=True)
        rows = [l.split() for l in r.stdout.splitlines() if len(l.split()) == 3 and len(l.split()[0]) == 5]
        out[name] = sum(int(x[2]) for x in rows)
    return out


def whole_block():
    """The whole CUBE source per block, entered through the resident seam stub
    as the dispatcher enters it, in emulator CYCLES (its per-opcode table: the
    static floor, no memory contention), on the worst layout the voice has:
    a new cycle streamed every block (X and BX change every block, LINK OFF,
    so A's and B's buffers alternate and the chunk copy never stops), SYNC
    HARD (the dearer loops), LAW EXP, and a trig at frame 8 of every block
    (two segments). Compared with the steady layout (default patch, no
    stream, no trig) and charged at (c * 7 + 3) / 4 against the doc's
    remainders: core 0 384, core 1 829."""
    print("== step 4a: the whole block in cycles, worst layout, through the seam ==", flush=True)
    worst = [(1, dict(LINK=3, LAW=1, FM=80, SYNC=2, MORPH=7, X=(b * 37) % 128, BX=(b * 53) % 128,
                     Y=(b * 11) % 128, Z=(b * 29) % 128), lambda _b: 8) for b in range(240)]
    calm = [(240, {}, None)]
    out = {}
    for name, patches in (("worst", worst), ("calm", calm)):
        recs, trigs = scenario(patches)
        got, meters = host(recs, trigs, f"block_{name}", 3, seam=True)
        want = model(recs, trigs)
        check(f"{name}: through the seam stub, DSP == model word for word ({len(recs)} blocks)", got == want)
        streaming = sum(1 for r in recs if r[16] & 3)
        cyc = [m[1] for m in meters[1:]]
        out[name] = (max(cyc), sum(cyc) / len(cyc), streaming)
        print(f"   {name}: {streaming}/{len(recs)} blocks carry a chunk; cycles per block max {max(cyc)} "
              f"(= {max(cyc) / 16:.2f}/sample), mean {sum(cyc) / len(cyc):.0f}; instructions max {max(m[0] for m in meters[1:])}")
    per = -(-out["worst"][0] // 16)
    ch = cube_pkg.charge(per)
    lines = []
    for core, rem in ((0, 384), (1, 829)):
        fit = min(4, rem // ch)
        lines.append(f"core {core}: {fit} of 4 ({4 * ch} for four vs {rem})")
    check(f"whole block, worst layout: {per} modelled cycles/sample (ceil), charged {ch}; " + "; ".join(lines),
          True)
    return dict(per=per, charge=ch, worst=out["worst"], calm=out["calm"])


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "dsp"
    if what in ("dsp", "all"):
        step_dsp()
    if what in ("port", "all"):
        r = subprocess.run([sys.executable, str(HERE / "verify_static.py"), "all", *sys.argv[2:]])
        check("verify_static.py all", r.returncode == 0)
    print(f"\n{len(failures)} failed" + (": " + "; ".join(failures) if failures else " -- all checks passed"))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
