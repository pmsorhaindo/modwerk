#!/usr/bin/env python3
"""CUBE's DSP source package: cube_engine.asm assembled, disassembled and
made relocatable.

    python3 modules/cube/cube_pkg.py          print words, relocations, loop counts

package() -> dict(words, relocations, init, proc): the engine at origin 0.
It is assembled at two origins; a word that differs must differ by exactly
the distance (an absolute P address inside the package: a DO loop's end) and
becomes a relocation, which the ColdFire adds the arena address to when it
sends the word (transfer.c packet()); every other word must be identical.
A third and a fourth assembly at other origins must equal the relocated
words. Every assembly is disassembled and compared with what was typed
(AGENTS.md: dsp_asm mis-encodes silently); the only su multiply allowed is
the interpolation's `macsu x0,y0,a` (x0 the signed half-difference, y0 the
unsigned frac).

loops() -> {name: words}: the per-sample DO bodies (the modelled cycles:
one word, one cycle; the counter refuses a branch or a nested loop inside).
"""
import pathlib
import re
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = HERE / "cube_engine.asm"
SEAM = HERE / "cube_seam.asm"
DSP_ASM = ROOT / "vendor/dsp56300/build/source/dsp_host/dsp_asm"
DISASM = ROOT / "vendor/dsp56300/build/source/disassemble/dsp56kDisassemble"
BAD = re.compile(r"\b(mpysu|macsu|mpyuu|macuu|max|maxm|rnd)\b")
ALLOWED_SU = {("macsu", "x0,y0,a")}
LINE = re.compile(r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$")
CUBE_ID = 0x1F
LOOPS = {"pass B": ("ce22", "do      n7,ce22"), "pass B hard": ("ce24", "do      n7,ce24"),
         "pass A": ("ce26", "do      n7,ce26"), "pass A hard": ("ce28", "do      n7,ce28")}


def _decoded(text):
    return {int(m.group(1), 16): (m.group(2), (m.group(3) or "").strip())
            for m in map(LINE.match, text.splitlines()) if m}


def assemble(src, org, name="cube"):
    """(words, symbols) at org, decode-checked."""
    with tempfile.TemporaryDirectory() as tmp:
        asm, binf, sym = (pathlib.Path(tmp) / f"{name}{e}" for e in (".asm", ".bin", ".sym"))
        asm.write_text(src)
        r = subprocess.run([str(DSP_ASM), "-in", str(asm), "-org", f"{org:x}", "-out", str(binf),
                            "-list", "-sym", str(sym)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stdout[-3000:] + r.stderr[-2000:])
        listing = r.stdout
        symbols = {n: int(a, 16) for n, a in (l.split() for l in sym.read_text().splitlines())}
        blob = binf.read_bytes()
        d = subprocess.run([str(DISASM), "-in", str(binf), "-pc", f"{org:x}", "-le"],
                           capture_output=True, text=True)
    words = [blob[i] | blob[i + 1] << 8 | blob[i + 2] << 16 for i in range(0, len(blob), 3)]
    typed, dec = _decoded(listing), _decoded(d.stdout)
    assert typed and len(dec) >= len(typed) * 0.9, "no decode to compare"
    norm = lambda op: re.sub(r"\s+", "", op.split(";")[0]).replace("#>", "#").replace("#<", "#").lower()
    bad = []
    for a, (m, op) in typed.items():
        dm, dop = dec.get(a, ("?", ""))
        su_ok = (dm, norm(dop)) in {(k, norm(v)) for k, v in ALLOWED_SU} and m == dm
        if (BAD.search(dm) and not su_ok) or dm != m:
            bad.append((a, m, op, dm, dop))
        elif m not in ("bsr", "bra", "beq", "bne", "blt", "bge", "jsr", "jmp", "do", "rep") \
                and norm(op) != norm(dop) and not re.search(r"#|\$", op):
            bad.append((a, m, op, dm, dop))
    if bad:
        raise RuntimeError("disassemble-what-you-assemble:\n" + "\n".join(
            f"  P:{a:06x} typed {m} {op}  decodes {dm} {dop}" for a, m, op, dm, dop in bad))
    return words, symbols


def package():
    src = SRC.read_text()
    o1, o2 = 0x1000, 0x1400
    w1, s1 = assemble(src, o1)
    w2, s2 = assemble(src, o2)
    if len(w1) != len(w2):
        raise SystemExit("cube_pkg: the engine's length changes with its origin")
    words, rel = [], []
    for k, (a, b) in enumerate(zip(w1, w2)):
        if a == b:
            words.append(a)
        elif b - a == o2 - o1 and o1 <= a < o1 + len(w1):
            words.append(a - o1)
            rel.append(k)
        else:
            raise SystemExit(f"cube_pkg: word {k} moves by {b - a:#x}, not {o2 - o1:#x}")
    for o in (0x1a00, 0x1d40):
        w, _ = assemble(src, o)
        moved = [(v + o) & 0xffffff if k in rel else v for k, v in enumerate(words)]
        if moved != w:
            raise SystemExit(f"cube_pkg: the relocated package differs from an assembly at {o:#x}")
    init, proc = s1["ce00"] - o1, s1["ce01"] - o1
    return dict(words=words, relocations=rel, init=init, proc=proc, symbols={k: v - o1 for k, v in s1.items()})


def loops():
    """Words in each per-sample DO body: a label is injected right after the
    DO (labels emit no words; cycle_count.py's method) and the span to the
    loop's end label is the count. The body must be straight-line."""
    text = SRC.read_text().splitlines()
    marked, marks = [], {}
    for line in text:
        marked.append(line)
        for n, (name, (end, do_line)) in enumerate(LOOPS.items()):
            if line.strip() == do_line.strip():
                marked.append(f"cx{n + 1:02d}:")
                marks[name] = (f"cx{n + 1:02d}", end)
    _w, sym = assemble("\n".join(marked) + "\n", 0x1000)
    out = {}
    for name, (mark, end) in marks.items():
        i = next(k for k, l in enumerate(marked) if l == mark + ":")
        j = next(k for k, l in enumerate(marked) if l.startswith(end + ":"))
        body = [l.split(";")[0].strip() for l in marked[i + 1:j]]
        if any(re.match(r"(b[a-z]+|j[a-z]+|do|rep)\b", c) for c in body if c):
            raise SystemExit(f"cube_pkg: {name} has a branch or a nested loop")
        out[name] = sym[end] - sym[mark]
    return out


def seam(cont, nullproc, org):
    src = SEAM.read_text().replace("CONTADDR", f"${cont:x}").replace("NULLPROC", f"${nullproc:x}")
    return assemble(src, org, "seam")


def charge(cycles):
    """dsp.c: a modelled price is charged at 7/4."""
    return (cycles * 7 + 3) // 4


if __name__ == "__main__":
    pkg = package()
    print(f"engine: {len(pkg['words'])} words, {len(pkg['relocations'])} relocations "
          f"({pkg['relocations']}), init +{pkg['init']}, proc +{pkg['proc']}")
    lp = loops()
    for k, v in lp.items():
        print(f"  {k:12s} {v} words/sample")
    for name, parts in (("LIN/EXP/OFF, FREE/TRIG", ("pass B", "pass A")), ("SYNC HARD", ("pass B hard", "pass A hard"))):
        c = sum(lp[p] for p in parts)
        print(f"  {name:24s} {c} modelled cycles/sample, charged {charge(c)}")
    w, s = seam(0x426, 0x7c9, 0x1000)
    print(f"seam stub: {len(w)} words")
