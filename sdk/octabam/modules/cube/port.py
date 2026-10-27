"""The ColdFire port for CUBE's gates: modules/turing-machine/verify.Port with
an LCD plane file, its stderr kept in work/port.err, MAIN posted at 64 (an
interactive port with `--main-level off` mixes every track to nothing), the
input tones on, and helpers for audio, DSP memory and runtime symbols."""
import os
import pathlib
import selectors
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/turing-machine"))
sys.path.insert(0, str(ROOT / "tools/emu"))
import verify as V  # noqa: E402
import lcd_view  # noqa: E402

V.KEYS.update({"AMP": 0x23, "LFO": 0x24, "FX1": 0x25, "FX2": 0x26})


def symbols(elf):
    out = {}
    for line in subprocess.run(["m68k-elf-nm", str(elf)], capture_output=True, text=True).stdout.splitlines():
        f = line.split()
        if len(f) == 3:
            out[f[2]] = int(f[0], 16)
    return out


class Port(V.Port):
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
        cmd = [str(V.EMU), "--image", str(image), "--card", str(self.card), "--dsp", "--frame", "--ms", "3000",
               "--interactive", "--main-level", "64", "--rtc", "off", "--mkii", "--lcd", str(self.lcdfile)] \
            + (["--card-rw"] if writable else []) + list(extra)
        self.err = open(work / "port.err", "w")
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, cwd=work)
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.p.stdout, selectors.EVENT_READ)
        self.pending, self.rows = b"", [0] * 8
        self.sym = symbols(elf) if elf else {}
        self.reply((b"ready ",), 900)

    def screen(self):
        self.run(150)
        return lcd_view.screen(lcd_view.read_plane(self.lcdfile))

    def shot(self, path, scale=4):
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
