#!/usr/bin/env python3
"""Turing machine under the ColdFire port: drive the panel, read MIDI OUT.

    modules/turing-machine/verify.py [IMAGE]    from an octabam tree; default out/mainos_bus.bin
                                                (make bus REMIX=<a remix with TURING MACHINE>)

Four boots under the ColdFire port, each making its fixture through the
emulated panel on an empty scratch card. MIDI OUT is read as the bytes the
firmware queues for UART0: a write watch on the transmit ring that
0x40010bc8 fills (its pointer at 0x400b966c), parsed with running status.

  1. Fixed test seed. MIDI track 1 on channel 1 with a trig on every step
     and NOT2 set, track 2 on channel 2 with a trig on every step. Every MODE
     OFF plays NOTE; then every Turing note is compared with a model of the
     engine (Model below): LOCK 127 at LENGTH 16 and 5, LOCK 64 and LOCK 0
     after a STOP and PLAY. A LOCK change while playing freezes the phrase,
     NOT2 keeps its interval and every note-on is released.
  2-3. No test seed, PLAY 500 ms and 2,700 ms after the fixture: the two
     first phrases differ, and neither is the fixed seed's.
  4. A writable card: a new project starts every track OFF; SAVE writes
     "#TURING_T1=1,127,8" after PATTERN_CHANGE_AUTO_SILENCE_TRACKS; RELOAD
     brings it back after the track was set OFF.
Not hardware. The image must carry the module (the detour at 0x4009fb2e).
"""
import functools
import os
import pathlib
import selectors
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
EMU = ROOT / "out/emu/ot_emu"
RING_PTR = 0x400b966c
HOOK_SITE = 0x4009fb2e
SETTINGS = 0x100ffe00
TEST_SEED = 0x100ffe20
NOTE_C3 = 48
SPAN = 24
LENGTH = 16
KEYS = {"FUNC": 0x2d, "SRC": 0x22, "YES": 0x31, "NO": 0x32, "UP": 0x33, "DOWN": 0x20,
        "LEFT": 0x34, "RIGHT": 0x21, "MENU": 0x1c, "MIDI": 0x35, "REC": 0x29,
        "PLAY": 0x28, "STOP": 0x27,
        **{f"TRIG{i + 1}": i for i in range(16)}, **{f"T{i + 1}": 0x10 + i for i in range(8)}}
ENCODERS = {name: i for i, name in enumerate("ABCDEF")} | {"LEVEL": 6}
failures = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


class Port:
    """ot_emu --interactive on a scratch card (tools/emu/ot_emu/main.cpp)."""

    def __init__(self, image, work, writable=False):
        sys.path.insert(0, str(ROOT / "tools/emu"))
        import emu_card
        work.mkdir()
        card = self.card = work / "card.img"
        (work / "tree").mkdir()
        card.write_bytes(emu_card.build_image(str(work / "tree"), 32))
        cmd = [str(EMU), "--image", str(image), "--card", str(card), "--dsp", "--frame", "--ms", "3000",
               "--interactive", "--main-level", "off", "--rtc", "off", "--mkii"] + (["--card-rw"] if writable else [])
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, cwd=work)
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.p.stdout, selectors.EVENT_READ)
        self.pending, self.rows = b"", [0] * 8
        self.reply((b"ready ",), 900)

    def reply(self, prefixes, timeout=600):
        deadline = time.monotonic() + timeout
        while True:
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                if line.startswith(prefixes):
                    if line.startswith(b"err"):
                        raise SystemExit(f"verify_turing: the port refused a command: {line.decode()}")
                    return line.decode()
            if time.monotonic() > deadline or self.p.poll() is not None:
                raise SystemExit("verify_turing: the port stopped answering")
            if self.sel.select(timeout=1):
                chunk = os.read(self.p.stdout.fileno(), 1 << 16)
                if not chunk:
                    raise SystemExit("verify_turing: the port exited")
                self.pending += chunk

    def cmd(self, line, prefix=b"ok"):
        self.p.stdin.write((line + "\n").encode())
        self.p.stdin.flush()
        return self.reply((prefix, b"err"))

    def run(self, ms):
        self.cmd(f"run {ms}")

    def key(self, name, down):
        code = KEYS[name]
        if down:
            self.rows[code >> 3] |= 1 << (code & 7)
        else:
            self.rows[code >> 3] &= ~(1 << (code & 7))
        self.cmd(f"key {0x20 | (code >> 3)} {self.rows[code >> 3]}")
        self.run(120)

    def press(self, *names):
        for n in names:
            self.key(n, True)
        for n in reversed(names):
            self.key(n, False)

    def enc(self, name, delta):
        self.cmd(f"knob {0x30 | ENCODERS[name]} {delta & 255}")
        self.run(200)

    def peek(self, addr, length):
        return bytes.fromhex(self.cmd(f"peek 0x{addr:08x} {length}", b"peek").split(" ", 1)[1])

    def writes(self):
        recs = self.cmd("writes", b"writes").split()[2:]
        return bytes(int(r.split(":")[3], 16) & 0xff for r in recs)

    def card_files(self):
        import emu_card
        return emu_card.extract_image(self.card.read_bytes())

    def quit(self):
        try:
            self.cmd("quit")
        finally:
            self.p.wait(timeout=60)


def notes(data):
    """MIDI OUT bytes -> [(kind, channel, note)], running status as on the wire."""
    out, status, buf = [], None, []
    for b in data:
        if b >= 0xf8:
            continue
        if b >= 0x80:
            status, buf = b, []
            continue
        if status is None:
            continue
        buf.append(b)
        if len(buf) == (1 if status & 0xf0 in (0xc0, 0xd0) else 2):
            if status & 0xf0 in (0x80, 0x90):
                out.append(("on" if status & 0xf0 == 0x90 and buf[1] else "off", status & 15, buf[0]))
            buf = []
    return out


def track_ons(events, channel):
    return [n for kind, ch, n in events if kind == "on" and ch == channel]


def chords(events, channel):
    """Note-ons of one channel grouped by trig: NOTE first, then NOT2."""
    ons = track_ons(events, channel)
    return [tuple(ons[i:i + 2]) for i in range(0, len(ons) - 1, 2)]


# ---- the engine, modelled (turing.c) ----------------------------------------

M32 = 0xffffffff


def mix(x):
    x ^= x >> 16; x = (x * 0x85ebca6b) & M32
    x ^= x >> 13; x = (x * 0xc2b2ae35) & M32
    return x ^ (x >> 16)


class Model:
    """One track's register, from the boot seed, exactly as tm_step runs it."""

    def __init__(self, seed, track):
        self.rng = mix((seed + 0x9e3779b9 * (track + 1)) & M32) or 0x6d2b79f5
        self.bits = self.random() & 0xffff

    def random(self):
        x = self.rng
        x ^= (x << 13) & M32; x ^= x >> 17; x ^= (x << 5) & M32
        self.rng = x
        return x

    def offset(self, lock, length):
        out = (self.bits >> (length - 1)) & 1
        if (self.random() & 0xff) < (127 - lock) * 256 // 127:
            out ^= 1
        self.bits = ((self.bits << 1) | out) & 0xffff
        return (self.bits & 0xff) * SPAN // 255


def periodic(seq, period, settle=LENGTH):
    tail = seq[settle:]
    return len(tail) > period and all(tail[i] == tail[i + period] for i in range(len(tail) - period))


# ---- the panel ----------------------------------------------------------------

def open_page(port):
    """PROJ > CONTROL > MIDI SEQUENCER from any menu state, cursor on row 0."""
    port.press("MENU")
    port.run(400)
    port.press("LEFT")
    for key, times in (("UP", 3), ("DOWN", 2)):
        for _ in range(times):
            port.press(key)
    port.press("RIGHT")
    for key, times in (("UP", 5), ("DOWN", 3)):
        for _ in range(times):
            port.press(key)
    port.press("YES")
    port.run(300)
    for _ in range(5):
        port.press("UP")


def close_page(port):
    port.press("NO")            # the page -> the CONTROL list
    port.press("NO")            # the list -> closed


def set_track(port, track, on, lock, length):
    """With the page open at row 0: TURING TRACK, MODE, LOCK, LENGTH for one track."""
    for row, low, value in ((1, -8, track - 1), (2, -1, int(on)), (3, -127, lock), (4, -16, length - 2)):
        port.press("DOWN")
        port.enc("LEVEL", low)
        if value:
            port.enc("LEVEL", value)
    for _ in range(4):
        port.press("UP")


def settings(port):
    raw = port.peek(SETTINGS, 32)
    return {"enabled": raw[3], "lock": list(raw[4:12]), "length": list(raw[12:20]),
            "valid": raw[:3] == b"TM\x01" and raw[31] == functools.reduce(lambda a, b: a ^ b, raw[:31], 0x5a)}


def fixture(port, tracks):
    """MIDI tracks on their own channels with trigs; T1 gets NOT2."""
    port.run(1000)
    port.press("NO")
    port.press("MIDI")
    for track, channel, steps in tracks:
        port.press(track)
        port.press("FUNC", "SRC")
        port.run(300)
        for _ in range(channel):
            port.enc("A", 4)
        port.press("YES")
        port.press("SRC")
        port.press("REC")
        for step in steps:
            port.press(f"TRIG{step}")
        port.press("REC")
    port.press("T1")
    port.enc("D", 7)
    chan = port.peek(0x46c76de0, 69 * len(tracks))
    check("fixture: each track on its own channel",
          all(chan[68 * i] == channel for i, (_t, channel, _s) in enumerate(tracks)), chan[::68].hex())


def play(port, ms):
    port.press("PLAY")
    port.run(ms)
    port.press("STOP")
    port.run(400)
    return notes(port.writes())


def watch_midi_out(port):
    ring = int.from_bytes(port.peek(RING_PTR, 4), "big")
    port.cmd(f"watchmem 0x{ring:08x} 4096")


def released(events):
    sounding, orphans = set(), 0
    for kind, ch, n in events:
        if kind == "on":
            sounding.add((ch, n))
        elif (ch, n) in sounding:
            sounding.discard((ch, n))
        else:
            orphans += 1
    return sounding, orphans


# ---- the runs -----------------------------------------------------------------

def fixed_seed_run(image, work):
    """One boot with the test seed: every note checked against the model."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, range(1, 17)), ("T2", 2, range(1, 17))))
        watch_midi_out(port)
        off = play(port, 2300)
        stock = chords(off, 0)
        interval = stock[0][1] - stock[0][0] if stock else None
        check("OFF: track 1 plays its NOTE, NOT2 a fixed interval above", len(stock) >= 16 and interval
              and all(c == (NOTE_C3, NOTE_C3 + interval) for c in stock), f"{stock[:6]}")
        check("OFF: track 2 plays its NOTE", set(track_ons(off, 1)) == {NOTE_C3}, f"{track_ons(off, 1)[:8]}")

        seed = 0x13572468
        port.cmd(f"poke 0x{TEST_SEED:08x} {(0x54534545).to_bytes(4, 'big').hex()}{seed.to_bytes(4, 'big').hex()}"
                 f"{(seed ^ M32).to_bytes(4, 'big').hex()}")
        models = {0: Model(seed, 0), 1: Model(seed, 1)}
        open_page(port)
        set_track(port, 1, True, 127, 16)
        set_track(port, 2, True, 127, 5)
        s = settings(port)
        check("rows: T1 ON 127/16 and T2 ON 127/5 in a valid record", s["valid"] and s["enabled"] == 3
              and s["lock"][:2] == [127, 127] and s["length"][:2] == [16, 5], f"{s}")
        close_page(port)

        def expect(events, settings_by_track):
            for ch, (lock, length) in settings_by_track.items():
                got = [c[0] for c in chords(events, 0)] if ch == 0 else track_ons(events, 1)
                want = [NOTE_C3 + models[ch].offset(lock, length) for _ in got]
                yield ch, got, want

        a = play(port, 4300)
        for ch, got, want in expect(a, {0: (127, 16), 1: (127, 5)}):
            name = ("track 1, LOCK 127 LENGTH 16", "track 2, LOCK 127 LENGTH 5")[ch]
            check(f"fixed seed, {name}: every note as the model predicts", len(got) >= 32 and got == want,
                  f"got {got}\nwant {want}")
            check(f"fixed seed, {name}: repeats every {(16, 5)[ch]} trigs", periodic(got, (16, 5)[ch]), f"{got}")
        check("NOT2 keeps the stock interval", all(c[1] - c[0] == interval for c in chords(a, 0)), f"{chords(a, 0)[:6]}")

        open_page(port)
        set_track(port, 1, True, 64, 16)
        set_track(port, 2, True, 0, 16)
        close_page(port)
        b = play(port, 4300)
        for ch, got, want in expect(b, {0: (64, 16), 1: (0, 16)}):
            name = ("track 1, LOCK 64 after STOP/PLAY", "track 2, LOCK 0 LENGTH 16")[ch]
            check(f"fixed seed, {name}: every note as the model predicts", len(got) >= 32 and got == want,
                  f"got {got}\nwant {want}")
        t1 = [c[0] for c in chords(b, 0)]
        check("LOCK 64: the phrase keeps changing", not periodic(t1, 16, 0), f"{t1}")
        check("every note inside NOTE..NOTE+24", all(NOTE_C3 <= n <= NOTE_C3 + SPAN
              for n in t1 + track_ons(a + b, 1)))

        port.press("PLAY")
        port.run(500)
        open_page(port)
        set_track(port, 1, True, 127, 16)
        close_page(port)
        port.run(5500)
        port.press("STOP")
        port.run(400)
        c = notes(port.writes())
        live = [x[0] for x in chords(c, 0)][-2 * LENGTH:]
        check("LOCK 127 set while playing: the phrase freezes", len(live) == 2 * LENGTH
              and live[:LENGTH] == live[LENGTH:], f"{live}")
        sounding, orphans = released(off + a + b + c)
        check("every note-on released; nothing sounds after STOP", not sounding and not orphans,
              f"sounding {sorted(sounding)}, orphan offs {orphans}")
        return [n for n in [x[0] for x in chords(a, 0)][:LENGTH]]
    finally:
        port.quit()


def timer_seed_run(image, work, wait_ms):
    """One boot without a test seed: PLAY after `wait_ms`, the first 16 notes of track 1."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, range(1, 17)),))
        port.cmd(f"poke 0x{SETTINGS:08x} " + settings_record({0: (True, 127, 16)}).hex())
        watch_midi_out(port)
        port.run(wait_ms)
        first = [x[0] for x in chords(play(port, 2300), 0)][:LENGTH]
        check(f"timer seed, PLAY after {wait_ms} ms: a full phrase inside the range", len(first) == LENGTH
              and all(NOTE_C3 <= n <= NOTE_C3 + SPAN for n in first), f"{first}")
        return first
    finally:
        port.quit()


def project_menu(port, downs):
    """PROJ > PROJECT list item `downs` rows below CHANGE (SAVE 1, RELOAD 2, the set's CHANGE 6)."""
    port.press("MENU")
    port.run(400)
    port.press("LEFT")
    for _ in range(3):
        port.press("UP")
    port.press("RIGHT")
    for key, times in (("UP", 16), ("DOWN", downs)):
        for _ in range(times):
            port.press(key)
    port.press("YES")
    port.run(1500)


def project_run(image, work):
    """One boot on a writable scratch card: new project, SAVE, RELOAD, the file."""
    port = Port(image, work, writable=True)
    try:
        port.run(1000)
        port.press("NO")
        open_page(port)
        set_track(port, 1, True, 127, 8)
        close_page(port)
        project_menu(port, 6)               # the set's CHANGE: "not within a project", YES
        port.press("YES")
        port.run(1000)
        for _ in range(5):                  # <CREATE NEW SET>, its name, the set, <CREATE EMPTY PROJECT>, its name
            port.press("YES")
            port.run(2500)
        port.run(25000)
        s = settings(port)
        check("new project: every track starts OFF", s["valid"] and s["enabled"] == 0
              and s["lock"] == [64] * 8 and s["length"] == [16] * 8, f"{s}")
        open_page(port)
        set_track(port, 1, True, 127, 8)
        close_page(port)
        project_menu(port, 1)               # SAVE
        port.press("YES")
        port.run(20000)
        open_page(port)
        set_track(port, 1, False, 64, 16)
        close_page(port)
        s = settings(port)
        check("after SAVE, T1 set back to OFF", s["valid"] and s["enabled"] == 0, f"{s}")
        project_menu(port, 2)               # RELOAD
        port.press("YES")
        port.run(25000)
        s = settings(port)
        check("RELOAD restores the saved T1 ON 127/8", s["valid"] and s["enabled"] == 1
              and s["lock"][0] == 127 and s["length"][0] == 8, f"{s}")
    finally:
        port.quit()
    files = port.card_files()
    work_files = {path: data.decode("latin1").splitlines() for path, data in files.items()
                  if path.lower().endswith("project.work")}
    lines = next(iter(work_files.values()), [])
    turing = [line for line in lines if line.startswith("#TURING")]
    check("project.work holds exactly #TURING_T1=1,127,8", turing == ["#TURING_T1=1,127,8"], f"{turing}")
    if turing:
        at = lines.index(turing[0])
        check("written after PATTERN_CHANGE_AUTO_SILENCE_TRACKS", lines[at - 1].startswith("PATTERN_CHANGE_AUTO_SILENCE_TRACKS="),
              f"{lines[at - 1]!r}")


def settings_record(tracks):
    raw = bytearray(32)
    raw[:3] = b"TM\x01"
    for t in range(8):
        on, lock, length = tracks.get(t, (False, 64, 16))
        raw[3] |= int(on) << t
        raw[4 + t], raw[12 + t] = lock, length
    raw[31] = functools.reduce(lambda a, b: a ^ b, raw[:31], 0x5a)
    return bytes(raw)


def main():
    image = (pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out/mainos_bus.bin").resolve()
    if not EMU.exists():
        print("  [SKIP] verify_turing: no ColdFire port (make emu-cf)")
        return
    raw = image.read_bytes()
    site = raw[HOOK_SITE - 0x40000400:HOOK_SITE - 0x40000400 + 2]
    if site != bytes.fromhex("4ef9"):
        raise SystemExit(f"verify_turing: {image} does not carry TURING MACHINE (no jmp at 0x{HOOK_SITE:08x})")
    phrases = []
    with tempfile.TemporaryDirectory(prefix="verify-turing.") as td:
        fixed = fixed_seed_run(image, pathlib.Path(td) / "fixed")
        for i, wait in enumerate((500, 2700)):
            phrases.append(timer_seed_run(image, pathlib.Path(td) / f"timer{i}", wait))
        project_run(image, pathlib.Path(td) / "project")
    check("timer seed: two boots, PLAY at different moments, different first phrases",
          phrases[0] != phrases[1], f"{phrases}")
    check("timer seed: neither boot plays the test seed's phrase", fixed not in phrases, f"{fixed} in {phrases}")
    if failures:
        raise SystemExit(f"verify_turing: {len(failures)} check(s) failed")
    print("verify_turing: all checks passed under the ColdFire port")


if __name__ == "__main__":
    main()
