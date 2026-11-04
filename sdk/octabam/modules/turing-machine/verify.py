#!/usr/bin/env python3
"""Turing machine under the ColdFire port: drive the panel, read MIDI OUT.

    modules/turing-machine/verify.py [IMAGE]    from an octabam tree; default out/mainos_bus.bin
                                                (make bus REMIX=<a remix with TURING MACHINE>)

REPLACE mode (OCTABAM8; OCTABAM9: locks, mute, NEI, range, ARP, LFO,
external clock, per-pattern settings): on a MIDI track whose MODE is ON
every sequencer step sends one note from the register, NOTE-12..NOTE+12,
with the step's locks, and the track's own trigs send no notes. Fourteen boots under the ColdFire port, each making its fixture through the
emulated panel on an empty scratch card. MIDI OUT is read as the bytes the
firmware queues for UART0 (a write watch on the transmit ring that
0x40010bc8 fills, its pointer at 0x400b966c, parsed with running status,
each byte with its sample time) or as UART0's wire bytes (tx0). Every track
setting is made on the TURING page (AMP, then a double tap to ARP SETUP and
another to TURING).

  1. Fixed test seed; T1 (channel 1, NOT2 set) EMPTY, T2 (channel 2) a trig
     on every step and MODE OFF, the stock reference. T1 OFF is silent. T1
     ON: one note per step, at T2's sample times, 16 a bar at 1x, at 2x and
     at 1/2x (PATTERN SCALE); each note as the model of the engine predicts,
     LOCK 127 repeating every LENGTH steps (16 and 5); T2's velocity and
     length; no NOT2. Trigs placed on T1 afterwards send nothing of their
     own. Mute silences T1; the register keeps clocking while
     muted, so after unmute T1 plays the note of the step it is on; a STOP while
     muted loses no step. MODE OFF while playing
     gives the trigs' own NOTE+NOT2 chords and nothing else, ON again one
     note a step; OFF or ON switched while stopped holds from the first
     step of the next PLAY. A long LEN: STOP releases every note.
  2-3. No test seed, PLAY 500 ms and 2,700 ms after the fixture (T1 empty):
     the two first phrases differ, and neither is the fixed seed's.
  4. A writable card: a new project starts every track OFF and TURING FIRST
     OFF; SAVE writes "#TURING_T1=1,127,8" (set on the TURING page) and
     "#TURING_FIRST=1" (the MIDI SEQUENCER row) after
     PATTERN_CHANGE_AUTO_SILENCE_TRACKS; RELOAD brings both back after they
     were set OFF, and AMP then shows TURING first.
  5. AMP's ring of pages, fixed test seed. TURING FIRST OFF: AMP shows ARP, a
     double tap ARP SETUP, another TURING, another ARP (the wrap); a press
     from TURING or ARP SETUP shows ARP; FUNC+AMP opens ARP SETUP from ARP
     and TURING. Knob A is each track's own switch, B and C its LOCK and
     LENGTH: T1 and (after T2 is selected, the page stays) T2, nothing goes
     out on MIDI OUT and no ARP byte changes; the stock widgets draw the
     page's values; every note against the model, and T2 switched OFF on
     knob A plays its NOTE while T1 goes on. TURING FIRST ON (the row):
     AMP shows TURING, a double tap ARP, another ARP SETUP, another TURING;
     a press from ARP or ARP SETUP shows TURING; FUNC+AMP opens ARP SETUP;
     the MIDI/audio toggle comes back to TURING.
  6-7. The same panel script on stock 1.40C (out/raw/section_3_MAIN_OS.bin)
     and on the image: with every MODE OFF, T1 and T2 with trigs give the
     same MIDI OUT wire bytes; then with CLOCK SEND and TRANSPORT SEND on and
     T1 ON (the image) a 2.3 s PLAY gives stock's F8 count, FA and FC, and
     stock's number of sequencer tick ISRs.
  8. Locks (panel, grid recording): VEL, LEN, NOTE (the centre), CC1, a lock
     trig and VEL 0 on T1, against stock (T1 OFF); muted ON as muted stock.
  9. NEI on T2 (conditions poked): follows T1's trigs OFF, true every step ON.
 10. Range: poked registers at NOTE C3, 6 and 121, all within NOTE+-12 (and a
     4,000-register model check).
 11. ARP (UP, 2 octaves) and KEY C MAJ: T1 as a stock T3 whose NOTE locks are
     T1's phrase, note for note and time for time.
 12. LFO 1 on NOTE (DEP 24): T1's offset from the register equals a stock T2's.
 13. External MIDI clock (FA, F8 at 125 BPM, FC on MIDI IN): 1x, 2x, 1/2x.
 14. Patterns: A01 T1 ON, A02 T1 OFF with trigs; A01 -> A02 -> A01 -> A02.
Not hardware. The image must carry the module (the detour at 0x4009fb2e).
"""
import collections
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
STOCK = ROOT / "out/raw/section_3_MAIN_OS.bin"
RING_PTR = 0x400b966c
HOOK_SITE = 0x4009fa2a
SETTINGS = 0x100ffe00
TEST_SEED = 0x100ffe20
RANDOM = 0x100ffe40              # each track's flip random state (turing.h TM_NV_RANDOM)
CELLS = 0x100f9000               # per pattern: 16 banks x 16 patterns x 8 tracks x 12 bytes (turing.h TmCell)
BANK0 = 0x400e21e0               # bank 1's pattern data (turing.h TM_SEQ_BANKS)
POPUP = 0x4005a2b8               # popup(text, ticks), turing.h TM_POPUP
NOTE_C3 = 48
SPAN = 24
CENTRE = 12
LENGTH = 16
M64 = (1 << 64) - 1
STEP = 44100 * 60 / 120 / 4      # samples a 16th at the default 120 BPM, scale 1x
SAME = 64                        # samples: two notes this close sit on one step
TICK_ISR = 0x400a1e0c
KEYS = {"FUNC": 0x2d, "SRC": 0x22, "YES": 0x31, "NO": 0x32, "UP": 0x33, "DOWN": 0x20,
        "LEFT": 0x34, "RIGHT": 0x21, "MENU": 0x1c, "MIDI": 0x35, "REC": 0x29,
        "PLAY": 0x28, "STOP": 0x27, "AMP": 0x23, "PAGE": 0x1b, "LFO": 0x24, "FX1": 0x25,
        "PATTERN": 0x2e,
        **{f"TRIG{i + 1}": i for i in range(16)}, **{f"T{i + 1}": 0x10 + i for i in range(8)}}
ENCODERS = {name: i for i, name in enumerate("ABCDEF")} | {"LEVEL": 6}
failures = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


class Port:
    """ot_emu --interactive on a scratch card (tools/emu/ot_emu/main.cpp)."""

    def __init__(self, image, work, writable=False, tree=None, extra=()):
        sys.path.insert(0, str(ROOT / "tools/emu"))
        import emu_card
        work.mkdir()
        card = self.card = work / "card.img"
        if tree is None:
            tree = work / "tree"
            tree.mkdir()
        card.write_bytes(emu_card.build_image(str(tree), 32))
        cmd = [str(EMU), "--image", str(image), "--card", str(card), "--dsp", "--frame", "--ms", "3000",
               "--interactive", "--main-level", "off", "--rtc", "off", "--mkii"] + (["--card-rw"] if writable else []) + list(extra)
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

    def key(self, name, down, ms=120):
        code = KEYS[name]
        if down:
            self.rows[code >> 3] |= 1 << (code & 7)
        else:
            self.rows[code >> 3] &= ~(1 << (code & 7))
        self.cmd(f"key {0x20 | (code >> 3)} {self.rows[code >> 3]}")
        self.run(ms)

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
        return bytes(b for _t, b in self.writes_timed())

    def writes_timed(self):
        """[(sample, byte)] queued for MIDI OUT since the last call."""
        recs = self.cmd("writes", b"writes").split()[2:]
        return [(float(r.split(":")[0]), int(r.split(":")[3], 16) & 0xff) for r in recs]

    def wire(self):
        """UART0's wire bytes since the last call."""
        line = self.cmd("tx0", b"tx0")
        return bytes.fromhex(line.split(" ", 1)[1]) if " " in line else b""

    def sample(self):
        return float(self.cmd("status", b"status").split("sample=")[1].split()[0])

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


def timed_notes(data):
    """[(sample, byte)] -> [(sample, kind, channel, note, velocity)], running status."""
    out, status, buf = [], None, []
    for t, b in data:
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
                out.append((t, "on" if status & 0xf0 == 0x90 and buf[1] else "off", status & 15, buf[0], buf[1]))
            buf = []
    return out


def untimed(events):
    return [(kind, ch, n) for _t, kind, ch, n, _v in events]


def onsets(events, channel):
    """[(sample, note, velocity)] of one channel's note-ons."""
    return [(t, n, v) for t, kind, ch, n, v in events if kind == "on" and ch == channel]


def steps(events, channel):
    """One channel's note-ons grouped by step: [(sample, (notes...))]."""
    out = []
    for t, n, _v in onsets(events, channel):
        if out and t - out[-1][0] <= SAME:
            out[-1] = (out[-1][0], out[-1][1] + (n,))
        else:
            out.append((t, (n,)))
    return out


def durations(events, channel):
    """Note-on to its note-off, in samples, per note-on of one channel."""
    held, out = {}, []
    for t, kind, ch, n, _v in events:
        if ch != channel:
            continue
        if kind == "on":
            held[n] = t
        elif n in held:
            out.append(t - held.pop(n))
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


NOTE_LOOP_MAX = 7                # LEN 2..7: a loop of LEN whole notes (turing.h TM_NOTE_LOOP_MAX)
NOTE_KEYS = (0x00, 0xb5, 0x6a, 0xd3, 0x2c, 0x99, 0x47)   # turing.c tm_keys


def flip_chance(lock, length):
    """tm_flip_chance: the chance, in 65536ths, that what comes round at the loop point changes (the README's
    table). LEN 8..64 a bit (random a half, loose four bits a pass); LEN 2..7 a note (random every note, loose two)."""
    notes = length <= NOTE_LOOP_MAX
    slip = 65536 // length
    rnd = 65536 if notes else 32768
    loose = min(slip * 2, 40960) if notes else min(slip * 4, 24576)
    if lock >= 96:
        return 0
    if lock >= 64:
        return rnd // 32 * (96 - lock)
    if lock >= 25:
        return slip + (rnd - slip) * (lock - 25) // 39
    return loose - (loose - slip) * lock // 25


def advance(bits, length, flip=0):
    """tm_advance: one clock of the loop. LEN 8..64 a shift register (bit LEN-1 back in at the bottom, `flip` 1
    inverts it); LEN 2..7 a loop of notes (bytes 0..LEN-1 turn a byte a step, byte LEN-1 back to 0 with `flip`'s
    bits inverted; the top byte counts the loop's place)."""
    if length > NOTE_LOOP_MAX:
        return ((bits << 1) | ((bits >> (length - 1)) & 1) ^ (flip & 1)) & M64
    b = [(bits >> (8 * i)) & 0xff for i in range(8)]
    come = b[length - 1] ^ flip
    b[1:length] = b[0:length - 1]
    b[0] = come
    b[7] = (b[7] % length + 1) % length
    return sum(x << (8 * i) for i, x in enumerate(b))


def step_value(bits, length):
    """tm_step_value: the newest eight bits; in a loop of notes the newest byte with its place's key inverted."""
    if length > NOTE_LOOP_MAX:
        return bits & 0xff
    return (bits & 0xff) ^ NOTE_KEYS[(bits >> 56) % length]


def span(scale):
    """tm_span: SCAL's range in semitones (0 at 0, 24 at 64, 48 at 127)."""
    return (scale * 3 + 4) // 8 if scale <= 64 else 24 + ((scale - 64) * 24 + 31) // 63


def gate(value, density):
    """tm_gate: a note when the step's value, newest bit first, is below 2 * DENS (all at 127)."""
    g = int(f"{value & 0xff:08b}"[::-1], 2)
    return g < (256 if density >= 127 else 2 * density)


def turing_note(centre, value, scale=64):
    """tm_turing_note: centre + value * span / 255 - span / 2, an octave in while off the MIDI range."""
    w = span(scale)
    note = centre + value * w // 255 - w // 2
    while note < 0:
        note += 12
    while note > 127:
        note -= 12
    return note


def seed_bits(seed, track, salt=0):
    x = mix((seed + 0x9e3779b9 * (track + 1) + 0x85ebca6b * salt) & M32)
    return mix((x + 0x6d2b79f5) & M32) << 32 | x


def seed_rng(seed, track):
    return mix((seed + 0x9e3779b9 * (track + 1) + 0x632be5ab) & M32) or 0x6d2b79f5


class Model:
    """One pattern's register of one track, from the boot seed, exactly as tm_step runs it (salt = bank * 16
    + pattern; the flip draws from the track's random state), or from a register state (bits, rng) poked
    into its cell and the track's random state. The cell holds the register as it is at the pass's first step
    (the anchor, `steps` a pass): a PLAY starts there (restart), a MODE switched ON picks the loop up at the
    pattern's step (restart(step, length): the anchor clocked to it as a locked loop)."""

    def __init__(self, seed, track, salt=0, state=None, steps=LENGTH):
        if state:
            self.bits, self.rng = state
        else:
            self.bits, self.rng = seed_bits(seed, track, salt), seed_rng(seed, track)
        self.flips, self.steps, self.pos, self.anchor = 0, steps, 0, self.bits

    def random(self):
        x = self.rng
        x ^= (x << 13) & M32; x ^= x >> 17; x ^= (x << 5) & M32
        self.rng = x
        return x

    def restart(self, step=0, length=LENGTH):
        self.bits, self.pos = self.anchor, step % self.steps
        for _ in range(self.pos):
            self.bits = advance(self.bits, length)
        return self

    def clock(self, lock, length):
        """One step: its value (tm_step_value)."""
        if self.pos == 0:
            self.anchor = self.bits
        self.pos = (self.pos + 1) % self.steps
        r = self.random()
        flip = 0
        if (r & 0xffff) < flip_chance(lock, length):
            flip = 1 if length > NOTE_LOOP_MAX else ((r >> 16) & 0xff) or 0x80
            self.flips += 1
        self.bits = advance(self.bits, length, flip)
        return step_value(self.bits, length)

    def step(self, lock, length, centre=NOTE_C3, scale=64, density=127):
        """One step: its note, or None for a rest."""
        value = self.clock(lock, length)
        return turing_note(centre, value, scale) if gate(value, density) else None

    def note(self, lock, length, centre=NOTE_C3, scale=64):
        return turing_note(centre, self.clock(lock, length), scale)

    def offset(self, lock, length):
        return self.clock(lock, length) * SPAN // 255


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


def set_first(port, on):
    """PROJ > CONTROL > MIDI SEQUENCER > TURING FIRST (row 1), then the menu closed."""
    open_page(port)
    port.press("DOWN")
    port.enc("LEVEL", -1)
    if on:
        port.enc("LEVEL", 1)
    port.press("UP")
    close_page(port)


# ---- the TURING page: AMP's ring ARP -> ARP SETUP -> TURING on a MIDI track ------

PAGE_KIND = 0x460d1684
WINDOW = 0x400bcd14
SETUP_WINDOW = 0x400cfeb6       # MIDI ARP SETUP's window, as WINDOW holds it
WIDGET_DIAL, WIDGET_TEXT = 0x400479b4, 0x400467a4
DOUBLE_TAP_MS = 700             # stock reads a second press within 15 ticks as a double tap:
                                # 240 ms after a press the count is already 14 under the port (~17 ms a tick)


def page_key(port):
    """AMP, slowly enough not to be a double tap."""
    port.run(DOUBLE_TAP_MS)
    port.press("AMP")
    port.run(300)


def double_tap(port):
    """AMP twice, 80 ms press to press."""
    port.run(DOUBLE_TAP_MS)
    for _ in range(2):
        port.key("AMP", True, 40)
        port.key("AMP", False, 40)
    port.run(300)


def open_turing(port):
    """From any MIDI page, TURING FIRST OFF: AMP shows ARP, two double taps step to ARP SETUP and TURING."""
    page_key(port)
    if port.peek(PAGE_KIND, 4) != bytes.fromhex("00000002"):
        raise SystemExit("verify_turing: AMP did not select the ARP page")
    double_tap(port)
    double_tap(port)


def midi_mode(port):
    """MIDI mode whichever mode shows (the MIDI key toggles)."""
    if not int.from_bytes(port.peek(0x80000012, 4), "big"):
        port.press("MIDI")


def page_tracks(port, tracks):
    """{track: (on, lock, length[, scale, density])} set on the TURING page; leaves it showing on the last
    track. SCAL and DENS default to 64 and 127 (a note every step, as the checks from before OCTABAM10)."""
    open_turing(port)
    for track, values in tracks.items():
        port.press(f"T{track}")
        set_page(port, *values)


def turn_to(port, knob, value, lowest=0):
    """A one-tick-a-step knob to its lowest, then up to value (30 ticks a turn at most)."""
    for _ in range(3):
        port.enc(knob, -60)
    left = value - lowest
    while left > 0:
        port.enc(knob, min(60, left))
        left -= 60


def set_page(port, on, lock, length, scale=64, density=127):
    """On the TURING page: knob A MODE (four ticks a step), B LOCK, C LEN, D SCAL, E DENS (one tick a step)."""
    port.enc("A", -8)
    if on:
        port.enc("A", 4)
    port.enc("B", -127)
    if lock:
        port.enc("B", lock)
    turn_to(port, "C", length, 2)
    if scale is not None:
        turn_to(port, "D", scale)
    if density is not None:
        turn_to(port, "E", density)


def window_open(port):
    w = int.from_bytes(port.peek(WINDOW, 4), "big")
    return int.from_bytes(port.peek(w + 8, 4), "big") != 0


def setup_open(port):
    return window_open(port) and int.from_bytes(port.peek(WINDOW, 4), "big") == SETUP_WINDOW


def drawn(port, action):
    """{slot: (widget, value)} of the last page the stock widgets drew after `action` (a page is
    drawn slot 0 upwards, so a slot no higher than the one before starts the next)."""
    port.cmd(f"watch 0x{WIDGET_DIAL:08x},0x{WIDGET_TEXT:08x}")
    port.cmd("hits", b"hits")
    action()
    port.run(300)
    out, last = {}, 6
    for rec in port.cmd("hits", b"hits").split()[2:]:
        f = rec.split(":")
        slot, value = int(f[10], 16), int(f[11], 16)
        if slot < 6:
            if slot <= last:
                out = {}
            out[slot], last = ("dial" if int(f[1], 16) == WIDGET_DIAL else "text", value), slot
    port.cmd("watch off")
    return out


def view(port, action):
    """Which of AMP's pages shows after `action`: SETUP (the MIDI ARP SETUP window), TURING (MODE text,
    LOCK dial, LEN text, SCAL and DENS dials, F not drawn), ARP (TRAN dial, MODE text), else what was drawn."""
    page = drawn(port, action)
    if window_open(port):
        return "SETUP" if setup_open(port) else f"window {port.peek(WINDOW, 4).hex()}"
    kind = lambda slot: page.get(slot, ("", 0))[0]
    if kind(0) == "text" and kind(1) == "dial" and kind(2) == "text" and kind(3) == "dial" and not set(page) - {0, 1, 2, 3, 4}:
        return "TURING"
    if kind(0) == "dial" and kind(2) == "text":
        return "ARP"
    return f"{page}"


def ring(port, name, steps):
    """[(label, action, expected view)] in order, each checked."""
    seen = []
    for label, action, want in steps:
        got = view(port, action)
        seen.append(f"{label}: {got}")
        if got != want:
            check(f"{name}: {label} shows {want}", False, "; ".join(seen))
            return
    check(f"{name}: " + ", ".join(f"{label} {want}" for label, _a, want in steps), True)


def arp_bytes(port, track):
    """The six ARP bytes of a MIDI track in the current Part, as the knob routine 0x40055304 stores them."""
    blob = int.from_bytes(port.peek(0x46c82456, 4), "big")
    part = port.peek(0x100b14cf, 1)[0]
    return port.peek(blob + part * 6322 + 0x8f162 + track * 32 + 12, 6)


def cell_address(bank, pattern, track):
    return CELLS + ((bank * 16 + pattern) * 8 + track) * 12


def decode_cell(raw):
    length = (raw[1] & 0x7f) ^ 16
    valid = 2 <= length <= 64 and raw[2] <= 127 and raw[3] <= 127
    return {"on": raw[0] >> 7 if valid else 0, "lock": (raw[0] & 0x7f) ^ 64 if valid else 64,
            "length": length if valid else 16, "scale": raw[2] ^ 64 if valid else 64,
            "density": raw[3] ^ 64 if valid else 64, "seeded": raw[1] >> 7 if valid else 0,
            "bits": int.from_bytes(raw[4:12], "big")}


def cell(port, bank, pattern, track):
    """One pattern's Turing settings and register for one track (turing.h TmCell)."""
    return decode_cell(port.peek(cell_address(bank, pattern, track), 12))


def encode_cell(on, lock, length, scale=64, density=127, bits=None):
    return bytes([(0x80 if on else 0) | (lock ^ 64), (0x80 if bits is not None else 0) | (length ^ 16), scale ^ 64,
                  density ^ 64]) + (bits or 0).to_bytes(8, "big")


def poke_cell(port, bank, pattern, track, on, lock, length, state=None, scale=64, density=127):
    """Write a cell as the TURING page would (state: a seeded register (bits, rng), the rng the track's random
    state, else unseeded). DENS defaults to 127 here: the checks from before OCTABAM10 play a note a step."""
    raw = encode_cell(on, lock, length, scale, density, state[0] if state else None)
    port.cmd(f"poke 0x{cell_address(bank, pattern, track):08x} {raw.hex()}")
    if state:
        port.cmd(f"poke 0x{RANDOM + 4 * track:08x} {state[1]:08x}")


def current_pattern(port):
    bank, pattern = port.peek(0x800065bd, 2)
    return bank, pattern


def settings(port):
    """The current pattern's eight cells as one record (OCTABAM8's shape), and TURING FIRST."""
    raw = port.peek(SETTINGS, 32)
    bank, pattern = current_pattern(port)
    cells = [decode_cell(c) for c in (lambda b: [b[i:i + 12] for i in range(0, 96, 12)])(
        port.peek(cell_address(bank, pattern, 0), 96))]
    return {"enabled": sum(c["on"] << t for t, c in enumerate(cells)), "lock": [c["lock"] for c in cells],
            "length": [c["length"] for c in cells], "first": raw[20] & 1,
            "valid": raw[:3] == b"TM\x01" and raw[31] == functools.reduce(lambda a, b: a ^ b, raw[:31], 0x5a)}


def fixture(port, tracks):
    """MIDI tracks on their own channels with trigs; T1 gets NOT2."""
    port.run(1000)
    port.press("NO")
    port.press("MIDI")
    setup_tracks(port, tracks)
    port.press("T1")
    port.enc("D", 7)
    chan = port.peek(0x46c76de0, 69 * len(tracks))
    check("fixture: each track on its own channel",
          all(chan[68 * i] == channel for i, (_t, channel, _s) in enumerate(tracks)), chan[::68].hex())


def setup_tracks(port, tracks):
    """In MIDI mode: each track's channel (FUNC+SRC) and its trigs (grid recording)."""
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


def play(port, ms):
    port.press("PLAY")
    port.run(ms)
    port.press("STOP")
    port.run(400)
    return notes(port.writes())


def play_timed(port, ms):
    """PLAY `ms`, STOP: the timed note events queued for MIDI OUT meanwhile."""
    port.writes_timed()
    port.press("PLAY")
    port.run(ms)
    port.press("STOP")
    port.run(400)
    return timed_notes(port.writes_timed())


def set_scale(port, moves):
    """FUNC+PAGE (PATTERN SCALE), its SCALE field, UP (faster) or DOWN `moves` times, NO. The window keeps
    its cursor: the first time it opens on the length, two RIGHTs from the scale (RIGHT wraps)."""
    port.press("FUNC", "PAGE")
    port.run(400)
    if not getattr(port, "on_scale", False):
        port.press("RIGHT")
        port.press("RIGHT")
        port.on_scale = True
    for _ in range(abs(moves)):
        port.press("UP" if moves > 0 else "DOWN")
    port.press("NO")
    port.run(300)


def place_trigs(port, track, trig_steps):
    """Grid recording on a track: SRC, REC, the TRIG keys, REC."""
    port.press(track)
    port.press("SRC")
    port.press("REC")
    for step in trig_steps:
        port.press(f"TRIG{step}")
    port.press("REC")


def lockstep(t1, ref):
    """Each of t1's steps on one of ref's (the stock track's step times): (all matched, unmatched)."""
    times = [t for t, _n in ref]
    missing = [t for t, _n in t1 if not any(abs(t - r) <= SAME for r in times)]
    return not missing, missing


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

def replace_run(image, work):
    """One boot with the test seed: an empty T1 in REPLACE mode against a stock T2 with a trig on every step."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        watch_midi_out(port)
        off = play_timed(port, 2300)
        check("empty T1, MODE OFF: silent, as stock", not onsets(off, 0) and len(onsets(off, 1)) >= 16,
              f"T1 {onsets(off, 0)[:4]}, T2 {len(onsets(off, 1))} notes")
        velocity = {v for _t, _n, v in onsets(off, 1)}
        length = durations(off, 1)

        seed = 0x13572468
        port.cmd(f"poke 0x{TEST_SEED:08x} {(0x54534545).to_bytes(4, 'big').hex()}{seed.to_bytes(4, 'big').hex()}"
                 f"{(seed ^ M32).to_bytes(4, 'big').hex()}")
        model = Model(seed, 0)
        played = []                                     # every Turing note of T1, in order

        def turing(events, lock, length_, name, ref=True):
            """T1's notes in one run: one a step, on T2's steps, as the model predicts."""
            t1, t2 = steps(events, 0), steps(events, 1)
            got = [n[0] for _t, n in t1]
            want = [model.note(lock, length_) for _ in got]
            played.extend(got)
            check(f"{name}: one note a step, none of NOT2", all(len(n) == 1 for _t, n in t1), f"{t1[:6]}")
            if ref:
                ok, missing = lockstep(t1, t2)
                check(f"{name}: a note on every step of the stock track and only there",
                      ok and len(t1) == len(t2) and len(t1) >= 16, f"T1 {len(t1)} T2 {len(t2)} unmatched {missing[:4]}")
            check(f"{name}: every note as the model predicts", got == want, f"got {got}\nwant {want}")
            return t1, got

        page_tracks(port, {1: (True, 127, 16)})
        c = cell(port, 0, 0, 0)
        check("page: T1 ON 127/16 in pattern A01's cell", (c["on"], c["lock"], c["length"]) == (1, 127, 16), f"{c}")
        a = play_timed(port, 4300)
        t1, got = turing(a, 127, 16, "empty T1 ON, 1x")
        dt = [b[0] - x[0] for x, b in zip(t1, t1[1:])]
        check("1x: 16 notes a bar (a 16th at 120 BPM)", dt and abs(sum(dt) / len(dt) - STEP) < STEP / 200,
              f"mean {sum(dt) / max(len(dt), 1):.1f} samples, want {STEP:.1f}")
        check("LOCK 127, LENGTH 16: repeats every 16 steps", periodic(got, 16), f"{got}")
        check("T2's velocity", {v for _t, _n, v in onsets(a, 0)} == velocity, f"{velocity}")
        d1, d2 = sorted(durations(a, 0)), sorted(durations(a, 1))
        check("T2's note length (median note-on to note-off)", d1 and d2 and abs(d1[len(d1) // 2] - d2[len(d2) // 2]) <= SAME,
              f"T1 {d1[len(d1) // 2] if d1 else None} T2 {d2[len(d2) // 2] if d2 else None}")

        place_trigs(port, "T1", (1, 3, 5, 8, 11, 14))   # T1 still ON: its trigs must send nothing
        b = play_timed(port, 4300)
        model.restart()                                 # each PLAY starts from the pass start the cell holds
        turing(b, 127, 16, "trigs placed on T1 while ON")
        page_tracks(port, {1: (True, 127, 5)})
        c = play_timed(port, 4300)
        model.restart()
        _t, got = turing(c, 127, 5, "LOCK 127, LENGTH 5")
        check("LOCK 127, LENGTH 5: repeats every 5 steps", periodic(got, 5), f"{got}")
        page_tracks(port, {1: (True, 127, 16)})

        for moves, name, factor, ms in ((2, "2X", 0.5, 2300), (-4, "1/2X", 2, 4300), (2, "1X", 1, 0)):
            set_scale(port, moves)
            if not ms:
                continue
            run = play_timed(port, ms)
            model.restart()
            t1, _got = turing(run, 127, 16, f"empty T1 ON, {name}")
            dt = [b[0] - x[0] for x, b in zip(t1, t1[1:])]
            check(f"{name}: a step every {factor} 16th", dt and abs(sum(dt) / len(dt) - STEP * factor) < STEP * factor / 200,
                  f"mean {sum(dt) / max(len(dt), 1):.1f}, want {STEP * factor:.1f}")

        port.writes_timed()
        port.press("PLAY")
        port.run(1500)
        port.press("FUNC", "T1")                        # mute (bit 8 of 0x8000000c, the note routine's mask)
        muted = port.sample()
        mask = port.peek(0x8000000c, 4)
        port.run(1500)
        unmuting = port.sample()
        port.press("FUNC", "T1")                        # unmute
        unmuted = port.sample()
        port.run(1500)
        port.press("FUNC", "T1")                        # muted again, and STOP while muted
        remuted = port.sample()
        port.run(800)
        port.press("STOP")
        port.run(400)
        port.press("FUNC", "T1")                        # unmuted while stopped
        m = timed_notes(port.writes_timed())
        t1, grid = steps(m, 0), steps(m, 1)             # T2 plays every step: the step grid
        inside = [t for t, _n in t1 if muted + 2 * STEP < t < unmuting or t > remuted + 2 * STEP]
        check("mute: T1 silent while muted, T2 goes on", mask == bytes.fromhex("00000100") and not inside
              and len([1 for t, _n in grid if muted + 2 * STEP < t < unmuting]) >= 8,
              f"mask {mask.hex()}, T1 inside {inside[:4]}")
        check("mute: T1 plays before and after", any(t < muted for t, _n in t1) and any(t > unmuted for t, _n in t1),
              f"{[round(t) for t, _n in t1][:4]} muted {muted:.0f} unmuted {unmuted:.0f}")
        index = [min(range(len(grid)), key=lambda i: abs(grid[i][0] - t)) for t, _n in t1]
        model.restart()
        every = [model.note(127, 16) for _ in grid]     # the register clocks on every step, muted or not
        got = [n[0] for _t, n in t1]
        want = [every[i] for i in index]
        played.extend(got)
        check("mute: the register keeps clocking while muted; after unmute T1 plays the note of the step it is on",
              got == want and lockstep(t1, grid)[0] and len(set(index)) == len(index),
              f"got {got}\nwant {want}\nsteps {index}")

        port.press("T1")
        open_turing(port)
        port.writes_timed()
        port.press("PLAY")
        port.run(1500)
        turning_off = port.sample()
        port.enc("A", -4)                               # the TURING page shows: MODE OFF while playing
        switched_off = port.sample()
        port.run(2300)
        switched_on = port.sample()
        port.enc("A", 4)                                # and ON, read before the knob
        port.run(1500)
        port.press("STOP")
        port.run(400)
        g = timed_notes(port.writes_timed())
        t1 = steps(g, 0)
        stock = [(t, n) for t, n in t1 if len(n) > 1]
        singles = [(t, n) for t, n in t1 if len(n) == 1]
        interval = stock[0][1][1] - stock[0][1][0] if stock else None
        check("MODE OFF while playing: T1's trigs play NOTE and NOT2, at their steps", len(stock) >= 4
              and all(n == (NOTE_C3, NOTE_C3 + interval) for _t, n in stock) and lockstep(stock, steps(g, 1))[0]
              and all(turning_off < t < switched_on + 2 * STEP + 200 * 44.1 for t, _n in stock),
              f"{[(round(t), n) for t, n in stock[:8]]} OFF at {switched_off:.0f}, ON at {switched_on:.0f}")
        check("MODE OFF while playing: no Turing note while OFF",
              not [t for t, _n in singles if switched_off + 2 * STEP < t < switched_on],
              f"{[(round(t), n) for t, n in singles if switched_off + 2 * STEP < t < switched_on][:6]} OFF at {switched_off:.0f}")
        check("MODE ON again: one note a step", len([1 for t, _n in singles if t > switched_on + 200 * 44.1 + 2 * STEP]) >= 8,
              f"{[(round(t), n) for t, n in singles][-4:]}")
        got = [n[0] for _t, n in singles]
        model.restart()                                 # ON again picks the loop up at the pattern's step
        phrase = [model.note(127, 16) for _ in range(16)]
        grid_g = steps(g, 1)
        want = [phrase[grid_index(grid_g, t) % 16] for t, _n in singles]
        played.extend(got)
        check("toggled (after a STOP while muted): every Turing note as the model predicts, ON again at the "
              "pattern's step", got == want, f"got {got}\nwant {want}")

        port.enc("A", -4)                               # OFF while stopped: the first step is T1's own trig
        h = play_timed(port, 1200)
        first = steps(h, 0)[:1], steps(h, 1)[:1]
        check("OFF while stopped: the next PLAY starts on T1's step-1 trig (NOTE, NOT2)", first[0] and first[1]
              and abs(first[0][0][0] - first[1][0][0]) <= SAME and len(first[0][0][1]) == 2, f"{first}")
        check("OFF while stopped: nothing but T1's trigs", all(len(n) == 2 for _t, n in steps(h, 0)), f"{steps(h, 0)}")
        port.enc("A", 4)                                # ON while stopped: the first step is a Turing note
        k = play_timed(port, 2300)
        model.restart()
        first = steps(k, 0)[:1], steps(k, 1)[:1]
        check("ON while stopped: the next PLAY starts with a Turing note on step 1", first[0] and first[1]
              and abs(first[0][0][0] - first[1][0][0]) <= SAME and len(first[0][0][1]) == 1, f"{first}")
        turing(k, 127, 16, "ON while stopped")

        port.press("SRC")
        port.enc("C", 127)                              # LEN to its longest: the last note still held at STOP
        port.writes_timed()
        port.press("PLAY")
        port.run(2300)
        stop_at = port.sample()
        port.press("STOP")
        port.run(400)
        long_run = timed_notes(port.writes_timed())
        sounding, orphans = released(untimed(long_run))
        last_off = max((t for t, kind, ch, _n, _v in long_run if ch == 0 and kind == "off"), default=0)
        check("long LEN: STOP sends a note-off for every T1 note", onsets(long_run, 0) and not sounding
              and not orphans, f"sounding {sorted(sounding)}, orphan offs {orphans}")
        check("long LEN: the last T1 note is released by STOP", last_off >= stop_at, f"last off {last_off:.0f}, STOP {stop_at:.0f}")
        sounding, orphans = released(untimed(off + a + b + c + m + g + h + k))
        check("every note-on released; nothing sounds after STOP", not sounding and not orphans,
              f"sounding {sorted(sounding)}, orphan offs {orphans}")
        return played[:LENGTH]
    finally:
        port.quit()


def timer_seed_run(image, work, wait_ms):
    """One boot without a test seed: an empty T1 ON, PLAY after `wait_ms`, its first 16 notes."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()),))
        poke_cell(port, 0, 0, 0, True, 127, 16)
        watch_midi_out(port)
        port.run(wait_ms)
        first = track_ons(play(port, 2300), 0)[:LENGTH]
        check(f"timer seed, PLAY after {wait_ms} ms: a full phrase inside the range", len(first) == LENGTH
              and all(NOTE_C3 - CENTRE <= n <= NOTE_C3 + SPAN - CENTRE for n in first), f"{first}")
        return first
    finally:
        port.quit()


def settle_card(port, at_least_ms=4000, at_most_ms=90000):
    """Run until the firmware stops writing the card: a project create, SAVE or RELOAD ends with its last
    sector, and its progress screen eats the keys sent before then."""
    ran, last, quiet = 0, None, 0
    while ran < at_most_ms:
        port.run(2000)
        ran += 2000
        written = port.cmd("card status", b"card").split("written=")[1].split()[0]
        quiet = quiet + 1 if written == last else 0
        last = written
        if ran >= at_least_ms and quiet >= 2:
            return
    raise SystemExit(f"verify_turing: the card was still being written after {at_most_ms} ms")


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
    saved = None
    try:
        port.run(1000)
        port.press("NO")
        midi_mode(port)
        port.press("T1")
        page_tracks(port, {1: (True, 127, 8)})
        set_first(port, True)
        s = settings(port)
        check("before the new project: T1 ON 127/8, TURING FIRST ON", s["valid"] and s["enabled"] == 1
              and s["first"] == 1, f"{s}")
        project_menu(port, 6)               # the set's CHANGE: "not within a project", YES
        port.press("YES")
        port.run(1000)
        for _ in range(5):                  # <CREATE NEW SET>, its name, the set, <CREATE EMPTY PROJECT>, its name
            port.press("YES")
            port.run(2500)
        settle_card(port, at_least_ms=25000)
        s = settings(port)
        check("new project: every track starts OFF, TURING FIRST OFF", s["valid"] and s["enabled"] == 0
              and s["lock"] == [64] * 8 and s["length"] == [16] * 8 and s["first"] == 0, f"{s}")
        c = cell(port, 0, 0, 0)
        check("new project: SCAL 64 and DENS 64 (the defaults)", (c["scale"], c["density"]) == (64, 64), f"{c}")
        midi_mode(port)                     # MIDI mode, T1: the TURING page and the row set what SAVE writes
        port.press("T1")
        page_tracks(port, {1: (True, 127, 64, 100, 30)})
        set_first(port, True)
        port.press("PLAY")                  # the register is seeded and clocks; SAVE writes it
        port.run(1000)
        port.press("STOP")
        port.run(400)
        saved = cell(port, 0, 0, 0)
        check("before SAVE: A01's T1 register seeded by a PLAY", saved["seeded"] == 1 and saved["bits"], f"{saved}")
        project_menu(port, 1)               # SAVE
        port.press("YES")
        settle_card(port, at_least_ms=20000)
        port.press("NO")
        midi_mode(port)
        port.press("T1")
        page_key(port)                      # TURING FIRST ON: AMP shows TURING
        set_page(port, False, 64, 16, 64, 64)
        set_first(port, False)
        s = settings(port)
        check("after SAVE, T1 set back to OFF 64/16 (SCAL 64, DENS 64) on the page and TURING FIRST OFF", s["valid"]
              and s["enabled"] == 0 and s["lock"][0] == 64 and s["length"][0] == 16 and s["first"] == 0
              and (cell(port, 0, 0, 0)["scale"], cell(port, 0, 0, 0)["density"]) == (64, 64), f"{s}")
        project_menu(port, 2)               # RELOAD
        port.press("YES")
        settle_card(port, at_least_ms=25000)
        s = settings(port)
        back = cell(port, 0, 0, 0)
        check("RELOAD restores the saved T1 ON 127, LEN 64, SCAL 100, DENS 30 and TURING FIRST ON", s["valid"]
              and s["enabled"] == 1 and s["lock"][0] == 127 and s["length"][0] == 64 and s["first"] == 1
              and (back["scale"], back["density"]) == (100, 30), f"{s} {back}")
        check("RELOAD restores A01's T1 64-bit register as saved (the same locked phrase from the same point)",
              (back["seeded"], back["bits"]) == (1, saved["bits"]), f"{back} vs {saved}")
        port.press("NO")
        midi_mode(port)
        port.press("T1")
        port.press("SRC")
        shown = view(port, lambda: page_key(port))
        check("after RELOAD, AMP shows TURING first", shown == "TURING", shown)
    finally:
        port.quit()
    files = port.card_files()
    work_files = {path: data.decode("latin1").splitlines() for path, data in files.items()
                  if path.lower().endswith("project.work")}
    lines = next(iter(work_files.values()), [])
    turing = [line for line in lines if line.startswith("#TURING")]
    r = saved["bits"] if saved else 0
    want = "#TURING_B1_P1_T1=1,127,64,100,30," + ",".join(str(r >> (16 * i) & 0xffff) for i in (3, 2, 1, 0))
    check("project.work holds exactly #TURING_B1_P1_T1=1,127,64,100,30,<64-bit register> and #TURING_FIRST=1",
          turing == [want, "#TURING_FIRST=1"], f"{turing}, want {want}")
    if turing:
        at = lines.index(turing[0])
        check("written after PATTERN_CHANGE_AUTO_SILENCE_TRACKS", lines[at - 1].startswith("PATTERN_CHANGE_AUTO_SILENCE_TRACKS="),
              f"{lines[at - 1]!r}")


def page_run(image, work):
    """One boot with the test seed: AMP's ring in both orders, the TURING page sets T1 and T2, the notes
    as the model predicts."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, range(1, 17)), ("T2", 2, range(1, 17))))
        seed = 0x2468ace1
        port.cmd(f"poke 0x{TEST_SEED:08x} {(0x54534545).to_bytes(4, 'big').hex()}{seed.to_bytes(4, 'big').hex()}"
                 f"{(seed ^ M32).to_bytes(4, 'big').hex()}")
        models = {0: Model(seed, 0), 1: Model(seed, 1)}
        arp = (arp_bytes(port, 0), arp_bytes(port, 1))
        port.press("T1")
        press, tap = (lambda: page_key(port)), (lambda: double_tap(port))
        func_amp, no = (lambda: port.press("FUNC", "AMP")), (lambda: port.press("NO"))
        ring(port, "TURING FIRST OFF", (
            ("AMP from SRC", press, "ARP"), ("double tap", tap, "SETUP"), ("double tap", tap, "TURING"),
            ("double tap (wrap)", tap, "ARP"), ("double tap", tap, "SETUP"), ("press", press, "ARP"),
            ("double tap", tap, "SETUP"), ("double tap", tap, "TURING"), ("press", press, "ARP"),
            ("press", press, "ARP"), ("FUNC+AMP", func_amp, "SETUP"), ("NO", no, "ARP"),
            ("double tap", tap, "SETUP"), ("double tap", tap, "TURING"), ("FUNC+AMP", func_amp, "SETUP"),
            ("FUNC+AMP", func_amp, "ARP")))
        port.press("SRC")
        ring(port, "TURING FIRST OFF, from SRC", (("double tap", tap, "SETUP"), ("NO", no, "ARP")))
        stock_arp = drawn(port, press)
        check("page: AMP shows the stock ARP page (TRAN is a dial, MODE text)",
              stock_arp.get(0, ("", 0))[0] == "dial" and stock_arp.get(2, ("", 0))[0] == "text", f"{stock_arp}")
        double_tap(port)
        watch_midi_out(port)
        port.writes()
        default = drawn(port, tap)
        check("page: the second double tap shows TURING with T1's defaults: MODE OFF, LOCK 64 (dial), LENGTH 16, "
              "SCAL 64 (dial), DENS 64 (dial)",
              default.get(0) == ("text", 0) and default.get(1) == ("dial", 64) and default.get(2) == ("text", 16)
              and default.get(3) == ("dial", 64) and default.get(4) == ("dial", 64) and not set(default) - {0, 1, 2, 3, 4},
              f"{default}")
        set_page(port, True, 127, 16)
        before = settings(port), cell(port, 0, 0, 0)
        port.enc("F", -5)
        check("page: knob F does nothing", (settings(port), cell(port, 0, 0, 0)) == before, f"{before} -> {settings(port)}")
        port.enc("D", -5)
        port.enc("E", -5)
        c = cell(port, 0, 0, 0)
        check("page: knobs D and E edit SCAL and DENS, one a tick", (c["scale"], c["density"]) == (59, 122), f"{c}")
        port.enc("D", 5)
        port.enc("E", 5)
        t1 = drawn(port, lambda: port.enc("B", 1))      # LOCK is at 127: a redraw, no change
        check("page: the page draws T1 ON, 127, 16, 64, 127", t1.get(0) == ("text", 1)
              and t1.get(1) == ("dial", 127) and t1.get(2) == ("text", 16) and t1.get(3) == ("dial", 64)
              and t1.get(4) == ("dial", 127), f"{t1}")
        port.press("T2")
        port.run(300)
        t2 = drawn(port, lambda: set_page(port, True, 127, 5))
        check("page: T2 selected, the page stays TURING and edits T2", t2.get(0) == ("text", 1)
              and t2.get(1) == ("dial", 127) and t2.get(2) == ("text", 5), f"{t2}")
        s = settings(port)
        check("page: T1 ON 127/16 and T2 ON 127/5 in a valid record", s["valid"] and s["enabled"] == 3
              and s["lock"][:2] == [127, 127] and s["length"][:2] == [16, 5], f"{s}")
        port.enc("A", -4)
        check("page: knob A on T2 switches T2 alone OFF", settings(port)["enabled"] == 1, f"{settings(port)}")
        port.enc("A", 4)
        check("page: and ON again", settings(port)["enabled"] == 3, f"{settings(port)}")
        sent = port.writes()
        check("page: the knobs send nothing on MIDI OUT", not sent, sent.hex())
        check("page: no ARP byte of T1 or T2 changed", (arp_bytes(port, 0), arp_bytes(port, 1)) == arp,
              f"{arp[0].hex()} {arp[1].hex()} -> {arp_bytes(port, 0).hex()} {arp_bytes(port, 1).hex()}")
        back = drawn(port, press)
        check("page: a press shows ARP with T2's own bytes", back.get(0) == ("dial", arp[1][0])
              and back.get(2) == ("text", arp[1][2]), f"{back} arp {arp[1].hex()}")
        port.writes()

        a = play(port, 4300)
        for ch, (lock, length) in {0: (127, 16), 1: (127, 5)}.items():
            got = track_ons(a, ch)
            want = [models[ch].note(lock, length) for _ in got]
            name = ("track 1, LOCK 127 LENGTH 16", "track 2, LOCK 127 LENGTH 5")[ch]
            check(f"page, fixed seed, {name}: every note as the model predicts", len(got) >= 32 and got == want,
                  f"got {got}\nwant {want}")
        double_tap(port)
        double_tap(port)
        port.enc("A", -4)                               # T2 OFF on its own switch
        b = play(port, 4300)
        got = track_ons(b, 0)
        models[0].restart()
        want = [models[0].note(127, 16) for _ in got]
        check("page: T2 OFF on knob A plays its NOTE", len(track_ons(b, 1)) >= 32
              and set(track_ons(b, 1)) == {NOTE_C3}, f"{track_ons(b, 1)[:8]}")
        check("page: while T1 goes on as the model predicts", len(got) >= 32 and got == want,
              f"got {got}\nwant {want}")
        sounding, orphans = released(a + b)
        check("page: every note-on released", not sounding and not orphans,
              f"sounding {sorted(sounding)}, orphan offs {orphans}")
        changed = drawn(port, lambda: port.enc("B", -127))
        check("page: still TURING after PLAY/STOP; T2 LOCK turned to 0", changed.get(1) == ("dial", 0)
              and settings(port)["lock"][:2] == [127, 0], f"{changed}")

        set_first(port, True)
        s = settings(port)
        check("row: TURING FIRST ON in a valid record, the tracks kept", s["valid"] and s["first"] == 1
              and s["enabled"] == 1 and s["lock"][:2] == [127, 0], f"{s}")
        port.press("SRC")
        ring(port, "TURING FIRST ON", (
            ("AMP from SRC", press, "TURING"), ("double tap", tap, "ARP"), ("double tap", tap, "SETUP"),
            ("double tap (wrap)", tap, "TURING"), ("double tap", tap, "ARP"), ("press", press, "TURING"),
            ("double tap", tap, "ARP"), ("double tap", tap, "SETUP"), ("press", press, "TURING"),
            ("press", press, "TURING"), ("T1", lambda: port.press("T1"), "TURING"),
            ("FUNC+AMP", func_amp, "SETUP"), ("NO", no, "ARP"), ("double tap", tap, "SETUP"),
            ("press", press, "TURING")))
        port.press("SRC")
        ring(port, "TURING FIRST ON, from SRC", (("double tap", tap, "ARP"),))
        port.press("MIDI")
        audio = not int.from_bytes(port.peek(0x80000012, 4), "big")
        shown = view(port, lambda: port.press("MIDI"))
        check("TURING FIRST ON: MIDI to audio and back shows TURING", audio and shown == "TURING", f"{audio} {shown}")
        t1 = drawn(port, lambda: port.enc("B", -127))
        check("TURING FIRST ON: the page edits T1, LOCK to 0", t1.get(1) == ("dial", 0)
              and settings(port)["lock"][:2] == [0, 0], f"{t1}")
        set_first(port, False)
        check("row: TURING FIRST OFF again", settings(port)["first"] == 0, f"{settings(port)}")
        port.press("SRC")
        shown = view(port, press)
        check("TURING FIRST OFF: AMP shows ARP", shown == "ARP", shown)
    finally:
        port.quit()


def stock_run(image, work, turing):
    """The same panel script on stock and on the image. Every MODE OFF: T1 (trigs, NOT2) and T2 (a trig on
    every step) for 4.3 s, the wire bytes. Then CLOCK SEND and TRANSPORT SEND on and, on the image, T1 ON:
    2.3 s, the wire bytes and the sequencer tick ISRs."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, (1, 3, 4, 7, 9, 12, 13, 16)), ("T2", 2, range(1, 17))))
        port.wire()
        port.press("PLAY")
        port.run(4300)
        port.press("STOP")
        port.run(400)
        off = port.wire()
        sync = port.peek(0x80000028, 1)[0]
        port.cmd(f"poke 0x80000028 {sync | 2:02x}")     # CLOCK SEND (diag/repro_clock.py)
        port.cmd("poke 0x8000002a 01")                  # TRANSPORT SEND
        if turing:
            poke_cell(port, 0, 0, 0, True, 64, 16)
        port.wire()
        port.cmd(f"watch 0x{TICK_ISR:08x}")
        port.cmd("hits", b"hits")
        port.press("PLAY")
        port.run(2300)
        ticks = len(port.cmd("hits", b"hits").split()) - 2
        port.press("STOP")
        port.run(400)
        port.cmd("watch off")
        return off, port.wire(), ticks
    finally:
        port.quit()


# ---- brief 7 (OCTABAM9): locks, NEI, range, ARP, LFO, external clock, patterns ----------

def messages(data):
    """[(sample, byte)] -> [(sample, status, data...)]: every channel message, running status."""
    out, status, buf = [], None, []
    for t, b in data:
        if b >= 0xf8:
            continue
        if b >= 0x80:
            status, buf = b, []
            continue
        if status is None:
            continue
        buf.append(b)
        if len(buf) == (1 if status & 0xf0 in (0xc0, 0xd0) else 2):
            out.append((t, status, *buf))
            buf = []
    return out


def run_messages(port, ms):
    """PLAY `ms`, STOP: (timed note events, every channel message)."""
    port.writes_timed()
    port.press("PLAY")
    port.run(ms)
    port.press("STOP")
    port.run(400)
    raw = port.writes_timed()
    return timed_notes(raw), messages(raw)


def seed(port, value):
    port.cmd(f"poke 0x{TEST_SEED:08x} {(0x54534545).to_bytes(4, 'big').hex()}{value.to_bytes(4, 'big').hex()}"
             f"{(value ^ M32).to_bytes(4, 'big').hex()}")


def set_cond(port, track, step, condition, bank=0, pattern=0):
    """A trig's condition, as the evaluator reads it (0x4009cf4c: the low seven bits of the step's word at
    10368 + track * 1112 + pattern * 18284 + step, in halfwords): 1 FILL, 2 NOT FILL, 5 NEI. The panel sets it
    with a knob this harness does not reach on a MIDI track (LEVEL on a held trig plays its note)."""
    port.cmd(f"poke 0x{BANK0 + bank * 635712 + (10368 + track * 1112 + pattern * 18284 + step) * 2 + 1:08x} "
             f"{condition:02x}")


def hold_lock(port, step, knob, delta):
    """Grid recording is on: hold TRIG `step` and turn a knob, a parameter lock on that step."""
    port.key(f"TRIG{step}", True)
    for part in [max(-30, min(30, delta - d)) for d in range(0, delta, 30)] if delta > 0 else \
            [max(-30, min(30, delta - d)) for d in range(0, delta, -30)]:
        port.enc(knob, part)
    port.key(f"TRIG{step}", False)


def lock_record(port, track, step, bank=0, pattern=0):
    return port.peek(BANK0 + bank * 635712 + pattern * 36568 + track * 2224 + step * 32 + 18688, 32)


def note_lengths(events, channel, only=None):
    """[(note-on sample, length)] of one channel's notes (of note `only`)."""
    held, out = {}, []
    for t, kind, ch, n, _v in events:
        if ch != channel or (only is not None and n != only):
            continue
        if kind == "on":
            held[n] = t
        elif n in held:
            out.append((held[n], t - held.pop(n)))
    return out


def grid_index(grid, t):
    return min(range(len(grid)), key=lambda i: abs(grid[i][0] - t))


def locks_run(image, work):
    """(b), (c): T1 (trigs on steps 1, 3, 5, 9; NOT2) with parameter locks, T2 a trig on every step. Stock
    (T1 OFF) is the reference for what each lock does; T1 ON must apply the same locks to its Turing notes."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, (1, 3, 5, 9)), ("T2", 2, range(1, 17))))
        sd = 0x0badcafe
        seed(port, sd)
        # CC1 (CC 7, MAIN VOL as CTRL 1 SETUP assigns it) is OFF on the CTRL 1 page and its knob does not move
        # it off OFF under the port: its send bit (the Part's byte 30, bit 2; the note routine 0x4009fea6)
        # is set here, in the Part and in the track's resolved copy, so CC1's locks are sent as stock sends them.
        for a in (BANK0 + 0x8f162 + 30, 0x46c76dc0 + 30):
            port.cmd(f"poke 0x{a:08x} 04")
        port.press("T1")
        port.press("FX1")
        port.press("REC")
        hold_lock(port, 1, "C", -40)        # step 1: CC1 87 ...
        hold_lock(port, 3, "C", -20)        # step 3: CC1 107
        port.press("FUNC", "TRIG7")         # step 7: a lock trig (no note trig): CC1 77 ...
        hold_lock(port, 7, "C", -50)
        port.press("SRC")
        hold_lock(port, 7, "B", -70)        # ... and VEL 30
        hold_lock(port, 1, "B", -100)       # ... and VEL 0 (OFF): no note on step 1
        hold_lock(port, 5, "A", 12)         # step 5: NOTE C4
        hold_lock(port, 9, "B", -40)        # step 9: VEL 60 ...
        hold_lock(port, 9, "C", -3)         # ... and a shorter LEN (a longer one is cut by the next step's
                                            # note on stock too: a fired step releases the track's notes)
        port.press("REC")
        recs = {st: lock_record(port, 0, st - 1) for st in (1, 3, 5, 7, 9)}
        check("locks: the panel wrote them (step 1 VEL 0 + CC1 87, 3 CC1 107, 5 NOTE 60, 7 VEL 30 + CC1 77, 9 VEL 60 + LEN)",
              recs[1][1] == 0 and recs[1][20] == 87 and recs[3][20] == 107 and recs[5][0] == 60
              and recs[7][1] == 30 and recs[7][20] == 77 and recs[9][1] == 60 and recs[9][2] != 0xff,
              " ".join(f"{k}:{v.hex()[:48]}" for k, v in recs.items()))
        watch_midi_out(port)
        off, off_m = run_messages(port, 4300)
        poke_cell(port, 0, 0, 0, True, 127, 16)
        on, on_m = run_messages(port, 4300)

        def cc(ms, t0, t1):
            return [(m[2], m[3]) for m in ms if m[1] == 0xb0 and t0 - SAME <= m[0] <= t1 + SAME]

        grid_off, grid_on = steps(off, 1), steps(on, 1)
        model = Model(sd, 0)
        notes_on = [(t, n, v) for t, n, v in onsets(on, 0)]
        expect, got = [], []
        for i, (gt, _n) in enumerate(grid_on):
            pos = i % 16 + 1
            note = model.note(127, 16, 60 if pos == 5 else NOTE_C3)
            hit = [(t, n, v) for t, n, v in notes_on if abs(t - gt) <= SAME]
            got.append((pos, hit[0][1] if hit else None, hit[0][2] if hit else None))
            expect.append((pos, None if pos == 1 else note, None if pos == 1 else 30 if pos == 7 else 60 if pos == 9 else 100))
        check("(b)(c) ON: one Turing note a step; VEL locks set its velocity (7: 30, 9: 60); VEL 0 on 1: no note; "
              "NOTE C4 on 5 centres that step's note on C4 (the register's offset - 12 + 60)",
              got == expect and len(got) >= 32, f"got {got[:18]}\nwant {expect[:18]}")
        d_on = {grid_index(grid_on, t) % 16 + 1: d for t, d in note_lengths(on, 0)[:-1]}      # the last: STOP
        d_off = {grid_index(grid_off, t) % 16 + 1: d for t, d in note_lengths(off, 0, NOTE_C3)[:-1]}
        others = [d for pos, d in d_on.items() if pos != 9]
        check("(b) ON: the LEN lock on 9 gives that Turing note stock's locked length; the others the default",
              9 in d_on and 9 in d_off and 3 in d_off and abs(d_on[9] - d_off[9]) <= SAME and d_off[9] < d_off[3] - SAME
              and others and all(abs(d - d_off[3]) <= SAME for d in others),
              f"ON {d_on}; stock {d_off}")
        ccs_off = [(grid_index(grid_off, m[0]) % 16 + 1, m[2], m[3]) for m in off_m if m[1] == 0xb0]
        ccs_on = [(grid_index(grid_on, m[0]) % 16 + 1, m[2], m[3]) for m in on_m if m[1] == 0xb0]
        check("(b) OFF (stock): CC1's locks go out on their trigs, the lock trig and the VEL-0 trig "
              "(87 on 1, 107 on 3, 77 on 7), back to its value on the next trig", (1, 7, 87) in ccs_off
              and (3, 7, 107) in ccs_off and (7, 7, 77) in ccs_off, f"{ccs_off[:12]}")
        check("(b) ON: the same CC1 locks go out on the same steps -- 1 with no note (VEL 0), 3 with its Turing "
              "note, 7 (a lock trig) with its Turing note -- and its value comes back on the next step",
              (1, 7, 87) in ccs_on and (3, 7, 107) in ccs_on and (7, 7, 77) in ccs_on
              and all((p + 1, 7, 127) in ccs_on for p in (1, 3, 7)), f"{ccs_on[:16]}")
        port.press("FUNC", "T1")                        # muted: stock sends nothing for a muted track
        mo, mo_m = run_messages(port, 2300)
        resolved = []
        port.press("PLAY")
        for _ in range(6):
            port.run(130)
            resolved.append(port.peek(0x46c76dc0, 3))
        port.press("STOP")
        port.run(400)
        port.press("FUNC", "T1")
        poke_cell(port, 0, 0, 0, False, 127, 16)
        port.press("FUNC", "T1")
        fo, fo_m = run_messages(port, 2300)
        port.press("FUNC", "T1")
        check("(b) muted: nothing of T1 goes out, ON as stock (OFF): no note, no CC", not [m for m in mo_m if m[1] & 15 == 0]
              and not [m for m in fo_m if m[1] & 15 == 0] and len(steps(mo, 1)) >= 16,
              f"ON {[m for m in mo_m if m[1] & 15 == 0][:4]} OFF {[m for m in fo_m if m[1] & 15 == 0][:4]}")
        check("(b) muted, ON: the Turing steps still resolve (the track's resolved NOTE moves step to step)",
              len({r[0] for r in resolved}) >= 3, f"{[r.hex() for r in resolved]}")
    finally:
        port.quit()


def nei_run(image, work):
    """(d): T2 a trig on every step with the NEI condition. T1: a FILL trig on 1 (false) and a NOT FILL trig on
    9 (true). OFF: NEI follows T1's trigs (T2 plays 9..16 of a bar). ON: every step is a Turing note, true."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, (1, 9)), ("T2", 2, range(1, 17))))
        set_cond(port, 0, 0, 1)
        set_cond(port, 0, 8, 2)
        for st in range(16):
            set_cond(port, 1, st, 5)
        watch_midi_out(port)
        play_timed(port, 600)                           # STOP evaluates the first step with the conditions
        off = play_timed(port, 4300)
        grid = [t for t, n in steps(off, 1)]
        t1 = steps(off, 0)
        first = t1[0][0] if t1 else 0                   # T1's first note: its trig on step 9
        pos = [(round((t - first) / STEP) + 8) % 16 + 1 for t in grid if t >= first - SAME]
        check("(d) OFF: T1 plays its NOT FILL trig (9) and not its FILL trig (1)", t1 and all(len(n) == 2 for _t, n in t1)
              and len(t1) >= 2, f"{t1}")
        check("(d) OFF: T2's NEI follows T1's trigs: it plays 9..16 of a bar, never 1..8",
              pos and set(pos) == set(range(9, 17)), f"{pos}")
        poke_cell(port, 0, 0, 0, True, 64, 16)
        play_timed(port, 600)
        on = play_timed(port, 4300)
        t1, t2 = steps(on, 0), steps(on, 1)
        check("(d) ON: T1 a Turing note on every step, T2's NEI true on every one of them",
              len(t1) >= 32 and len(t2) == len(t1) and lockstep(t2, t1)[0] and all(len(n) == 1 for _t, n in t1),
              f"T1 {len(t1)} T2 {len(t2)}")
    finally:
        port.quit()


def range_run(image, work):
    """(e): the note range across registers and NOTE values: every note within NOTE-12..NOTE+12 (an octave in
    where that leaves 0..127), as the model predicts, for poked registers and LOCKs."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()),))
        watch_midi_out(port)
        rnd = __import__("random").Random(7)
        port.press("T1")
        port.press("SRC")
        note, results = NOTE_C3, []
        for target in (NOTE_C3, 6, 121):
            while note != target:
                d = max(-30, min(30, target - note))
                port.enc("A", d)
                note += d
            for _ in range(3):
                bits, rng = rnd.getrandbits(64), rnd.getrandbits(32) | 1
                lock, length = rnd.choice((0, 30, 64, 100, 127)), rnd.randint(2, 64)
                poke_cell(port, 0, 0, 0, True, lock, length, (bits, rng))
                ev = play_timed(port, 1700)
                got = [n[0] for _t, n in steps(ev, 0)]
                m = Model(0, 0, state=(bits, rng))
                want = [m.note(lock, length, target) for _ in got]
                lo, hi = max(0, target - CENTRE), min(127, target + CENTRE)
                results.append((target, lock, length, got == want and len(got) >= 12 and all(lo <= n <= hi for n in got),
                                min(got, default=None), max(got, default=None)))
        check("(e) every note within NOTE-12..NOTE+12 and as the model predicts (NOTE C3, 6, 121; 9 registers)",
              all(r[3] for r in results), f"{results}")
    finally:
        port.quit()


def range_model_check():
    """(e), the arithmetic: 4,000 random registers x 64 steps x every LOCK class, NOTE 0..127."""
    rnd = __import__("random").Random(11)
    worst = 0
    for i in range(4000):
        m = Model(0, 0, state=(rnd.getrandbits(64), rnd.getrandbits(32) | 1))
        lock, length, centre = rnd.randint(0, 127), rnd.randint(2, 64), rnd.randint(0, 127)
        for _ in range(64):
            n = m.note(lock, length, centre)
            lo, hi = max(0, centre - CENTRE), min(127, centre + CENTRE)
            if not lo <= n <= hi:
                worst += 1
    check("(e) model: 4,000 registers x 64 steps, NOTE 0..127: every note within NOTE-12..NOTE+12 and 0..127",
          worst == 0, f"{worst} out of range")


def arp_run(image, work):
    """(f): T1 ON (LOCK 127, LENGTH 16: one phrase a bar) beside T3, a stock track with a trig on every step whose
    NOTE locks are that phrase. With the same ARP settings the two must give the same notes at the same times;
    with ARP SETUP's KEY on C MAJ every note is in C major."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17)), ("T3", 3, range(1, 17))))
        sd = 0x5eed1234
        seed(port, sd)
        m = Model(sd, 0)
        start = (m.bits, m.rng)                         # each run starts T1's phrase here, as T3's bar starts
        phrase = [m.note(127, 16) for _ in range(16)]
        port.press("T3")
        port.press("SRC")
        port.press("REC")
        for st, n in enumerate(phrase, 1):
            if n != NOTE_C3:
                hold_lock(port, st, "A", n - NOTE_C3)
        port.press("REC")
        locked = [lock_record(port, 2, st)[0] for st in range(16)]
        check("(f) T3's NOTE locks are the phrase", [NOTE_C3 if x == 0xff else x for x in locked] == phrase,
              f"{locked} vs {phrase}")
        poke_cell(port, 0, 0, 0, True, 127, 16, start)
        watch_midi_out(port)
        base = play_timed(port, 2300)
        a1, a3 = [n[0] for _t, n in steps(base, 0)], [n[0] for _t, n in steps(base, 2)]
        check("(f) ARP off: T1 plays the phrase, as T3", a1 and a1 == a3[:len(a1)], f"T1 {a1}\nT3 {a3}")
        for track in ("T1", "T3"):                      # ARP: MODE UP, SPD faster, RNGE 2 octaves
            port.press(track)
            page_key(port)
            port.enc("C", 8)
            port.enc("D", -2)
            port.enc("E", 4)
        arp = (arp_bytes(port, 0), arp_bytes(port, 2))
        check("(f) ARP on both tracks: MODE UP, the same SPD and RNGE", arp[0] == arp[1] and arp[0][2] == 2, f"{arp[0].hex()} {arp[1].hex()}")
        poke_cell(port, 0, 0, 0, True, 127, 16, start)
        run = play_timed(port, 2300)
        o1 = [(round(t), n) for t, n, _v in onsets(run, 0)]
        o3 = [(round(t), n) for t, n, _v in onsets(run, 2)]
        same = len(o1) == len(o3) and all(abs(x[0] - y[0]) <= SAME and x[1] == y[1] for x, y in zip(o1, o3))
        check("(f) ARP UP: T1's Turing notes arpeggiated exactly as T3's trigs (notes and times)", same and len(o1) > len(steps(run, 1)),
              f"T1 {o1[:10]}\nT3 {o3[:10]} (T2 steps {len(steps(run, 1))})")
        check("(f) ARP UP, 2 octaves: notes outside the phrase (an octave up) are played", any(n not in phrase for _t, n in o1),
              f"{o1[:10]}")
        for track in ("T1", "T3"):                      # ARP SETUP: KEY C MAJ
            port.press(track)
            page_key(port)
            double_tap(port)
            port.enc("F", 1)
            port.press("NO")
            port.run(300)
        key = (port.peek(0x46c76dc0 + 49, 1)[0], port.peek(0x46c76dc0 + 2 * 68 + 49, 1)[0])
        poke_cell(port, 0, 0, 0, True, 127, 16, start)
        run = play_timed(port, 2300)
        k1 = [(round(t), n) for t, n, _v in onsets(run, 0)]
        k3 = [(round(t), n) for t, n, _v in onsets(run, 2)]
        major = {0, 2, 4, 5, 7, 9, 11}
        check("(f) KEY C MAJ: every T1 note in C major", k1 and all(n % 12 in major for _t, n in k1) and key == (1, 1),
              f"key {key} {k1[:12]}")
        check("(f) KEY C MAJ: T1 as T3 (notes and times)", len(k1) == len(k3)
              and all(abs(x[0] - y[0]) <= SAME and x[1] == y[1] for x, y in zip(k1, k3)), f"T1 {k1[:10]}\nT3 {k3[:10]}")
    finally:
        port.quit()


def lfo_run(image, work):
    """(g): LFO 1 targets NOTE (LFO SETUP's default). T1 ON, LOCK 127, LENGTH 4, and T2 a stock trig on every
    step, both with LFO 1 DEP 24: T1's note less the register's note is T2's offset from its NOTE, step by step."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        sd = 0x00c0ffee
        seed(port, sd)
        poke_cell(port, 0, 0, 0, True, 127, 4)
        for track in ("T1", "T2"):
            port.press(track)
            port.press("LFO")
            port.enc("D", 24)
        watch_midi_out(port)
        ev = play_timed(port, 4300)
        t1, t2 = steps(ev, 0), steps(ev, 1)
        m = Model(sd, 0)
        turing = [m.note(127, 4) for _ in t1]
        lfo1 = [n[0] - x for (_t, n), x in zip(t1, turing)]
        lfo2 = [n[0] - NOTE_C3 for _t, n in t2]
        check("(g) LFO on NOTE, LOCK 127, LENGTH 4: T1's offset from the register's note follows the LFO, as on a stock track",
              len(t1) >= 32 and lockstep(t1, t2)[0] and lfo1 == lfo2[:len(lfo1)] and max(lfo2) - min(lfo2) >= 12,
              f"T1 {lfo1}\nT2 {lfo2}")
    finally:
        port.quit()


def clock_run(image, work):
    """(h): CLOCK RECV and TRANSPORT RECV on (PROJECT > MIDI > SYNC, 0x80000028 bit 0 and 0x80000029); MIDI IN
    gets START, 24 clocks a quarter at 125 BPM (20 ms), STOP. T1 ON beside the stock T2 at 1x, 2x and 1/2x."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        sd = 0x13572468
        seed(port, sd)
        poke_cell(port, 0, 0, 0, True, 127, 16)
        sync = port.peek(0x80000028, 1)[0]
        port.cmd(f"poke 0x80000028 {sync | 1:02x}")
        port.cmd("poke 0x80000029 01")
        watch_midi_out(port)
        m = Model(sd, 0)
        for moves, name, factor in ((0, "1x", 1), (2, "2x", 0.5), (-4, "1/2x", 2)):
            if moves:
                set_scale(port, moves)
            m.restart()
            port.writes_timed()
            port.cmd("midi fa")
            for _ in range(24 * 4 * 2):
                port.cmd("midi f8")
                port.run(20)
            port.cmd("midi fc")
            port.run(400)
            ev = timed_notes(port.writes_timed())
            t1, t2 = steps(ev, 0), steps(ev, 1)
            got = [n[0] for _t, n in t1]
            want = [m.note(127, 16) for _ in got]
            dt = [b[0] - a[0] for a, b in zip(t1, t1[1:])]
            step = 6 * 0.020 * 44100 * factor
            check(f"(h) external clock, {name}: a Turing note on every step of the stock track, one per {6 * factor:g} "
                  "clocks, as the model predicts", len(t1) == len(t2) == round(32 / factor) and lockstep(t1, t2)[0]
                  and dt and abs(sum(dt) / len(dt) - step) < step / 50 and got == want,
                  f"T1 {len(t1)} T2 {len(t2)} mean {sum(dt) / max(len(dt), 1):.0f} want {step:.0f}\n{got}\n{want}")
        set_scale(port, 2)
    finally:
        port.quit()


def pattern_run(image, work):
    """(i): A01: T1 ON (LOCK 127, LENGTH 16) on the TURING page; A02: T1 OFF with trigs on 1, 5, 9, 13 (NOTE,
    NOT2). PLAY A01, queue A02, then A01, then A02 (PATTERN + TRIG): A01's bars play its register on from
    where it was, the same locked phrase each bar; A02's bars play its trigs as stock."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        sd = 0x13572468
        seed(port, sd)
        port.press("T1")
        page_tracks(port, {1: (True, 127, 16)})
        port.press("PATTERN", "TRIG2")
        port.run(500)
        on_a02 = current_pattern(port)
        shown = drawn(port, lambda: port.enc("B", 1))
        check("(i) A02 selected: the TURING page shows A02's T1, OFF 64 16", on_a02 == (0, 1)
              and shown.get(0) == ("text", 0) and shown.get(1) == ("dial", 65) and shown.get(2) == ("text", 16), f"{on_a02} {shown}")
        port.enc("B", -1)
        place_trigs(port, "T1", (1, 5, 9, 13))
        place_trigs(port, "T2", range(1, 17))
        c1, c2 = cell(port, 0, 0, 0), cell(port, 0, 1, 0)
        check("(i) the cells: A01 T1 ON 127/16, A02 T1 OFF 64/16", (c1["on"], c1["lock"], c1["length"]) == (1, 127, 16)
              and (c2["on"], c2["lock"], c2["length"]) == (0, 64, 16), f"{c1} {c2}")
        port.press("PATTERN", "TRIG1")
        port.run(500)
        watch_midi_out(port)
        port.writes_timed()
        port.press("PLAY")
        port.run(1000)
        for q in ("TRIG2", "TRIG1", "TRIG2"):
            port.press("PATTERN", q)
            port.run(2000)
        port.press("STOP")
        port.run(400)
        ev = timed_notes(port.writes_timed())
        grid, t1 = steps(ev, 1), steps(ev, 0)
        bars = []
        for b in range(len(grid) // 16):
            span = (grid[16 * b][0] - SAME, grid[16 * b + 15][0] + SAME)
            bars.append([(grid_index(grid, t) - 16 * b, n) for t, n in t1 if span[0] <= t <= span[1]])
        kinds = ["A01" if all(len(n) == 1 for _p, n in bar) and len(bar) == 16 else
                 "A02" if [p for p, _n in bar] == [0, 4, 8, 12] and all(n == (NOTE_C3, NOTE_C3 + 7) for _p, n in bar)
                 else "?" for bar in bars]
        m = Model(sd, 0)
        a01 = [[n[0] for _p, n in bar] for bar, k in zip(bars, kinds) if k == "A01"]
        want = [[m.note(127, 16) for _ in range(16)] for _ in a01]
        joined = "".join(k[-1] for k in kinds)
        check("(i) bars: A01, A02, A01 ... A02 (each bar Turing or stock, nothing else)", "?" not in kinds and "121" in joined
              and joined.startswith("1"), f"{kinds}")
        check("(i) A01's bars: its register on from where it was, the identical locked phrase every bar", a01 and a01 == want
              and all(b == a01[0] for b in a01), f"{a01}\n{want}")
        c1 = cell(port, 0, 0, 0)
        check("(i) A01's register lives in its cell (seeded), A02's never seeded", c1["seeded"] == 1 and not cell(port, 0, 1, 0)["seeded"],
              f"{c1}")
    finally:
        port.quit()



# ---- brief 8 (OCTABAM10): LOCK curve, FUNC snap, LEN 2..64, SCAL, DENS, WRITE, storage -------------

KEYS["PUSHA"] = 0x38                # encoder A pushed (0x4004ecfc(0x38, 1 / 0))
LOCKS = (0, 25, 40, 64, 80, 96, 127)


def push_a(port):
    """Knob A pushed and released, not turned."""
    port.key("PUSHA", True, 200)
    port.key("PUSHA", False, 400)


def popups(port):
    """The texts the stock popup showed since the last call (a watch on 0x4005a2b8 must be armed)."""
    out = []
    for h in port.cmd("hits", b"hits").split()[2:]:
        text = port.peek(int(h.split(":")[8], 16), 24)
        out.append(text.split(b"\0")[0].decode("latin1"))
    return out


def track_data(port, track, bank=0, pattern=0):
    """A MIDI track's trigs in a pattern: (note bits, trigless bits) as 64-bit step masks, 64 lock records, 64 step words."""
    base = BANK0 + bank * 635712
    longs = port.peek(base + 4 * (4660 + track * 556 + pattern * 9142), 16)
    word = lambda i: int.from_bytes(longs[4 * i:4 * i + 4], "big")
    notes, trigless = word(1) | word(0) << 32, word(3) | word(2) << 32
    at = base + pattern * 36568 + track * 2224
    recs = port.peek(at + 0x4900, 2048)
    conds = port.peek(at + 0x5100, 128)
    return notes, trigless, [recs[32 * i:32 * i + 32] for i in range(64)], \
        [int.from_bytes(conds[2 * i:2 * i + 2], "big") for i in range(64)]


def grid_steps(events, t1_channel, grid_channel):
    """{grid index: T1's notes} for the T1 notes on a stock grid track's steps, and the grid's length."""
    grid = steps(events, grid_channel)
    out = {}
    for t, n in steps(events, t1_channel):
        out[grid_index(grid, t)] = n
    return out, len(grid)


def minimal_period(seq, settle=8):
    tail = seq[settle:]
    return next((p for p in range(1, len(tail) // 2 + 1) if all(tail[i] == tail[i + p] for i in range(len(tail) - p))), None)


def lock_model_check():
    """(a), the arithmetic: flips per pass of the loop against the table, LEN 8, 16 and 64, 60 registers x 50
    passes a cell; LOCK 96..127 never flips; LOCK 25 about one bit a pass; the notes a slip changes."""
    rnd = __import__("random").Random(21)
    bad, table = [], []
    for length in (4, 8, 16, 64):
        for lock in LOCKS:
            flips = 0
            for _ in range(60):
                m = Model(0, 0, state=(rnd.getrandbits(64), rnd.getrandbits(32) | 1))
                for _ in range(50 * length):
                    m.clock(lock, length)
                flips += m.flips
            rate, want = flips / 3000, flip_chance(lock, length) * length / 65536
            table.append((length, lock, round(want, 3), round(rate, 3)))
            if abs(rate - want) > max(0.06 * want, 0.03):
                bad.append((length, lock, want, rate))
    print("    LEN LOCK flips/pass: table, measured: " + "; ".join(f"{a} {b}: {c} {d}" for a, b, c, d in table))
    check("(a) model: flips per pass at LOCK 0/25/40/64/80/96/127 (LEN 4, 8, 16, 64) match the documented table",
          not bad, f"{bad}")
    locked = []
    for lock in range(96, 128):
        m = Model(0, 0, state=(rnd.getrandbits(64), rnd.getrandbits(32) | 1))
        seq = [m.note(lock, 16, scale=127) for _ in range(16 * 40)]
        locked.append(m.flips == 0 and periodic(seq, 16))
    check("(a) model: every LOCK 96..127 repeats the loop exactly over 40 passes (no flip)", all(locked),
          f"{[96 + i for i, ok in enumerate(locked) if not ok]}")
    slip = [r for r in table if r[1] == 25]
    check("(a) model: LOCK 25 changes about one bit (LEN 8..64) or one note (LEN 2..7) a pass (0.85..1.15 for LEN 4, 8, 16, 64)",
          all(0.85 <= r[3] <= 1.15 for r in slip), f"{slip}")
    for length in (4, 8, 16, 64):
        changed = []
        for _ in range(40):
            m = Model(0, 0, state=(rnd.getrandbits(64), rnd.getrandbits(32) | 1))
            seq = [m.note(25, length) for _ in range(length * 30)]
            changed.extend(sum(seq[i] != seq[i - length] for i in range(p * length, p * length + length)) for p in range(2, 30))
        print(f"    LOCK 25, LEN {length}: notes that differ from the pass before, mean {sum(changed) / len(changed):.2f} a pass"
              + (" (one flipped bit moves through the eight-bit window: it changes up to 8 notes)" if length == 16 else ""))


WIRE_LENGTHS = (2, 3, 4, 5, 7, 8, 16, 33, 64)


def loop_register(rnd, length, density):
    """A random register (bits, rng) whose locked loop of LEN `length` plays a sequence of period LEN, no shorter
    (a loop of whole notes can still repeat a note: two bytes a step apart giving one note)."""
    while True:
        bits, rng = rnd.getrandbits(64), rnd.getrandbits(32) | 1
        m = Model(0, 0, state=(bits, rng))
        seq = [m.step(127, length, scale=127, density=density) for _ in range(4 * length + 16)]
        if minimal_period(seq) == length and any(x is not None for x in seq):
            return bits, rng


def live_length_run(image, work):
    """(c) as on the hardware, the panel alone: a fresh pattern (fixed test seed), MODE ON at the defaults, PLAY;
    FUNC + LOCK to 127 and DENS to 127 while playing; LEN turned live 16 -> 4 -> 2 -> 3 -> 5 -> 8 -> 7 -> 16, each
    for 64 steps at 2X. On the wire: each LEN's notes repeat with period LEN and play more than one note (OCTABAM10:
    a 2-bit loop of 00 or 11 is one note, and it filled the whole register with it), and the last LEN 16 plays
    notes from across the range."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        seed(port, 0x2bad5eed)
        set_scale(port, 2)
        port.press("T1")
        open_turing(port)
        port.enc("A", 4)
        watch_midi_out(port)
        port.writes_timed()
        port.press("PLAY")
        port.run(1500)
        port.key("FUNC", True, 60)
        port.enc("B", 1)
        port.key("FUNC", False, 60)
        turn_to(port, "E", 127)
        marks = []
        for length in (16, 4, 2, 3, 5, 8, 7, 16):
            port.enc("C", length - cell(port, 0, 0, 0)["length"])
            t0 = port.sample()
            port.run(4000)
            marks.append((length, t0, port.sample()))
        port.press("STOP")
        port.run(400)
        t1 = steps(timed_notes(port.writes_timed()), 0)
        c = cell(port, 0, 0, 0)
        results = []
        for length, a, b in marks:
            got = [n[0] for t, n in t1 if a + 2 * STEP < t < b]
            results.append((length, len(got), minimal_period(got), len(set(got)), min(got, default=None), max(got, default=None)))
        print("    (c) live LEN: (notes, period, distinct notes, lowest, highest): " + "; ".join(f"{r[0]}: {r[1:]}" for r in results))
        check("(c) LEN turned live on the panel (16, 4, 2, 3, 5, 8, 7; LOCK 127): each repeats with period LEN on the "
              "wire and plays more than one note", (c["lock"], c["density"]) == (127, 127)
              and all(n >= 2 * length + 8 and p == length and k > 1 for length, n, p, k, _lo, _hi in results[:-1]),
              f"{results} {c}")
        first, last = results[0], results[-1]
        check("(c) the fresh pattern's LEN 16: at least 8 different notes, spread over the range (not stuck at one end)",
              first[3] >= 8 and first[4] <= NOTE_C3 - 6 and first[5] >= NOTE_C3 + 6, f"{first}")
        # A locked LEN 8 leaves its loop as the register's whole history, so LEN 16 after it replays it twice (as
        # on a Turing Machine): its period divides 16. The notes must still be the short loops' many, not one.
        check("(c) LEN 16 again after LEN 8 and 7: repeats within 16 steps, at least 4 different notes over 8 semitones",
              last[1] >= 40 and last[2] and 16 % last[2] == 0 and last[3] >= 4 and last[5] - last[4] >= 8, f"{last}")
    finally:
        port.quit()


def fresh_model_check():
    """(2) a fresh register is 64 random bits: over 2,000 boot seeds x 8 tracks x 4 patterns the first pass's notes
    (LEN 16, SCAL 64) average the range's centre and fill its quarters evenly."""
    rnd = __import__("random").Random(31)
    notes_ = []
    for _ in range(2000):
        sd = rnd.getrandbits(32)
        for t in range(8):
            for salt in (0, 1, 17, 255):
                m = Model(sd, t, salt)
                notes_.extend(m.note(127, 16) for _ in range(16))
    mean = sum(notes_) / len(notes_)
    low = sum(n < NOTE_C3 - 6 for n in notes_) / len(notes_)
    check("(2) model: fresh registers' notes average NOTE (within 0.5) and a quarter of them sit in the bottom quarter",
          abs(mean - NOTE_C3) < 0.5 and 0.2 < low < 0.3, f"mean {mean:.2f} bottom quarter {low:.3f}")


def fresh_run(image, work):
    """(2) under the port: four tracks x four patterns never played (unseeded cells, fixed test seed), each played
    for a bar at 2X, SCAL 127, LEN 16: the notes are the model's seeded registers, and they spread over the range."""
    port = Port(image, work)
    try:
        fixture(port, tuple((f"T{t + 1}", t + 1, ()) for t in range(4)))
        sd = 0x0f5eed11
        seed(port, sd)
        watch_midi_out(port)
        allnotes, results = [], []
        for pattern in range(4):
            port.press("PATTERN", f"TRIG{pattern + 1}")
            port.run(500)
            for t in range(4):
                poke_cell(port, 0, pattern, t, True, 127, 16, scale=127)
            ev = play_timed(port, 2300)
            for t in range(4):
                got = [n[0] for _t, n in steps(ev, t)]
                m = Model(sd, t, pattern)
                want = [m.note(127, 16, scale=127) for _ in got]
                results.append((pattern, t, len(got), got == want))
                allnotes.extend(got)
        mean = sum(allnotes) / max(len(allnotes), 1)
        check("(2) fresh registers (4 tracks x 4 patterns, unseeded cells): each plays its seeded register, as the model",
              all(n >= 12 and ok for _p, _t, n, ok in results), f"{results}")
        check("(2) fresh registers: the notes average NOTE C3 (within 6 semitones at SCAL 127) and reach both halves",
              abs(mean - NOTE_C3) < 6 and min(allnotes) < NOTE_C3 - 12 and max(allnotes) > NOTE_C3 + 12,
              f"mean {mean:.1f} lowest {min(allnotes, default=None)} highest {max(allnotes, default=None)}")
    finally:
        port.quit()


def lock_run(image, work):
    """(a) the LOCK curve under the port, (b) FUNC + LOCK snaps, (c) LEN 2, 16, 33, 64 at LOCK 127. T1 empty, T2 a
    trig every step, PATTERN SCALE 2X (a step every 62.5 ms)."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        watch_midi_out(port)
        set_scale(port, 2)
        rnd = __import__("random").Random(5)
        results = []
        for lock in LOCKS:
            bits, rng = rnd.getrandbits(64), rnd.getrandbits(32) | 1
            poke_cell(port, 0, 0, 0, True, lock, 16, (bits, rng), scale=127)
            got = [n[0] for _t, n in steps(play_timed(port, 4300), 0)]
            m = Model(0, 0, state=(bits, rng))
            want = [m.note(lock, 16, scale=127) for _ in got]
            results.append((lock, got == want and len(got) >= 60, m.flips, round(len(got) / 16, 1),
                            periodic(got, 16)))
        print("    LOCK: (model == port, flips, passes, repeats): " + "; ".join(f"{r[0]}: {r[1:]}" for r in results))
        check("(a) LOCK 0/25/40/64/80/96/127, LEN 16, SCAL 127: every note under the port as the model of the documented "
              "curve predicts", all(r[1] for r in results), f"{results}")
        check("(a) LOCK 96 and 127: the loop repeats exactly under the port (no flip, period 16)",
              all(r[4] and r[2] == 0 for r in results if r[0] >= 96), f"{results}")
        check("(a) LOCK 0, 25, 40, 64, 80: the loop changes (the model's flips happened)",
              all(r[2] > 0 for r in results if r[0] < 96), f"{results}")

        port.press("T1")
        open_turing(port)
        port.enc("B", -127)
        port.enc("B", 30)
        snaps = []
        for d in (1, 1, 1, -1, -1, -1):
            port.key("FUNC", True, 60)
            port.enc("B", d)
            port.key("FUNC", False, 60)
            snaps.append(cell(port, 0, 0, 0)["lock"])
        port.enc("B", 100)
        port.key("FUNC", True, 60)
        shown = drawn(port, lambda: port.enc("B", -1))
        port.key("FUNC", False, 60)
        snaps.append(cell(port, 0, 0, 0)["lock"])
        port.key("FUNC", True, 60)
        port.enc("B", 1)
        port.key("FUNC", False, 60)
        snaps.append(cell(port, 0, 0, 0)["lock"])
        port.enc("B", -3)
        snaps.append(cell(port, 0, 0, 0)["lock"])
        check("(b) FUNC + LOCK snaps: 30 -> 64 -> 127 -> 127, -> 64 -> 0 -> 0; 100 -> 64 -> 127; without FUNC one a tick (124)",
              snaps == [64, 127, 127, 64, 0, 0, 64, 127, 124] and shown.get(1) == ("dial", 64), f"{snaps} {shown}")

        lengths, gates = [], []
        for length in WIRE_LENGTHS:                     # (c) the notes on the wire, LOCK 127, a note every step
            if length == 64:                            # LEN on the page: C turned well past its end
                turn_to(port, "C", 70, 2)
                page = drawn(port, lambda: port.enc("C", 5))
                c = cell(port, 0, 0, 0)
                check("(c) LEN on the page goes to 64 and stops there", c["length"] == 64 and page.get(2) == ("text", 64),
                      f"{c} {page}")
            bits, rng = loop_register(rnd, length, 127)
            poke_cell(port, 0, 0, 0, True, 127, length, (bits, rng), scale=127)
            got = [n[0] for _t, n in steps(play_timed(port, 1300 + 125 * length), 0)]
            m = Model(0, 0, state=(bits, rng))
            want = [m.note(127, length, scale=127) for _ in got]
            lengths.append((length, len(got), got == want, minimal_period(got)))
        print("    (c) LEN: (notes, model == wire, period on the wire): " + "; ".join(f"{r[0]}: {r[1:]}" for r in lengths))
        check("(c) LOCK 127, LEN 2, 3, 4, 5, 7, 8, 16, 33, 64: the notes on the wire repeat exactly with period LEN (and "
              "no shorter), as the model", all(ok and n >= 2 * length + 8 and p == length for length, n, ok, p in lengths),
              f"{lengths}")
        for length in WIRE_LENGTHS[:7]:                 # (c) and the rests: DENS 64, notes and rests on the grid
            bits, rng = loop_register(rnd, length, 64)
            poke_cell(port, 0, 0, 0, True, 127, length, (bits, rng), scale=127, density=64)
            pos, n = grid_steps(play_timed(port, 1300 + 125 * length), 0, 1)
            got = [pos[i][0] if i in pos else None for i in range(n)]
            m = Model(0, 0, state=(bits, rng))
            want = [m.step(127, length, scale=127, density=64) for _ in got]
            gates.append((length, n, got == want, minimal_period(got), sum(x is not None for x in got)))
        print("    (c) LEN, DENS 64: (steps, model == wire, period of notes and rests, notes): "
              + "; ".join(f"{r[0]}: {r[1:]}" for r in gates))
        check("(c) LOCK 127, DENS 64, LEN 2, 3, 4, 5, 7, 8, 16: notes and rests on the wire repeat with period LEN, as "
              "the model", all(ok and n >= 2 * length + 8 and p == length for length, n, ok, p, _k in gates), f"{gates}")
        set_scale(port, -2)
    finally:
        port.quit()


def scale_model_check():
    """(d), the arithmetic: 3,000 registers x 64 steps, NOTE C3: SCAL 0 only NOTE, 64 within +-12 reaching both ends,
    127 within +-24 reaching both ends and nearly every note between; the span grows with SCAL."""
    rnd = __import__("random").Random(13)
    seen = {0: set(), 64: set(), 127: set()}
    for _ in range(3000):
        state = (rnd.getrandbits(64), rnd.getrandbits(32) | 1)
        for scale in seen:
            m = Model(0, 0, state=state)
            seen[scale] |= {m.note(rnd.choice(LOCKS), 16, NOTE_C3, scale) - NOTE_C3 for _ in range(64)}
    check("(d) model: SCAL 0 plays only NOTE", seen[0] == {0}, f"{sorted(seen[0])}")
    check("(d) model: SCAL 64 within NOTE-12..NOTE+12, both ends reached", min(seen[64]) == -12 and max(seen[64]) == 12,
          f"{sorted(seen[64])}")
    check("(d) model: SCAL 127 within NOTE-24..NOTE+24, both ends and at least 45 of the 49 notes reached",
          min(seen[127]) == -24 and max(seen[127]) == 24 and len(seen[127]) >= 45, f"{sorted(seen[127])}")
    check("(d) model: the span grows with SCAL, 0 / 24 / 48 semitones at 0 / 64 / 127",
          all(span(a) <= span(a + 1) for a in range(127)) and (span(0), span(64), span(127)) == (0, 24, 48),
          f"{[span(a) for a in range(0, 128, 8)]}")


def scale_run(image, work):
    """(d) under the port: SCAL 0, 64, 127 on poked registers (NOTE C3) and against the model; SCAL on the page
    (knob D); a NOTE lock (C4 on step 5) centres that step at SCAL 127; ARP SETUP's KEY quantises SCAL 127."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, (5,)), ("T2", 2, range(1, 17))))
        port.press("T1")
        port.press("SRC")
        port.press("REC")
        hold_lock(port, 5, "A", 12)                     # step 5: NOTE C4
        port.press("REC")
        watch_midi_out(port)
        rnd = __import__("random").Random(17)
        results = []
        for scale in (0, 64, 127):
            for lock in (25, 127):
                bits, rng = rnd.getrandbits(64), rnd.getrandbits(32) | 1
                poke_cell(port, 0, 0, 0, True, lock, 16, (bits, rng), scale=scale)
                ev = play_timed(port, 2300)
                pos, _n = grid_steps(ev, 0, 1)
                m = Model(0, 0, state=(bits, rng))
                want = {i: m.note(lock, 16, 60 if i % 16 == 4 else NOTE_C3, scale) for i in range(max(pos, default=0) + 1)}
                got = {i: n[0] for i, n in pos.items()}
                w = span(scale) // 2
                inside = all(c - w <= n <= c + w for i, n in got.items() for c in [60 if i % 16 == 4 else NOTE_C3])
                results.append((scale, lock, got == want and len(got) >= 16, inside, min(got.values()), max(got.values())))
        check("(d) SCAL 0 / 64 / 127 under the port: every note as the model (NOTE C3, C4 on the NOTE-locked step 5), "
              "within NOTE, +-12, +-24", all(r[2] and r[3] for r in results), f"{results}")
        check("(d) SCAL 0: only NOTE (C3, and C4 on the locked step)",
              all(r[4] >= NOTE_C3 and r[5] <= 60 for r in results if r[0] == 0), f"{results}")
        open_turing(port)
        page = drawn(port, lambda: turn_to(port, "D", 100))
        c = cell(port, 0, 0, 0)
        check("(d) SCAL on the page: knob D sets it (100, a dial with its number)", c["scale"] == 100
              and page.get(3) == ("dial", 100), f"{c} {page}")
        page_key(port)                                  # ARP SETUP's KEY on C MAJ, SCAL 127
        double_tap(port)
        port.enc("F", 1)
        port.press("NO")
        port.run(300)
        bits, rng = rnd.getrandbits(64), rnd.getrandbits(32) | 1
        poke_cell(port, 0, 0, 0, True, 64, 16, (bits, rng), scale=127)
        keyed = [n for _t, n, _v in onsets(play_timed(port, 2300), 0)]
        check("(d) SCAL 127 with ARP SETUP KEY C MAJ: every note in C major, the range still wide",
              len(keyed) >= 16 and all(n % 12 in {0, 2, 4, 5, 7, 9, 11} for n in keyed) and max(keyed) - min(keyed) >= 24,
              f"{keyed}")
    finally:
        port.quit()


def density_model_check():
    """(e), the arithmetic: 4,000 registers x 64 steps: DENS 0 no note, 127 every step, 64 half (49..51 %), the
    share rising with DENS; at LOCK 127 the rests repeat with the loop."""
    rnd = __import__("random").Random(19)
    share = {}
    for density in (0, 32, 64, 96, 127):
        on = total = 0
        r2 = __import__("random").Random(23)
        for _ in range(4000):
            m = Model(0, 0, state=(r2.getrandbits(64), r2.getrandbits(32) | 1))
            for _ in range(64):
                on += m.step(64, 16, density=density) is not None
                total += 1
        share[density] = on / total
    check("(e) model: DENS 0 silent, 127 every step, 64 about half (49..51 %), rising with DENS",
          share[0] == 0 and share[127] == 1 and 0.49 <= share[64] <= 0.51 and share[32] < share[64] < share[96],
          f"{share}")
    rests = []
    for _ in range(200):
        m = Model(0, 0, state=(rnd.getrandbits(64), rnd.getrandbits(32) | 1))
        seq = [m.step(127, 16, density=64) is None for _ in range(16 * 8)]
        rests.append(periodic(seq, 16, settle=8))
    check("(e) model: LOCK 127, DENS 64: the rests fall on the same steps every pass", all(rests), f"{rests.count(False)}")


def density_run(image, work):
    """(e) under the port. T1 the Turing track; T2 a trig on every step with the NEI condition; T3 a trig on every
    step (the grid). DENS 0, 127 and 64 against the model; the rests at LOCK 127 the same every pass; DENS turned
    live to 100 and back to 64; CC1 locks on a rest step still go out; NEI on T2 follows T1's notes."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, (3, 7)), ("T2", 2, range(1, 17)), ("T3", 3, range(1, 17))))
        for st in range(16):
            set_cond(port, 1, st, 5)
        for a in (BANK0 + 0x8f162 + 30, 0x46c76dc0 + 30):      # CC1's send bit, as locks_run
            port.cmd(f"poke 0x{a:08x} 04")
        port.press("T1")
        port.press("FX1")
        port.press("REC")
        hold_lock(port, 3, "C", -40)                    # step 3: CC1 87
        hold_lock(port, 7, "C", -20)                    # step 7: CC1 107
        port.press("REC")
        rnd = __import__("random").Random(29)
        while True:                                     # a register whose step 3 rests and step 7 plays at DENS 64
            bits, rng = rnd.getrandbits(64), rnd.getrandbits(32) | 1
            m = Model(0, 0, state=(bits, rng))
            g = [m.step(127, 16, density=64) is not None for _ in range(16)]
            if not g[2] and g[6] and 5 <= sum(g) <= 11:
                break
        watch_midi_out(port)
        play_timed(port, 600)                           # STOP evaluates the first step with the conditions
        runs = {}
        for density in (0, 127, 64):
            poke_cell(port, 0, 0, 0, True, 127, 16, (bits, rng), density=density)
            runs[density] = run_messages(port, 4300)
        silent, _l = grid_steps(runs[0][0], 0, 2)
        check("(e) DENS 0: T1 silent, T2 (NEI) silent, T3 plays", not silent and not onsets(runs[0][0], 1)
              and len(steps(runs[0][0], 2)) >= 32, f"T1 {silent} T2 {len(onsets(runs[0][0], 1))}")
        full, n_full = grid_steps(runs[127][0], 0, 2)
        check("(e) DENS 127: a note on every step", len(full) == n_full >= 32, f"{len(full)} of {n_full}")
        half, n_half = grid_steps(runs[64][0], 0, 2)
        m = Model(0, 0, state=(bits, rng))
        want = {i: n for i in range(n_half) for n in [m.step(127, 16, density=64)] if n is not None}
        got = {i: n[0] for i, n in half.items()}
        check("(e) DENS 64, LOCK 127: the notes and rests as the model, the same steps rest every pass",
              got == want and n_half >= 32 and all(((i + 16) in got) == (i in got) for i in range(n_half - 16)),
              f"got {sorted(got.items())[:20]}\nwant {sorted(want.items())[:20]}")
        nei, _n = grid_steps(runs[64][0], 1, 2)
        check("(e) NEI on T2 follows T1's Turing notes: true on its note steps, false on its rests",
              set(nei) == set(got) and len(nei) >= 8, f"T2 {sorted(nei)}\nT1 {sorted(got)}")
        grid = steps(runs[64][0], 2)
        ccs = [(grid_index(grid, mm[0]) % 16 + 1, mm[2], mm[3]) for mm in runs[64][1] if mm[1] == 0xb0]
        check("(e) CC1 locks still go out on a rest step (3: 87, no note) and on a note step (7: 107, with its note)",
              (3, 7, 87) in ccs and (7, 7, 107) in ccs and all(i % 16 != 2 for i in got) and any(i % 16 == 6 for i in got),
              f"{ccs[:12]} notes {sorted(got)[:10]}")

        poke_cell(port, 0, 0, 0, True, 127, 16, (bits, rng), density=64)
        open_turing(port)
        port.writes_timed()
        port.press("PLAY")
        port.run(4300)
        port.enc("E", 36)                               # DENS 100 ...
        port.run(4300)
        port.enc("E", -36)                              # ... and back to 64
        port.run(6300)
        port.press("STOP")
        port.run(400)
        live = timed_notes(port.writes_timed())
        pos, n_live = grid_steps(live, 0, 2)
        bars = [sorted(i % 16 for i in pos if b * 16 <= i < b * 16 + 16) for b in range(n_live // 16)]
        check("(e) DENS turned live to 100: more steps play at once; back to 64: the old rhythm returns",
              len(bars) >= 6 and bars[0] == bars[1] == bars[-1] == bars[-2] and len(bars[len(bars) // 2]) > len(bars[0]),
              f"{bars}")
        check("(e) DENS on the page: knob E, back at 64", cell(port, 0, 0, 0)["density"] == 64, f"{cell(port, 0, 0, 0)}")
    finally:
        port.quit()


def write_run(image, work):
    """(f) WRITE. T1 the Turing track (LOCK 127, LEN 16, SCAL 64, DENS 64, set on the page), T2 a trig every step
    (the grid). A push of knob A with MODE OFF does nothing. ON, PLAY, STOP; a push writes: the popup, the trigs and
    NOTE locks as the model; the register untouched. Then ON plays the same phrase, and MODE OFF plays it from the
    track's own trigs: the same MIDI OUT bytes, at the same times. LEN 5 (not a divisor of 16): the first pass
    matches. WRITE while playing, then MODE OFF while playing: one unbroken phrase."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        sd = 0x0dd5eed1
        seed(port, sd)
        port.press("T1")
        page_tracks(port, {1: (False, 127, 16, 64, 64)})
        port.cmd(f"watch 0x{POPUP:08x}")
        popups(port)
        before = track_data(port, 0)
        push_a(port)
        check("(f) MODE OFF: a push of knob A writes nothing and shows no popup", not popups(port)
              and track_data(port, 0) == before, "")
        port.enc("A", 4)
        watch_midi_out(port)
        play_timed(port, 2300)
        c0 = cell(port, 0, 0, 0)
        rng0 = int.from_bytes(port.peek(RANDOM, 4), "big")
        push_a(port)
        shown = popups(port)
        c1 = cell(port, 0, 0, 0)
        check("(f) WRITE: the popup MIDI TRACK WRITTEN", shown == ["MIDI TRACK WRITTEN"], f"{shown}")
        check("(f) WRITE leaves MODE ON and the register as it was", c1 == c0 and c1["on"] == 1
              and int.from_bytes(port.peek(RANDOM, 4), "big") == rng0, f"{c0} -> {c1}")
        m = Model(0, 0, state=(c0["bits"], rng0))
        phrase = [m.step(127, 16, density=64) for _ in range(16)]
        notes_, trigless, recs, conds = track_data(port, 0)
        rec_ok = all((recs[i][0], recs[i][3:6], recs[i][30:32]) == (n, b"\x40\x40\x40", bytes([0x57, NOTE_C3]))
                     if n is not None else recs[i] == b"\xff" * 32 for i, n in enumerate(phrase))
        check("(f) WRITE: a note trig with the register's note as its NOTE lock on each note step, none on the rests, "
              "as the model; NOT2..NOT4 locked off, conditions clear",
              notes_ == sum(1 << i for i, n in enumerate(phrase) if n is not None) and not trigless and rec_ok
              and not any(conds[:16]), f"bits {notes_:016x} phrase {phrase}\n{[r.hex()[:12] for r in recs[:16]]}")
        port.wire()
        on_ev = play_timed(port, 4300)
        on_wire = port.wire()
        pos, n_on = grid_steps(on_ev, 0, 1)
        check("(f) after WRITE, MODE still ON: the same locked phrase on from where it was (the model)",
              {i: n[0] for i, n in pos.items()} == {i: phrase[i % 16] for i in range(n_on) if phrase[i % 16] is not None}
              and n_on >= 32, f"{sorted(pos.items())[:12]}")
        open_turing(port)
        port.enc("A", -4)
        off_ev = play_timed(port, 4300)
        off_wire = port.wire()
        # The wire's running status is not part of the music: stock clears it every 89 passes of a sequencer
        # routine (0x400a4df0), whose phase against PLAY differs from run to run, so two identical stock runs
        # already differ in where a status byte is repeated (diag/octabam10/probe_rs.py). Compared: every MIDI
        # message, status written out, in order, and the times of the notes up to STOP (STOP's release is the
        # panel's moment).
        full = lambda w: [m[1:] for m in messages([(0, x) for x in w])]
        check("(f) MODE OFF after WRITE: the MIDI OUT messages (bytes with running status written out) are exactly "
              "those MODE ON played", full(on_wire) == full(off_wire) and len(full(on_wire)) > 60,
              f"{len(full(on_wire))} vs {len(full(off_wire))} messages, raw {len(on_wire)} vs {len(off_wire)} bytes, first "
              f"difference at {next((i for i, (x, y) in enumerate(zip(full(on_wire), full(off_wire))) if x != y), None)}")
        a = [(t - on_ev[0][0], k, ch, n, v) for t, k, ch, n, v in on_ev]
        b = [(t - off_ev[0][0], k, ch, n, v) for t, k, ch, n, v in off_ev]
        last_a = max(t for t, k, ch, _n, _v in a if k == "on")
        drift = max((abs(x[0] - y[0]) for x, y in zip(a, b) if x[0] <= last_a), default=None)
        check("(f) MODE OFF after WRITE: every note-on and note-off of T1 and T2 at the same time as ON (within 4 "
              "samples, stock's own run-to-run jitter is ~2)", len(a) == len(b) and [x[1:] for x in a] == [y[1:] for y in b]
              and drift is not None and drift <= 4, f"{len(a)} vs {len(b)} events, largest time difference {drift}")
        print(f"    WRITE: raw wire {len(on_wire)} vs {len(off_wire)} bytes (running status), "
              f"{'identical' if on_wire == off_wire else 'status bytes repeated at different points'}; "
              f"largest note time difference ON vs OFF {drift:.1f} samples over {len(a)} events")

        port.enc("A", 4)                                # LEN 5: the written pattern is its first 16 steps
        port.enc("C", 5 - 16)
        play_timed(port, 1200)
        c5 = cell(port, 0, 0, 0)
        rng5 = int.from_bytes(port.peek(RANDOM, 4), "big")
        push_a(port)
        popups(port)
        m = Model(0, 0, state=(c5["bits"], rng5))
        five = [m.step(127, 5, density=64) for _ in range(16)]
        on5, n5 = grid_steps(play_timed(port, 2300), 0, 1)
        port.enc("A", -4)
        off5, m5 = grid_steps(play_timed(port, 4300), 0, 1)
        first = lambda pos, upto: {i: n[0] for i, n in pos.items() if i < upto}
        check("(f) LEN 5: WRITE fills the pattern's 16 steps from the 5-step loop: OFF's first pass is ON's; OFF then "
              "repeats 16 steps", c5["length"] == 5 and first(on5, 16) == first(off5, 16)
              == {i: n for i, n in enumerate(five) if n is not None}
              and all((i + 16 in off5) == (i in off5) for i in range(m5 - 16)), f"{five}\n{sorted(off5.items())[:12]}")

        port.enc("A", 4)                                # LEN 16 again; WRITE while playing, then OFF while playing
        port.enc("C", 11)
        play_timed(port, 1200)
        c2 = cell(port, 0, 0, 0)
        rng2 = int.from_bytes(port.peek(RANDOM, 4), "big")
        m = Model(0, 0, state=(c2["bits"], rng2))
        loop = [m.step(127, 16, density=64) for _ in range(16)]
        port.writes_timed()
        port.press("PLAY")
        port.run(1700)
        push_a(port)
        written = popups(port)
        port.run(1100)
        port.enc("A", -4)
        port.run(2300)
        port.press("STOP")
        port.run(400)
        run, n_run = grid_steps(timed_notes(port.writes_timed()), 0, 1)
        check("(f) WRITE while playing, MODE OFF while playing: one unbroken locked phrase, ON then the written trigs",
              written == ["MIDI TRACK WRITTEN"] and n_run >= 36 and {i: n[0] for i, n in run.items()}
              == {i: loop[i % 16] for i in range(n_run) if loop[i % 16] is not None}, f"{written} {sorted(run.items())[:20]}")
    finally:
        port.quit()


def write_trigs(image, work):
    """What WRITE puts in the trigs (fixed seed, T1 ON LOCK 127, LEN 16, SCAL 64, DENS 64 on the page, a push of knob
    A on the register never played: both builds seed it alike and start at step 1; after a PLAY OCTABAM10 starts
    from the register wherever the loop stopped, brief 9's bug 5), and a trig placed by hand on T3 step 1 with a
    NOTE lock (+5)."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17)), ("T3", 3, ())))
        seed(port, 0x0dd5eed1)
        port.press("T3")
        port.press("SRC")
        port.press("REC")
        port.press("TRIG1")
        hold_lock(port, 1, "A", 5)
        port.press("REC")
        port.press("T1")
        page_tracks(port, {1: (False, 127, 16, 64, 64)})
        port.enc("A", 4)
        push_a(port)
        return track_data(port, 0), track_data(port, 2)
    finally:
        port.quit()


def write_flags_check(image, work):
    """(3) WRITE's trigs are OCTABAM10's (brief 9: WRITE's NOTE-locked trigs flash as stock flashes any locked trig;
    kept as it is): the same register and fixture on out/turing_10.bin give byte-identical trig bits, trigless
    bits, lock records and step words. A hand-placed NOTE-locked trig is shown beside them."""
    work.mkdir()
    ours, hand = write_trigs(image, work / "ours")
    at = next((i for i in range(64) if ours[0] >> i & 1), 0)  # WRITE's first note step
    print(f"    WRITE's note trig (step {at + 1}) / a hand-placed NOTE-locked trig (T3 step 1): note bit {ours[0] >> at & 1}/"
          f"{hand[0] & 1}, trigless {ours[1] >> at & 1}/{hand[1] & 1}, step word {ours[3][at]:04x}/{hand[3][0]:04x}, "
          f"lock record {ours[2][at].hex()} / {hand[2][0].hex()}")
    ten = ROOT / "out/turing_10.bin"
    if not ten.exists():
        check("(3) WRITE: OCTABAM10's payload (out/turing_10.bin) present for the comparison", False, "")
        return
    theirs, _hand = write_trigs(ten, work / "ten")
    check("(3) WRITE: trig bits, trigless bits, lock records and step words byte-identical to OCTABAM10's (the same "
          "trig type and LEDs)", ours == theirs and ours[0], f"ours {ours[0]:016x}/{ours[1]:016x} OCTABAM10 "
          f"{theirs[0]:016x}/{theirs[1]:016x}, records differ at {[i for i in range(64) if ours[2][i] != theirs[2][i]][:8]}")


def toggle_run(image, work):
    """(4) MODE switched between the written trigs (OFF) and live (ON) while playing, twelve times, then six knob
    redraws: every T1 note within 2 ms of the stock grid track's note on its step, one on every step."""
    port = Port(image, work)
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        seed(port, 0x0dd5eed1)
        port.press("T1")
        page_tracks(port, {1: (True, 127, 16, 64, 127)})
        watch_midi_out(port)
        play_timed(port, 1200)
        push_a(port)
        port.writes_timed()
        port.press("PLAY")
        for i in range(12):
            port.run(700)
            port.enc("A", -4 if i % 2 == 0 else 4)
        port.run(1000)
        for _ in range(6):
            port.enc("B", 1)
            port.run(700)
        port.press("STOP")
        port.run(400)
        ev = timed_notes(port.writes_timed())
        grid, t1 = [t for t, _n in steps(ev, 1)], steps(ev, 0)
        late = [abs(t - min(grid, key=lambda g: abs(g - t))) / 44.1 for t, _n in t1]
        print(f"    MODE toggles: {len(t1)} T1 notes on {len(grid)} grid steps, largest |T1 - grid| {max(late, default=0):.3f} ms")
        check("(4) MODE OFF <-> ON while playing (12 switches) and knob redraws: every T1 note within 2 ms of its step, "
              "a note on every step", t1 and len(t1) == len(grid) and max(late) <= 2.0,
              f"{len(t1)} notes on {len(grid)} steps, worst {max(late, default=0):.2f} ms")
    finally:
        port.quit()


def track_keys(port):
    """The track keys select tracks: T3, T2, T1 pressed, the current track (0x80000000) read after each."""
    got = []
    for t in (3, 2, 1):
        port.press(f"T{t}")
        port.run(200)
        got.append(port.peek(0x80000000, 1)[0])
    return got == [2, 1, 0]


def bar_phrase(events):
    """T1's notes on the stock grid (T2, a trig every step) as one bar [(step 1..16, note)], or None when the
    bars differ."""
    pos, n = grid_steps(events, 0, 1)
    bars = [tuple((i % 16 + 1, pos[i][0]) for i in range(b * 16, b * 16 + 16) if i in pos) for b in range(n // 16)]
    return bars[0] if bars and all(b == bars[0] for b in bars) else None


def new_project(port):
    project_menu(port, 6)                   # the set's CHANGE: "not within a project", YES
    port.press("YES")
    port.run(1000)
    for _ in range(5):                      # <CREATE NEW SET>, its name, the set, <CREATE EMPTY PROJECT>, its name
        port.press("YES")
        port.run(2500)
    settle_card(port, at_least_ms=25000)


def reload_run(image, work):
    """(5), (6) the hardware's sequence: a new project, T1 ON (LOCK 127, LEN 16, DENS 64) beside a stock grid track,
    PLAY; WRITE and SAVE while playing, mid-pass; STOP. The locked phrase (notes and rests on their steps) after a
    RELOAD, and after a fresh boot of the saved card that loads the project, is the one played before, from the
    same step; the cell holds the register of the pass's first step. The track keys work after each."""
    sys.path.insert(0, str(ROOT / "tools/emu"))
    import emu_card
    work.mkdir()
    port = Port(image, work / "a", writable=True)
    keys = {}
    try:
        port.run(1000)
        port.press("NO")
        new_project(port)
        midi_mode(port)
        setup_tracks(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        port.press("T1")
        page_tracks(port, {1: (True, 127, 16, 64, 64)})
        watch_midi_out(port)
        ref = bar_phrase(play_timed(port, 4300))
        port.press("PLAY")
        port.run(2900)                      # into the second pass, mid-pass
        push_a(port)
        keys["WRITE while playing"] = track_keys(port)
        port.press("T1")
        anchor = cell(port, 0, 0, 0)
        project_menu(port, 1)               # SAVE, still playing
        port.press("YES")
        settle_card(port, at_least_ms=8000)
        port.press("NO")
        keys["SAVE while playing"] = track_keys(port)
        port.press("STOP")
        port.run(400)
        port.press("T1")
        check("(5) the cell holds the register of the pass's first step, mid-pass and after STOP",
              cell(port, 0, 0, 0)["bits"] == anchor["bits"] and anchor["seeded"], f"{anchor} {cell(port, 0, 0, 0)}")
        page_tracks(port, {1: (True, 127, 16, 64, 64)})
        port.enc("A", -4)                   # MODE OFF: the written trigs ...
        written = bar_phrase(play_timed(port, 4300))
        port.enc("A", 4)                    # ... and ON
        before = bar_phrase(play_timed(port, 4300))
        project_menu(port, 2)               # RELOAD
        port.press("YES")
        settle_card(port, at_least_ms=20000)
        port.press("NO")
        keys["RELOAD"] = track_keys(port)
        port.press("T1")
        back = cell(port, 0, 0, 0)
        reloaded = bar_phrase(play_timed(port, 4300))
        print(f"    reload: before SAVE {ref}\n      written (OFF) {written}\n      after RELOAD {reloaded}")
        check("(5) SAVE while playing mid-pass, RELOAD: the cell's register is the one saved (the pass's first step)",
              (back["seeded"], back["bits"], back["on"], back["lock"], back["length"], back["density"])
              == (1, anchor["bits"], 1, 127, 16, 64), f"{back} vs {anchor}")
        check("(5) RELOAD: the identical locked phrase from the same step (notes and rests), as played before SAVE",
              ref and reloaded == ref == before and written == ref, f"{ref}\n{before}\n{reloaded}")
    finally:
        port.quit()
    tree = work / "tree"
    emu_card.extract_image(port.card.read_bytes(), str(tree))
    works = [f for f in tree.rglob("*") if f.name.lower() == "project.work"]
    if len(works) != 1:
        check("(5) reboot: one project.work on the saved card", False, f"{works}")
        return
    project_dir = works[0].parent
    port = Port(image, work / "b", tree=tree, extra=("--mount", "--set", project_dir.parent.name, "--project", project_dir.name))
    try:
        port.run(3000)
        settle_card(port, at_least_ms=8000)
        booted = cell(port, 0, 0, 0)
        check("(5) a fresh boot of the saved card loads A01's T1 cell as saved (ON 127, LEN 16, DENS 64, the register)",
              (booted["seeded"], booted["bits"], booted["on"], booted["lock"], booted["length"], booted["density"])
              == (1, anchor["bits"], 1, 127, 16, 64), f"{booted} vs {anchor}")
        midi_mode(port)
        keys["boot load"] = track_keys(port)
        watch_midi_out(port)
        rebooted = bar_phrase(play_timed(port, 4300))
        print(f"    reboot + load: {rebooted}")
        check("(5) reboot + load: the identical locked phrase from the same step", rebooted == ref, f"{rebooted}\n{ref}")
    finally:
        port.quit()
    check("(6) the track keys select tracks after WRITE, SAVE and RELOAD while playing and after a boot load",
          all(keys.values()) and len(keys) == 4, f"{keys}")


def elf_symbol(name):
    """A symbol of the runtime the image was built with (out/platform/runtime/runtime.elf), or None."""
    elf = pathlib.Path(os.environ.get("TM_ELF", ROOT / "out/platform/runtime/runtime.elf"))
    if not elf.exists():
        return None
    out = subprocess.run(["m68k-elf-nm", str(elf)], capture_output=True, text=True).stdout
    return next((int(line.split()[0], 16) for line in out.splitlines() if line.endswith(" " + name)), None)


def storage_run(image, work):
    """(g) a power cycle (the battery-RAM cells, settings and random states of one boot written into a fresh boot's
    battery RAM: what a power cycle keeps, DRAM lost) keeps LEN 64, SCAL, DENS and the register; OCTABAM9's cells
    (a valid settings record without the OCTABAM10 flag) are converted: MODE, LOCK, LEN and the 16-bit register
    kept, SCAL 64, DENS 127."""
    sd = 0x51ede0ff
    work.mkdir()
    port = Port(image, work / "a")
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        seed(port, sd)
        port.press("T1")
        page_tracks(port, {1: (True, 40, 64, 100, 30)})
        watch_midi_out(port)
        play_timed(port, 2300)
        kept = (port.peek(CELLS, 12), port.peek(SETTINGS, 32), port.peek(RANDOM, 32))
        first, _n = grid_steps(play_timed(port, 2300), 0, 1)
    finally:
        port.quit()
    port = Port(image, work / "b")
    try:
        fixture(port, (("T1", 1, ()), ("T2", 2, range(1, 17))))
        for at, raw in zip((CELLS, SETTINGS, RANDOM), kept):
            port.cmd(f"poke 0x{at:08x} {raw.hex()}")
        port.press("T1")
        open_turing(port)
        page = drawn(port, lambda: port.enc("B", 1))    # a redraw: LOCK 41 ...
        port.enc("B", -1)                               # ... and back to 40
        check("(g) power cycle: the page shows T1 ON, LOCK 40 (41 while drawn), LEN 64, SCAL 100, DENS 30",
              page.get(0) == ("text", 1) and page.get(1) == ("dial", 41) and page.get(2) == ("text", 64)
              and page.get(3) == ("dial", 100) and page.get(4) == ("dial", 30) and cell(port, 0, 0, 0)["lock"] == 40,
              f"{page}")
        watch_midi_out(port)
        again, _n = grid_steps(play_timed(port, 2300), 0, 1)
        check("(g) power cycle: the same notes and rests as before it (register and random state kept, LOCK 40)",
              again == first and len(first) >= 4, f"{sorted(again.items())[:10]}\n{sorted(first.items())[:10]}")

        cells = elf_symbol("tm_globals")
        label = elf_symbol("tm_label_first")
        if cells is None or label is None or port.peek(label, 12) != b"TURING FIRST":
            check("(g) OCTABAM9 cells: the runtime's symbols (out/platform/runtime/runtime.elf) match the image", False,
                  "build the image first, or set TM_ELF")
            return
        old = bytes([0x80 | (127 ^ 64), 8 ^ 16, 1, 0, 0xa5, 0x3c, 0, 0]) + (0x12345678).to_bytes(4, "big")
        port.cmd(f"poke 0x{cell_address(0, 0, 1):08x} {old.hex()}")
        port.cmd(f"poke 0x{cell_address(0, 0, 0):08x} {bytes(12).hex()}")
        port.cmd(f"poke 0x{SETTINGS:08x} {settings_record({}).hex()}")
        port.cmd(f"poke 0x{cells + 5:08x} 00")         # tm_globals.cells: the first access after a boot
        port.press("T2")
        page = drawn(port, lambda: port.enc("B", 1))    # LOCK 127: a redraw, no change
        c = cell(port, 0, 0, 1)
        check("(g) OCTABAM9 cells converted: T2 ON, LOCK 127, LEN 8, SCAL 64, DENS 127, its 16-bit register kept",
              (c["on"], c["lock"], c["length"], c["scale"], c["density"], c["seeded"], c["bits"]) == (1, 127, 8, 64, 127, 1, 0xa53c)
              and page.get(2) == ("text", 8) and page.get(4) == ("dial", 127) and port.peek(SETTINGS + 20, 1)[0] & 2,
              f"{c} {page}")
        got = [n[0] for _t, n in steps(play_timed(port, 2300), 1)]
        m = Model(0, 1, state=(0xa53c, 1))             # LOCK 127: the random state draws, never flips
        want = [m.note(127, 8) for _ in got]
        check("(g) OCTABAM9 cells converted: T2 plays the old register's locked 8-step phrase (a note every step)",
              len(got) >= 16 and got == want and periodic(got, 8, settle=0), f"{got}\n{want}")
    finally:
        port.quit()


def oldlines_run(image, work):
    """(g) OCTABAM9's and OCTABAM8's project lines load. A project is made and SAVEd on a writable card; its
    project.work's #TURING lines are replaced by lines in the old formats; a fresh boot of a card built from
    that tree loads the project (stock's own load at boot): the cells as each line says, SCAL 64 and DENS 127."""
    sys.path.insert(0, str(ROOT / "tools/emu"))
    import emu_card
    work.mkdir()
    port = Port(image, work / "a", writable=True)
    try:
        if (pathlib.Path(os.environ.get("TM_OLDLINES_TREE", work / "tree")) / ".saved").exists():
            raise StopIteration                         # a tree kept from an earlier run (TM_OLDLINES_TREE)
        port.run(1000)
        port.press("NO")
        project_menu(port, 6)
        port.press("YES")
        port.run(1000)
        for _ in range(5):
            port.press("YES")
            port.run(2500)
        settle_card(port, at_least_ms=25000)
        midi_mode(port)
        port.press("T1")
        page_tracks(port, {1: (True, 127, 8)})
        project_menu(port, 1)
        port.press("YES")
        settle_card(port, at_least_ms=20000)
    except StopIteration:
        pass
    finally:
        port.quit()
    tree = pathlib.Path(os.environ.get("TM_OLDLINES_TREE", work / "tree"))
    if not (tree / ".saved").exists():
        emu_card.extract_image(port.card.read_bytes(), str(tree))
    works = [f for f in tree.rglob("*") if f.name.lower() == "project.work"]
    if len(works) != 1:
        check("(g) old project lines: one project.work on the saved card", False, f"{works}")
        return
    old = ["#TURING_B1_P1_T1=1,127,8,42300,4660,22136", "#TURING_B1_P2_T2=1,100,5", "#TURING_T3=1,30,12"]
    lines = [line for line in works[0].read_bytes().decode("latin1").split("\r\n") if not line.startswith("#TURING")]
    at = next(i for i, line in enumerate(lines) if line.startswith("PATTERN_CHANGE_AUTO_SILENCE_TRACKS=")) + 1
    works[0].write_bytes("\r\n".join(lines[:at] + old + lines[at:]).encode("latin1"))
    (tree / ".saved").write_text("kept by oldlines_run\n")
    project_dir = works[0].parent                       # <SET>/<PROJECT>: the port loads it after the boot
    port = Port(image, work / "b", tree=tree,
                extra=("--mount", "--set", project_dir.parent.name, "--project", project_dir.name))
    try:
        port.run(3000)
        settle_card(port, at_least_ms=8000)
        got = {(b, q, t): cell(port, b, q, t) for b, q, t in ((0, 0, 0), (0, 1, 1), (0, 0, 2), (5, 9, 2), (0, 0, 1))}
        pick = lambda c: (c["on"], c["lock"], c["length"], c["scale"], c["density"], c["seeded"], c["bits"])
        want = {(0, 0, 0): (1, 127, 8, 64, 127, 1, 42300), (0, 1, 1): (1, 100, 5, 64, 127, 0, 0),
                (0, 0, 2): (1, 30, 12, 64, 127, 0, 0), (5, 9, 2): (1, 30, 12, 64, 127, 0, 0),
                (0, 0, 1): (0, 64, 16, 64, 64, 0, 0)}
        check("(g) OCTABAM9 project lines load at boot (A01 T1 1,127,8 + its 16-bit register; A02 T2 1,100,5) and "
              "OCTABAM8's #TURING_T3=1,30,12 into every pattern of T3: SCAL 64, DENS 127; T2 of A01 the defaults",
              {k: pick(v) for k, v in got.items()} == want, f"{ {k: pick(v) for k, v in got.items()} }")
        # Playing the loaded register is storage_run's (a converted OCTABAM9 cell plays its phrase): after the
        # port's own project load the fixture's channel edits do not land (they read back 0), so nothing here
        # would reach MIDI OUT.
    finally:
        port.quit()


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
    only = set(filter(None, os.environ.get("TM_ONLY", "").split(",")))   # e.g. TM_ONLY=lock,reload: those runs alone
    want = lambda name: not only or name in only
    phrases, fixed = [], None
    with tempfile.TemporaryDirectory(prefix="verify-turing.") as td:
        at = lambda name: pathlib.Path(td) / name
        if want("replace"):
            fixed = replace_run(image, at("replace"))
            for i, wait in enumerate((500, 2700)):
                phrases.append(timer_seed_run(image, at(f"timer{i}"), wait))
        runs = (("project", project_run), ("page", page_run), ("locks", locks_run), ("nei", nei_run),
                ("range", range_run), ("range", lambda i, w: range_model_check()), ("arp", arp_run), ("lfo", lfo_run),
                ("clock", clock_run), ("pattern", pattern_run), ("model", lambda i, w: lock_model_check()),
                ("model", lambda i, w: scale_model_check()), ("model", lambda i, w: density_model_check()),
                ("model", lambda i, w: fresh_model_check()), ("lock", lock_run), ("live", live_length_run),
                ("fresh", fresh_run), ("scale", scale_run), ("density", density_run), ("write", write_run),
                ("flags", write_flags_check), ("toggle", toggle_run), ("storage", storage_run),
                ("reload", reload_run), ("oldlines", oldlines_run))
        for n, (name, run) in enumerate(runs):
            if want(name):
                run(image, at(f"{name}{n}"))
        if not want("stock"):
            pass
        elif STOCK.exists():
            ours = stock_run(image, at("ours"), True)
            stock = stock_run(STOCK, at("stock"), False)
            # Messages, not raw bytes: stock repeats a running-status byte at points that differ run to run
            # (write_run's note; diag/octabam10/probe_rs.py).
            full = lambda w: [m[1:] for m in messages([(0, x) for x in w])]
            check("MODE OFF: MIDI OUT messages identical to stock 1.40C (running status written out)",
                  full(ours[0]) == full(stock[0]) and len(full(stock[0])) > 50,
                  f"{len(full(ours[0]))} vs {len(full(stock[0]))} messages, first difference at "
                  f"{next((i for i, (x, y) in enumerate(zip(full(ours[0]), full(stock[0]))) if x != y), None)}")
            print(f"    MODE OFF: raw wire {len(ours[0])} vs stock {len(stock[0])} bytes, "
                  f"{'identical' if ours[0] == stock[0] else 'running status repeated at different points'}")
            count = lambda w: collections.Counter(x for x in w if x >= 0xf8)
            o, k = count(ours[1]), count(stock[1])
            check("T1 ON, CLOCK SEND: F8 as stock, one FA and one FC", abs(o[0xf8] - k[0xf8]) <= 1 and k[0xf8] > 100
                  and o[0xfa] == k[0xfa] == 1 and o[0xfc] == k[0xfc] == 1, f"ours {dict(o)} stock {dict(k)}")
            check("T1 ON, CLOCK SEND: sequencer tick ISRs as stock", abs(ours[2] - stock[2]) <= 1 and stock[2] > 300,
                  f"ours {ours[2]} stock {stock[2]}")
            check("T1 ON, CLOCK SEND: T1 plays one note a step, as many as T2",
                  len(track_ons(notes(ours[1]), 0)) == len(track_ons(notes(ours[1]), 1)) >= 16,
                  f"T1 {len(track_ons(notes(ours[1]), 0))} T2 {len(track_ons(notes(ours[1]), 1))}")
        else:
            check("stock 1.40C reference (out/raw/section_3_MAIN_OS.bin) present", False, "make os && make recon")
    if want("replace"):
        check("timer seed: two boots, PLAY at different moments, different first phrases",
              phrases[0] != phrases[1], f"{phrases}")
        check("timer seed: neither boot plays the test seed's phrase", fixed not in phrases, f"{fixed} in {phrases}")
    if failures:
        raise SystemExit(f"verify_turing: {len(failures)} check(s) failed")
    print("verify_turing: all checks passed under the ColdFire port")


if __name__ == "__main__":
    main()
