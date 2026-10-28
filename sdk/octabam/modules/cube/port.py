"""The ColdFire port for CUBE's gates: ot_emu --interactive on a scratch card
(tools/emu/ot_emu/main.cpp), with an LCD plane file, its stderr kept in
work/port.err, MAIN posted at 64 (an interactive port with `--main-level off`
mixes every track to nothing), and helpers for keys, encoders, audio, DSP
memory, runtime symbols and the card. Self-contained: CUBE's gates need no
other module."""
import os
import pathlib
import selectors
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/emu"))
import lcd_view  # noqa: E402

EMU = ROOT / "out/emu/ot_emu"
KEYS = {"FUNC": 0x2d, "SRC": 0x22, "YES": 0x31, "NO": 0x32, "UP": 0x33, "DOWN": 0x20,
        "LEFT": 0x34, "RIGHT": 0x21, "MENU": 0x1c, "MIDI": 0x35, "REC": 0x29,
        "PLAY": 0x28, "STOP": 0x27, "AMP": 0x23, "PAGE": 0x1b, "LFO": 0x24, "FX1": 0x25, "FX2": 0x26,
        "PATTERN": 0x2e,
        **{f"TRIG{i + 1}": i for i in range(16)}, **{f"T{i + 1}": 0x10 + i for i in range(8)}}
ENCODERS = {name: i for i, name in enumerate("ABCDEF")} | {"LEVEL": 6}


def symbols(elf):
    out = {}
    for line in subprocess.run(["m68k-elf-nm", str(elf)], capture_output=True, text=True).stdout.splitlines():
        f = line.split()
        if len(f) == 3:
            out[f[2]] = int(f[0], 16)
    return out


class Port:
    def __init__(self, image, work, elf=None, writable=False, extra=(), card=None):
        import emu_card
        image, work = pathlib.Path(image).resolve(), pathlib.Path(work).resolve()
        work.mkdir(parents=True, exist_ok=True)
        self.work = work
        self.card = work / "card.img"
        if card is not None:
            self.card.write_bytes(pathlib.Path(card).read_bytes())
        else:
            (work / "tree").mkdir(exist_ok=True)
            self.card.write_bytes(emu_card.build_image(str(work / "tree"), 32))
        self.lcdfile = work / "lcd.bin"
        cmd = [str(EMU), "--image", str(image), "--card", str(self.card), "--dsp", "--frame", "--ms", "3000",
               "--interactive", "--main-level", "64", "--rtc", "off", "--mkii", "--lcd", str(self.lcdfile)] \
            + (["--card-rw"] if writable else []) + list(extra)
        self.err = open(work / "port.err", "w")
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, cwd=work)
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.p.stdout, selectors.EVENT_READ)
        self.pending, self.rows = b"", [0] * 8
        self.sym = symbols(elf) if elf else {}
        self.reply((b"ready ",), 900)

    def reply(self, prefixes, timeout=600):
        deadline = time.monotonic() + timeout
        while True:
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                if line.startswith(prefixes):
                    if line.startswith(b"err"):
                        raise SystemExit(f"cube port: the port refused a command: {line.decode()}")
                    return line.decode()
            if time.monotonic() > deadline or self.p.poll() is not None:
                raise SystemExit("cube port: the port stopped answering")
            if self.sel.select(timeout=1):
                chunk = os.read(self.p.stdout.fileno(), 1 << 16)
                if not chunk:
                    raise SystemExit("cube port: the port exited")
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

    def push(self, name, ms=150):
        """An encoder's push: down, held `ms`, up (the encoder's switch is a key code 0x38 + its index)."""
        code = 0x38 + ENCODERS[name]
        self.rows[code >> 3] |= 1 << (code & 7)
        self.cmd(f"key {0x20 | (code >> 3)} {self.rows[code >> 3]}")
        self.run(ms)
        self.rows[code >> 3] &= ~(1 << (code & 7))
        self.cmd(f"key {0x20 | (code >> 3)} {self.rows[code >> 3]}")
        self.run(200)

    def peek(self, addr, length):
        return bytes.fromhex(self.cmd(f"peek 0x{addr:08x} {length}", b"peek").split(" ", 1)[1])

    def card_files(self):
        import emu_card
        return emu_card.extract_image(self.card.read_bytes())

    def screen(self):
        self.run(150)
        return lcd_view.screen(lcd_view.read_plane(self.lcdfile))

    def shot(self, path, scale=4):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        lcd_view.png(self.screen(), str(path), scale)

    def long(self, name, n=1):
        b = self.peek(self.sym[name], 4 * n)
        v = [int.from_bytes(b[4 * i:4 * i + 4], "big") for i in range(n)]
        return v[0] if n == 1 else v

    def dsp(self, core, space, addr, n):
        out = []
        while n > 0:
            k = min(n, 4096)
            out += [int(w, 16) for w in self.cmd(f"dsp peek {core} {space} {addr:#x} {k}", b"dsp").split()[1:]]
            addr += k
            n -= k
        return out

    def audio(self, words):
        """Every frame captured so far: lists of `words` int16 (tracks mode: 8 ESAI slots, then T1L T1R .. T8L T8R)."""
        out = []
        while True:
            line = self.cmd("audio read 44100", b"audio")
            f = line.split(" ", 2)
            n = int(f[1])
            if n == 0:
                break
            h = f[2]
            v = [int.from_bytes(bytes.fromhex(h[i:i + 4]), "little", signed=True) for i in range(0, len(h), 4)]
            out += [v[k * words:(k + 1) * words] for k in range(n)]
        return out

    def part(self):
        blob = int.from_bytes(self.peek(0x46c82456, 4), "big")
        pi = self.peek(0x100b14cf, 1)[0] & 3
        return blob + 0x8ed80 + pi * 6322

    def part_bytes(self):
        return self.peek(self.part(), 0x300)

    def quit(self):
        """quit, and keep what the port printed after it (its end report: the stopwatch) in .tail."""
        self.tail = ""
        try:
            self.p.stdin.write(b"quit\n")
            self.p.stdin.flush()
            rest = self.p.stdout.read()
            self.p.wait(timeout=120)
            self.tail = (self.pending + rest).decode(errors="replace")
        finally:
            self.err.close()


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
    raise SystemExit(f"cube port: the card was still being written after {at_most_ms} ms")


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
