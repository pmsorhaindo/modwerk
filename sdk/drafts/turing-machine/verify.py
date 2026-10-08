#!/usr/bin/env python3
"""Turing machine under the ColdFire port: drive the panel, read MIDI OUT.

    modules/turing-machine/verify.py [IMAGE]    from an octabam tree; default out/mainos_bus.bin
                                                (make bus REMIX=<a remix with TURING MACHINE>)

The fixture is made through the emulated panel on an empty scratch card, so
no project file is needed: MIDI track 1 on channel 1 with a trig on every
step and NOT2 set, MIDI track 2 on channel 2 with trigs on steps 1 and 9.
MIDI OUT is read as the bytes the firmware queues for UART0: a write watch
on the transmit ring that 0x40010bc8 fills (its pointer at 0x400b966c), in
order, parsed with running status.

Checks, all on one boot:
  1. TURING TRACK OFF: every note is the trig's NOTE (C3 = 48) on both tracks.
  2. T1, LOCK 127: track 1 repeats one 16-note phrase, inside NOTE..NOTE+24;
     track 2 still plays 48.
  3. LOCK 64, set from the menu while playing: the phrase changes.
  4. Throughout: NOT2 keeps the stock interval to NOTE; every note-on is
     released and nothing sounds after STOP.
Not hardware. The image must carry the module (the detour at 0x4009fb2e).
"""
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
NV = 0x100b14e8
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

    def __init__(self, image, work):
        sys.path.insert(0, str(ROOT / "tools/emu"))
        import emu_card
        card = work / "card.img"
        (work / "tree").mkdir()
        card.write_bytes(emu_card.build_image(str(work / "tree"), 32))
        cmd = [str(EMU), "--image", str(image), "--card", str(card), "--dsp", "--frame", "--ms", "3000",
               "--interactive", "--main-level", "off", "--rtc", "off", "--mkii"]
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


def menu_rows(port):
    port.press("MENU")
    port.run(400)
    port.press("DOWN")
    port.press("DOWN")
    port.press("RIGHT")
    port.press("DOWN")
    port.press("DOWN")
    port.press("DOWN")
    port.press("YES")
    port.run(300)


def main():
    image = (pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out/mainos_bus.bin").resolve()
    if not EMU.exists():
        print("  [SKIP] verify_turing: no ColdFire port (make emu-cf)")
        return
    raw = image.read_bytes()
    site = raw[HOOK_SITE - 0x40000400:HOOK_SITE - 0x40000400 + 2]
    if site != bytes.fromhex("4ef9"):
        raise SystemExit(f"verify_turing: {image} does not carry TURING MACHINE (no jmp at 0x{HOOK_SITE:08x})")
    with tempfile.TemporaryDirectory(prefix="verify-turing.") as td:
        port = Port(image, pathlib.Path(td))
        try:
            port.run(1000)
            port.press("NO")
            port.press("MIDI")
            for track, channel, steps in (("T1", 1, range(1, 17)), ("T2", 2, (1, 9))):
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
            chan = port.peek(0x46c76de0, 69)
            check("fixture: T1 on channel 1, T2 on channel 2", chan[0] == 1 and chan[68] == 2,
                  f"channel bytes {chan[0]}, {chan[68]}")
            ring = int.from_bytes(port.peek(RING_PTR, 4), "big")
            port.cmd(f"watchmem 0x{ring:08x} 4096")

            # 1. OFF
            port.press("PLAY")
            port.run(2300)
            port.press("STOP")
            port.run(400)
            off = notes(port.writes())
            stock = chords(off, 0)
            interval = stock[0][1] - stock[0][0] if stock else None
            check("OFF: track 1 plays its NOTE", len(stock) >= 16 and all(c[0] == NOTE_C3 for c in stock),
                  f"{stock[:8]}")
            check("OFF: NOT2 sounds a fixed interval above NOTE", interval not in (None, 0)
                  and all(c[1] - c[0] == interval for c in stock), f"{stock[:8]}")
            check("OFF: track 2 plays its NOTE", track_ons(off, 1) and set(track_ons(off, 1)) == {NOTE_C3},
                  f"{track_ons(off, 1)}")

            # 2. T1, LOCK 127
            menu_rows(port)
            port.press("DOWN")
            port.press("RIGHT")
            port.press("DOWN")
            port.enc("LEVEL", 127)
            nv = port.peek(NV, 3)
            check("rows: TURING TRACK T1, LOCK 127 in battery RAM", nv == bytes((1, 127, 1 ^ 127 ^ 0x5a)), nv.hex())
            port.press("NO")            # the page -> the CONTROL list
            port.press("NO")            # the list -> closed
            port.press("PLAY")
            port.run(4300)
            port.press("STOP")
            port.run(400)
            locked = notes(port.writes())
            held = chords(locked, 0)
            roots = [c[0] for c in held]
            check("LOCK 127: at least two full loops", len(roots) >= 2 * LENGTH, f"{len(roots)} trigs")
            check("LOCK 127: the 16-note phrase repeats exactly",
                  all(roots[i] == roots[i + LENGTH] for i in range(len(roots) - LENGTH)), f"{roots}")
            check("LOCK 127: the phrase moves", len(set(roots)) > 1, f"{roots}")
            check("LOCK 127: every note inside NOTE..NOTE+24",
                  all(NOTE_C3 <= n <= NOTE_C3 + SPAN for n in roots), f"{roots}")
            check("LOCK 127: NOT2 keeps the stock interval", all(c[1] - c[0] == interval for c in held), f"{held[:8]}")
            check("LOCK 127: track 2 untouched", set(track_ons(locked, 1)) == {NOTE_C3}, f"{track_ons(locked, 1)}")

            # 3. LOCK 64 from the menu, while playing
            port.press("PLAY")
            port.run(500)
            port.press("MENU")
            port.run(400)
            port.press("YES")
            port.run(300)
            port.press("DOWN")
            port.press("DOWN")
            port.enc("LEVEL", -63)
            port.press("NO")
            port.press("NO")
            check("rows: LOCK 64 set while playing", port.peek(NV, 3) == bytes((1, 64, 1 ^ 64 ^ 0x5a)))
            port.run(4300)
            port.press("STOP")
            port.run(400)
            free = notes(port.writes())
            moving = [c[0] for c in chords(free, 0)][-2 * LENGTH:]
            phrase = roots[:LENGTH]
            check("LOCK 64: the phrase changes", len(moving) == 2 * LENGTH and moving[:LENGTH] != moving[LENGTH:]
                  and moving[LENGTH:] != phrase, f"{moving}")
            check("LOCK 64: every note inside NOTE..NOTE+24",
                  all(NOTE_C3 <= n <= NOTE_C3 + SPAN for n in moving), f"{moving}")

            # 4. Note-offs across the whole run
            sounding, orphans = set(), 0
            for kind, ch, n in off + locked + free:
                if kind == "on":
                    sounding.add((ch, n))
                elif (ch, n) in sounding:
                    sounding.discard((ch, n))
                else:
                    orphans += 1
            check("every note-on released; nothing sounds after STOP", not sounding and not orphans,
                  f"sounding {sorted(sounding)}, orphan offs {orphans}")
        finally:
            port.quit()
    if failures:
        raise SystemExit(f"verify_turing: {len(failures)} check(s) failed")
    print("verify_turing: all checks passed under the ColdFire port")


if __name__ == "__main__":
    main()
