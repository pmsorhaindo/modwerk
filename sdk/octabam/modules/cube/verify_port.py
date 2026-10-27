"""CUBE under the ColdFire port, brief 5 steps 0-4 (called by verify.py port).

Each boot drives the emulated panel on a scratch card:
  0. diag/repro_clock.py on the image: clock and notes with OT_HW_RULES on.
  1. CUBE on T1 through SRC SETUP: Part signature and defaults, the engine
     uploaded to core 1 only, T1 plays C4 on its stem (T2 FLEX beside it is
     untouched), a morph and an OSC B detune change the sound.
  2. Pages and Part bytes: SRC knobs write PTCH..MIX, SETUP knobs FINE..SYNC,
     OSC B knobs BX..BPCH into the track's own bytes; SAVE, change, RELOAD on
     a writable card brings each track's bytes back; leaving CUBE restores
     FLEX's bytes.
  3. The ring SRC -> SETUP -> OSC B -> SRC on the CUBE track, single press
     and FUNC+SRC, and a stock FLEX track keeping stock's double tap.
  4. All eight tracks CUBE: both engines, every stem sounds, the sequencer
     clock keeps running; the seam's CUBE branch timed per core.
LCD shots go to diag/cube1/, port WAVs to diag/cube1/audio/port_*.wav."""
import math
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import port as P  # noqa: E402
import cube_pkg  # noqa: E402

SHOTS = ROOT / "diag/cube1"
AUDIO = SHOTS / "audio"
PB, SU, FX, NB = 0x2A, 0x1DA, 6, 18
SETUP_WINDOW = 0x400BB7C8
TICK_ISR = 0x400A1E0C
SRC_NAMES = ("PTCH", "X", "Y", "Z", "FM", "MIX")
SETUP_NAMES = ("FINE", "OCT", "UNI", "TONE", "MORPH", "SYNC")
OSCB_NAMES = ("BX", "BY", "BZ", "LINK", "LAW", "BPCH")
DEFAULTS = dict(PTCH=64, X=0, Y=0, Z=0, FM=0, MIX=64, FINE=64, OCT=2, UNI=0, TONE=0, MORPH=7, SYNC=1,
                BX=0, BY=0, BZ=0, LINK=0, LAW=0, BPCH=64)
check = None


def at(t, name):
    """The Part offset of CUBE byte `name` on track t (0..7)."""
    if name in SRC_NAMES:
        return PB + 30 * t + FX + SRC_NAMES.index(name)
    if name in SETUP_NAMES:
        return SU + 30 * t + FX + SETUP_NAMES.index(name)
    k = OSCB_NAMES.index(name)
    return PB + 30 * t + NB + 3 + k if k < 3 else SU + 30 * t + NB + k - 3


def cube_bytes(raw, t):
    return {n: raw[at(t, n)] for n in DEFAULTS}


def signed(raw, t):
    return raw[0x22 + t] == 1 and raw[PB + 30 * t + NB:PB + 30 * t + NB + 3] == b"CU\x01"


def boot(image, elf, **kw):
    work = pathlib.Path(tempfile.mkdtemp(prefix="cube_")) / "w"
    return P.Port(image, work, elf=elf, extra=["--audio-in", "tones"] + list(kw.pop("extra", ())), **kw)


def machine(p, track, row):
    """SRC SETUP on `track`, the machine list's row (0 FLEX? stock order; 5 CUBE), YES, closed."""
    p.press(track)
    p.press("FUNC", "SRC")
    p.run(300)
    for _ in range(6):
        p.press("UP")
    for _ in range(row):
        p.press("DOWN")
    p.press("YES")
    p.run(400)
    p.press("NO")
    p.run(300)


def window(p):
    w = int.from_bytes(p.peek(0x400BCD14, 4), "big")
    return w if int.from_bytes(p.peek(w + 8, 4), "big") else 0


def view(p):
    return p.peek(p.sym["cube_view"], 1)[0]


def where(p):
    """SETUP (SRC SETUP window), OSCB, SRC (page 0, no window), or what else."""
    w = window(p)
    if w:
        return "SETUP" if w == SETUP_WINDOW else f"window {w:08x}"
    page = int.from_bytes(p.peek(0x460D1684, 4), "big")
    if page != 0:
        return f"page {page}"
    return "OSCB" if view(p) == 2 else "SRC"


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


def turn(p, enc, t, name, target, tries=6):
    """Encoder `enc` until byte `name` of track t reads `target`."""
    for _ in range(tries):
        v = p.part_bytes()[at(t, name)]
        if v == target:
            return True
        d = max(-120, min(120, (target - v) * (4 if name in ("OCT", "TONE", "MORPH", "SYNC", "LINK", "LAW") else 1)))
        p.enc(enc, d)
        if os.environ.get("CUBE_TRACE"):
            print(f"    turn {name} t{t}: {v} {d:+d} -> {p.part_bytes()[at(t, name)]} ({where(p)}, view {view(p)})")
    return p.part_bytes()[at(t, name)] == target


def trigs(p, tracks, steps):
    p.press("REC")
    for t in tracks:
        p.press(t)
        for s in steps:
            p.press(f"TRIG{s}")
    p.press("REC")


def stems(p, ms, extra=None):
    p.cmd("audio start tracks")
    p.press("PLAY")
    p.run(ms)
    if extra:
        extra()
    p.press("STOP")
    p.run(300)
    fr = p.audio(24)
    p.cmd("audio stop")
    return fr


def wav(path, x, ch=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(struct.pack("<h", v) for v in x)
    path.write_bytes(b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
                     struct.pack("<IHHIIHH", 16, 1, ch, 44100, 44100 * 2 * ch, 2 * ch, 16) + b"data" +
                     struct.pack("<I", len(pcm)) + pcm)


def pitch(x):
    """Hz of the loudest stretch, by rising zero crossings over up to 1 s."""
    loud = [i for i, v in enumerate(x) if abs(v) > 300]
    if not loud:
        return 0.0
    seg = x[loud[0] + 200:loud[0] + 200 + 44100]
    ups = sum(1 for a, b in zip(seg, seg[1:]) if a < 0 <= b)
    return ups / (len(seg) / 44100) if seg else 0.0


def gap_after_onset(x):
    """The longest run of exact zeros inside the sounding part (a lost frame is 16)."""
    loud = [i for i, v in enumerate(x) if abs(v) > 300]
    if not loud:
        return 0
    run = best = 0
    for v in x[loud[0]:loud[-1]]:
        run = run + 1 if v == 0 else 0
        best = max(best, run)
    return best


# ---- step 0 ------------------------------------------------------------------------

def step0(image):
    print("== step 0: the OCTABAM74 transport keeps clock and notes (OT_HW_RULES on) ==", flush=True)
    r = subprocess.run([sys.executable, str(ROOT / "diag/repro_clock.py"), str(image)], capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if "UART0" in l or "hardware rules" in l or "tick ISR" in l]
    for l in lines:
        print("   " + l.strip())
    rules = next((l for l in lines if "hardware rules" in l), "")
    check("repro_clock: F8 and ch11 notes go out, the frames run, no core-1 select at state 7",
          r.returncode == 0 and "core-1 selects at state 7 = 0" in rules and "frames stopped = 0" in rules,
          r.stdout[-400:])


# ---- steps 1 and 3 ---------------------------------------------------------------------

def step1_3(image, elf):
    print("== step 1: one CUBE track (T1, core 1) beside a FLEX track ==", flush=True)
    p = boot(image, elf)
    try:
        p.run(1500)
        p.press("NO")
        p.run(300)
        check("boot: no source engine wanted or loaded, no loader error",
              p.long("dl_source_want") == 0 and p.long("dl_source_loaded") == 0 and p.long("dl_errors") == 0)
        p.press("T1")
        p.press("FUNC", "SRC")
        p.run(300)
        for _ in range(6):
            p.press("UP")
        for _ in range(5):
            p.press("DOWN")
        p.shot(SHOTS / "01_src_setup_cube_row.png")
        p.press("YES")
        p.run(400)
        raw = p.part_bytes()
        check("YES on CUBE: T1 is FLEX + CU\\x01 and holds CUBE's defaults",
              signed(raw, 0) and cube_bytes(raw, 0) == DEFAULTS, f"{cube_bytes(raw, 0)}")
        check("T2..T8 untouched (FLEX, no signature, FLEX's bytes)",
              not any(signed(raw, t) for t in range(1, 8)) and raw[PB + 30 + FX:PB + 30 + FX + 6] == bytes((64, 0, 0, 127, 0, 79)),
              f"{list(raw[PB + 30 + FX:PB + 30 + FX + 6])}")
        p.shot(SHOTS / "02_setup_page_defaults.png")
        p.press("NO")
        p.run(1500)
        check("the engine uploaded and bound on core 1 only (T1's core), no error",
              p.long("dl_source_loaded") == 2 and p.long("dl_source_failures", 2) == [0, 0] and p.long("dl_errors") == 0,
              f"loaded {p.long('dl_source_loaded')} failures {p.long('dl_source_failures', 2)}")
        proc1, proc0 = p.dsp(1, "X", 0x254, 1)[0], p.dsp(0, "X", 0x254, 1)[0]
        pool = p.long("dl_pool_base", 2)
        words = p.long("dl_pool_words", 2)
        res = p.long("dl_source_reserve")
        want = pool[1] + words[1] - res + 1
        check(f"core 1's id $1f proc is the engine at the arena's top (P:{want:05x}); core 0's is still the null stub",
              proc1 == want and proc0 == 0x7C9, f"core1 {proc1:05x} core0 {proc0:05x}")
        pkg = cube_pkg.package()
        base = want - 1
        got = p.dsp(1, "P", base, len(pkg["words"]))
        wantw = [(w + base) & 0xFFFFFF if k in pkg["relocations"] else w for k, w in enumerate(pkg["words"])]
        check(f"core 1's P:{base:05x}.. holds the relocated package word for word ({len(wantw)} words)", got == wantw)
        p.press("SRC")
        p.run(300)
        p.shot(SHOTS / "03_src_page_defaults.png")
        trigs(p, ("T1", "T2"), (1, 5, 9, 13))
        fr = stems(p, 3000)
        t1, t2 = [f[8] for f in fr], [f[10] for f in fr]
        hz = pitch(t1)
        check(f"T1 sounds on its stem (peak {max(map(abs, t1))}) and on MAIN", max(map(abs, t1)) > 1000 and
              max(abs(f[2]) for f in fr) > 1000)
        check(f"T1 at PTCH 64 (Z1 X1 Y1: a sine) plays C4: {hz:.1f} Hz (261.6)", abs(hz - 261.6) < 3)
        check("no lost frame inside the note (longest run of zero samples < 16)", gap_after_onset(t1) < 16,
              f"{gap_after_onset(t1)}")
        check("T2 (FLEX, no sample) stays silent beside it", max(map(abs, t2)) == 0)
        wav(AUDIO / "port_t1_c4_sine.wav", t1)
        # a morph and a detuned B
        p.press("T1")
        turn(p, "B", 0, "X", 100)
        turn(p, "C", 0, "Y", 40)
        turn(p, "D", 0, "Z", 30)
        turn(p, "E", 0, "FM", 30)
        p.shot(SHOTS / "04_src_page_morphed.png")
        fr = stems(p, 3000)
        t1b = [f[8] for f in fr]
        check("X 100 Y 40 Z 30 FM 30: T1 still sounds and its waveform changed",
              max(map(abs, t1b)) > 1000 and t1b[3000:3400] != t1[3000:3400])
        wav(AUDIO / "port_t1_morph_fm.wav", t1b)
        check(f"record and chunk counters moved (render {p.long('cube_render_calls')}, chunks {p.long('cube_chunks')}, "
              f"commits {p.long('cube_commits')}, trigs {p.long('cube_hits')})",
              p.long("cube_commits") >= 2 and p.long("cube_hits") >= 4)

        print("== step 3: the SRC ring on T1 (CUBE), T2 (FLEX) stock ==", flush=True)
        p.press("T1")
        press(p)
        seq = [("press", press, "SRC"), ("tap", tap, "SETUP"), ("tap", tap, "OSCB"), ("tap", tap, "SRC"),
               ("tap", tap, "SETUP"), ("press", press, "SRC"), ("tap", tap, "SETUP"), ("tap", tap, "OSCB"),
               ("press", press, "SRC"), ("tap", tap, "SETUP"), ("tap", tap, "OSCB")]
        seen = []
        ok = True
        for label, act, want_ in seq:
            act(p)
            got = where(p)
            seen.append(f"{label}:{got}")
            if got != want_:
                ok = False
                break
        check("ring: SRC, tap SETUP, tap OSC B, tap SRC, tap SETUP, press SRC, tap SETUP, tap OSC B, press SRC, "
              "tap SETUP, tap OSC B", ok, " ".join(seen))
        p.shot(SHOTS / "05_oscb_page_defaults.png")
        before = cube_bytes(p.part_bytes(), 0)
        ok_b = turn(p, "A", 0, "BX", 50) and turn(p, "C", 0, "BZ", 90) and turn(p, "D", 0, "LINK", 3) \
            and turn(p, "E", 0, "LAW", 1) and turn(p, "F", 0, "BPCH", 76)
        after = cube_bytes(p.part_bytes(), 0)
        check("OSC B knobs write BX 50, BZ 90, LINK OFF, LAW EXP, BPCH +12 into T1's bytes", ok_b, f"{after}")
        check("... and no SRC or SETUP byte moved", all(after[n] == before[n] for n in SRC_NAMES + SETUP_NAMES),
              f"{before} -> {after}")
        check("still OSC B after the knobs", where(p) == "OSCB", where(p))
        p.shot(SHOTS / "06_oscb_page_edited.png")
        sram = p.peek(0x100A4ECE + (p.peek(0x100B14CF, 1)[0] & 3) * 6322, 0x300)
        check("the SRAM shadow Part carries the same OSC B bytes", cube_bytes(sram, 0) == after,
              f"{cube_bytes(sram, 0)}")
        p.press("FUNC", "SRC")
        p.run(300)
        check("FUNC+SRC from OSC B opens SETUP", where(p) == "SETUP", where(p))
        p.shot(SHOTS / "07_setup_from_oscb.png")
        p.press("NO")
        p.run(300)
        press(p)
        check("a single SRC press after SETUP shows SRC", where(p) == "SRC", where(p))
        tap(p)
        tap(p)
        p.press("AMP")
        p.run(300)
        check("AMP from OSC B leaves the ring (AMP page), cube_view 0", where(p) == "page 2" and view(p) == 0,
              f"{where(p)} {view(p)}")
        press(p)
        check("SRC from AMP shows SRC", where(p) == "SRC", where(p))
        fr = stems(p, 2500)
        t1c = [f[8] for f in fr]
        check("LINK OFF (B a drone at +12 st, own cycle) and LAW EXP: T1 still sounds, differently",
              max(map(abs, t1c)) > 1000 and t1c[3000:3400] != t1b[3000:3400])
        wav(AUDIO / "port_t1_oscb_drone_exp.wav", t1c)
        # a stock FLEX track keeps stock's double tap
        p.press("T2")
        press(p)
        tap(p)
        a = where(p)
        tap(p)
        b = where(p)
        p.shot(SHOTS / "08_t2_flex_after_two_taps.png")
        check(f"T2 (FLEX): tap opens SETUP ({a}); the next tap is stock's ({b}), never OSC B; cube_view 0",
              a == "SETUP" and b != "OSCB" and view(p) == 0)
        p.press("NO")
        p.run(300)
        p.press("T1")
        p.run(300)
        check("back on T1: the SRC page (switching tracks leaves OSC B)", where(p) == "SRC", where(p))
    finally:
        p.quit()


# ---- step 2 -----------------------------------------------------------------------------

def settle(p):
    import verify as V
    V.settle_card(p, at_least_ms=20000)


def step2(image, elf):
    import verify as V
    print("== step 2: pages, Part bytes, SAVE / RELOAD per track ==", flush=True)
    p = boot(image, elf, writable=True)
    try:
        p.run(1000)
        p.press("NO")
        V.project_menu(p, 6)                # a new set and an empty project (the Turing gate's walk)
        p.press("YES")
        p.run(1000)
        for _ in range(5):
            p.press("YES")
            p.run(2500)
        V.settle_card(p, at_least_ms=25000)
        p.press("NO")
        machine(p, "T1", 5)
        machine(p, "T5", 5)
        raw = p.part_bytes()
        check("new project: CUBE on T1 and T5 (one per core), both with CUBE's defaults",
              signed(raw, 0) and signed(raw, 4) and cube_bytes(raw, 0) == DEFAULTS and cube_bytes(raw, 4) == DEFAULTS)
        want = {0: dict(PTCH=70, X=33, Z=99, MIX=20, FINE=80, OCT=3, UNI=105, MORPH=5, BX=11, LINK=1, BPCH=52),
                1: None,
                4: dict(PTCH=58, Y=77, FM=60, FINE=50, TONE=2, SYNC=2, BY=66, BZ=7, LAW=1)}
        enc = {n: "ABCDEF"[i % 6] for i, n in enumerate(SRC_NAMES + SETUP_NAMES + OSCB_NAMES)}
        oks = []
        for t in (0, 4):
            p.press(f"T{t + 1}")
            press(p)
            for n, v in want[t].items():
                if n in SRC_NAMES:
                    oks.append((t, n, turn(p, enc[n], t, n, v)))
            p.press("FUNC", "SRC")
            p.run(300)
            for n, v in want[t].items():
                if n in SETUP_NAMES:
                    oks.append((t, n, turn(p, enc[n], t, n, v)))
            if t == 0:
                p.shot(SHOTS / "09_setup_page_edited.png")
            p.press("NO")
            p.run(300)
            press(p)
            tap(p)
            tap(p)
            for n, v in want[t].items():
                if n in OSCB_NAMES:
                    oks.append((t, n, turn(p, enc[n], t, n, v)))
        bad = [(t, n) for t, n, ok in oks if not ok]
        check("SRC, SETUP and OSC B knobs set each byte on its own track", not bad, f"{bad}")
        raw = p.part_bytes()
        saved = {t: cube_bytes(raw, t) for t in (0, 4)}
        check("T1 and T5 hold different patches", saved[0] != saved[4])
        V.project_menu(p, 1)                # SAVE
        p.press("YES")
        V.settle_card(p, at_least_ms=20000)
        p.press("NO")
        for t in (0, 4):                    # change every set byte
            p.press(f"T{t + 1}")
            press(p)
            turn(p, "B", t, "X", 5)
            p.press("FUNC", "SRC")
            p.run(300)
            turn(p, "A", t, "FINE", 64)
            p.press("NO")
            p.run(300)
            press(p)
            tap(p)
            tap(p)
            turn(p, "A", t, "BX", 120)
        raw = p.part_bytes()
        check("after SAVE the bytes were changed", cube_bytes(raw, 0) != saved[0] and cube_bytes(raw, 4) != saved[4])
        V.project_menu(p, 2)                # RELOAD
        p.press("YES")
        V.settle_card(p, at_least_ms=25000)
        p.press("NO")
        raw = p.part_bytes()
        check("RELOAD brings back T1's and T5's own bytes, signatures included",
              all(cube_bytes(raw, t) == saved[t] and signed(raw, t) for t in (0, 4)),
              f"{ {t: cube_bytes(raw, t) for t in (0, 4)} }")
        check("T2..T4, T6..T8 are still FLEX", not any(signed(raw, t) for t in (1, 2, 3, 5, 6, 7)))
        p.run(1500)
        check("after RELOAD the engines are on both cores", p.long("dl_source_loaded") == 3,
              f"{p.long('dl_source_loaded')}")
        machine(p, "T5", 1)                 # FLEX
        raw = p.part_bytes()
        check("FLEX on T5: signature gone, FLEX's playback and SETUP defaults back, NEIGHBOR bytes zero",
              not signed(raw, 4) and raw[PB + 120 + FX:PB + 120 + FX + 6] == bytes((64, 0, 0, 127, 0, 79))
              and raw[SU + 120 + FX:SU + 120 + FX + 6] == bytes((1, 0, 0, 0, 1, 64))
              and raw[PB + 120 + NB:PB + 120 + NB + 6] == bytes(6) and raw[SU + 120 + NB:SU + 120 + NB + 6] == bytes(6),
              f"{list(raw[PB + 120 + FX:PB + 120 + FX + 6])} {list(raw[SU + 120 + FX:SU + 120 + FX + 6])}")
        check("T1 kept its patch", cube_bytes(raw, 0) == saved[0])
    finally:
        p.quit()
    files = p.card_files()
    banks = {k: v for k, v in files.items() if k.lower().endswith("bank01.work")}
    check(f"the saved bank file is on the card ({', '.join(banks) or 'none'})", bool(banks))
    if banks:
        data = next(iter(banks.values()))
        sig = data.count(b"CU\x01")
        check(f"bank01.work carries the CU\\x01 signature ({sig} copies: T1 and T5 in the Part and its saved copy)",
              sig >= 2)


# ---- step 4 -----------------------------------------------------------------------------

def step4(image, elf):
    print("== step 4: eight CUBE tracks, both cores (the cycle price is step 4a, verify.py dsp) ==", flush=True)
    results = {}
    for core in (0, 1):
        p = boot(image, elf)
        try:
            p.run(1500)
            p.press("NO")
            p.run(300)
            for t in range(8):
                machine(p, f"T{t + 1}", 5)
            raw = p.part_bytes()
            if core == 0:
                check("all eight tracks are CUBE", all(signed(raw, t) for t in range(8)))
                # one note per track, a fifth apart, different cube positions
                for t in range(8):
                    p.press(f"T{t + 1}")
                    press(p)
                    turn(p, "A", t, "PTCH", 52 + 2 * t)
                    turn(p, "D", t, "Z", 16 * t)
                    turn(p, "B", t, "X", 10 * t)
            p.run(1500)
            check(f"boot {core}: the engine is on both cores, no failure",
                  p.long("dl_source_loaded") == 3 and p.long("dl_source_failures", 2) == [0, 0])
            trigs(p, [f"T{t + 1}" for t in range(8)], (1, 5, 9, 13))
            p.cmd(f"watch {TICK_ISR:#x}")
            p.cmd("hits", b"hits")
            fr = stems(p, 3000)
            hits = len(p.cmd("hits", b"hits").split()[2:])
            p.cmd("watch off")
            peaks = [max(abs(f[8 + 2 * t]) for f in fr) for t in range(8)]
            check(f"boot {core}: every stem sounds {peaks}", all(v > 500 for v in peaks))
            check(f"boot {core}: the sequencer runs: {hits} tick ISRs in 3 s of PLAY (stock-like rate ~215/s)",
                  hits > 500)
            if core == 0:
                wav(AUDIO / "port_all8_main.wav", [v for f in fr for v in f[2:4]], ch=2)
                for t in (0, 4):
                    wav(AUDIO / f"port_all8_t{t + 1}.wav", [f[8 + 2 * t] for f in fr])
                p.press("T1")
                p.run(300)
                p.shot(SHOTS / "10_all8_src_t1.png")
        finally:
            p.quit()
    return results


def main(image, chk, failures):
    global check
    check = chk
    elf = ROOT / "out/platform/runtime/runtime.elf"
    SHOTS.mkdir(parents=True, exist_ok=True)
    steps = sys.argv[3].split(",") if len(sys.argv) > 3 else ["0", "1", "2", "4"]
    if "0" in steps:
        step0(image)
    if "1" in steps or "3" in steps:
        step1_3(image, elf)
    if "2" in steps:
        step2(image, elf)
    if "4" in steps:
        step4(image, elf)
