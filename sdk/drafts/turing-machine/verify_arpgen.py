#!/usr/bin/env python3
"""Exercise the existing Turing engine gate through its new generator UI.

The historical engine assertions are retained; approved FUNC UI and package-dispatch edits are documented in TESTING.md. This adapter selects TURING in
NOTE SETUP instead of using the retired AMP ring, and addresses shared Part
settings in fixtures. Tests for retired ARP/ring/storage contracts are replaced
by the explicit S2 checks below, never counted as passing unchanged.
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('turing_legacy_gate', HERE / 'verify.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def part_address(port, bank, pattern):
    part = port.peek(0x400e21e0 + bank * 635712 + pattern * 36568 + 0x8e57, 1)[0] & 3
    return 0x400e21e0 + bank * 635712 + 0x8ed80 + part * 6322


def current_part(port):
    bank = int.from_bytes(port.peek(0x46c82456, 4), 'big')
    return bank + 0x8ed80 + (port.peek(0x100b14cf, 1)[0] & 3) * 6322


def choose(port):
    track = port.peek(0x100b14cc, 1)[0]
    setup = int.from_bytes(port.peek(0x400bc6c0,4),'big')
    if port.peek(current_part(port) + 0x1822 + 2 * track, 2) == b'M\x01':
        if setup:
            port.press('NO')
        return
    # A recent second press of TRACK may already have opened NOTE SETUP.
    if not setup:
        port.press('FUNC', 'SRC')
    port.press('DOWN')
    port.press('YES')
    port.press('NO')
    v.check('NOTE SETUP chooses TURING on this Part/track',
            port.peek(current_part(port) + 0x1822 + 2 * track, 2) == b'M\x01')


def open_turing(port):
    v.dismiss_windows(port)
    choose(port)
    # A direct-backend saved-card boot can retain the stock page's input
    # layer. Re-enter through real SRC/AMP keys so the unmodified host owns
    # the page before a fixture turns any encoder.
    port.press('SRC')
    v.page_key(port)
    # NO on the first page forwards to stock. Avoid injecting an unrelated
    # key event into a wire capture; use NO only to leave page two.
    second = int.from_bytes(port.peek(v.elf_symbol('mg_second'),4),'big')
    if second:
        port.press('NO')
    assert port.peek(v.elf_symbol('tm_ui'),1)==b'\x01', 'Turing page did not acquire its input layer'


def page_tracks(port, tracks):
    for track, values in tracks.items():
        port.press(f'T{track}')
        open_turing(port)
        v.set_page(port, *values)


raw_poke_cell, raw_cell = v.poke_cell, v.cell
legacy_open_turing, legacy_page_tracks = v.open_turing, v.page_tracks
legacy_write_trigs = v.write_trigs


def poke_cell(port, bank, pattern, track, on, lock, length, state=None, scale=64, density=127):
    raw_poke_cell(port, bank, pattern, track, on, lock, length, state, scale, density)
    address = part_address(port, bank, pattern)
    port.cmd(f'poke {address + 0x1822 + 2 * track:#x} 4d01')
    # Legacy engine fixtures reset engine settings, not the independently selected KEY.
    # Keep the generator's equivalent SCALE/ROOT when this Part already has S2 settings.
    prior = port.peek(address + 0x1832 + 16 * track, 8)
    quant = [((n + 64) & 127) for n in prior[4:6]] if prior[6:8] == bytes((193, 245)) else [0, 0]
    values = [lock, length, scale, density, *quant, 1, 53]
    data = bytes((n - 64) & 255 for n in values) + bytes(8)
    port.cmd(f'poke {address + 0x1832 + 16 * track:#x} {data.hex()}')


def cell(port, bank, pattern, track):
    answer = raw_cell(port, bank, pattern, track)
    address = part_address(port, bank, pattern) + 0x1832 + 16 * track
    data = port.peek(address, 8)
    if data[6:8] == bytes((193, 245)):
        answer.update(zip(('lock', 'length', 'scale', 'density'), ((n + 64) & 127 for n in data[:4])))
    return answer


def s2_run(image, work):
    port = v.Port(image, work)
    try:
        v.fixture(port, (('T1', 1, ()), ('T2', 2, range(1, 17))))
        v.seed(port, 0x13572468)
        page_tracks(port, {1: (True, 127, 16, 64, 127)})
        p = current_part(port)
        initial = port.peek(p + 0x1832, 16)
        v.check('S2 settings occupy signed-valid arp notes',
                all(n < 64 or n >= 192 for n in initial)
                and initial[:4] == bytes((63, 208, 0, 63)))
        port.enc('B', -63)
        port.enc('B', 63)
        v.check('Plain encoder B sets LOCK 64 to 127',port.peek(p + 0x1832,1) == bytes((63,)))
        before = raw_cell(port, 0, 0, 0)
        port.press('FUNC', 'AMP')
        port.enc('A', 1)  # SCALE MAJ
        port.enc('B', 2)  # ROOT D
        quant = port.peek(p + 0x1832, 16)
        v.check('FUNC+AMP edits own SCALE/ROOT only',
                quant[:4] == initial[:4] and quant[4:6] == bytes((193,194)))
        port.press('NO')
        port.enc('A', 4)
        after = raw_cell(port, 0, 0, 0)
        v.check('MODE stays per pattern; Part settings survive MODE edits',
                before['on'] == after['on'] == 1 and port.peek(p + 0x1832, 16) == quant)
        v.watch_midi_out(port)
        events = v.play_timed(port, 4300)
        notes = v.onsets(events, 0)
        v.check('D major: all generated output belongs to own key',
                len(notes) >= 16 and all((n - 2) % 12 in (0,2,4,5,7,9,11) for _, n, _ in notes))
        port.press('SRC')
        source_before = port.peek(p + 0x3e2, 12)
        port.enc('A', 1)
        source_after = port.peek(p + 0x3e2, 12)
        v.check('SRC remains the stock NOTE page', source_after[0] != source_before[0]
                and source_after[1:] == source_before[1:])
    finally:
        port.quit()


def call(port, name, *args):
    command = 'call ' + hex(v.elf_symbol(name)) + ''.join(' ' + hex(x) for x in args)
    reply = port.cmd(command)
    if 'err' in reply:
        raise RuntimeError(reply)
    return int(reply.split('d0=')[1], 16)


def line(port, text):
    address = 0x47eff000
    port.cmd(f'poke {address:#x} {(text.encode() + bytes(1)).hex()}')
    call(port, 'tm_project_line', address, 0)


def migration_run(image, work):
    """Execute the real loader callbacks; no host reimplementation of migration."""
    port = v.Port(image, work)
    try:
        port.run(1000)
        port.press('NO')
        call(port, 'tm_project_begin')
        bank = 0x400e21e0
        for q, part in ((0,0), (1,0), (2,1)):
            port.cmd(f'poke {bank + q * 36568 + 0x8e57:#x} {part:02x}')
        part0, part1 = bank + 0x8ed80, bank + 0x8ed80 + 6322
        for part in (part0, part1):
            port.cmd(f'poke {part + 0x1822:#x} ffff')
        port.cmd(f'poke {part0 + 0x3e2 + 12:#x} 460003')  # TRAN +6; old arp UP
        port.cmd(f'poke {part0 + 0x4e2 + 17:#x} 05')  # D major
        line(port, '#TURING_B1_P1_T1=0,64,16,64,64')
        line(port, '#TURING_B1_P2_T1=1,127,5,100,30,4660,22136,48879,1')
        line(port, '#TURING_B1_P3_T1=1,80,64,127,96,1,2,3,4')
        line(port, '#TURING_FIRST=1')
        call(port, 'tm_generator_tick')
        v.check('Migration waits until banks finish loading', port.peek(part0 + 0x1822, 2) == b'\xff\xff')
        call(port, 'tm_project_loaded', 1)
        call(port, 'tm_generator_tick')
        p0, p1 = port.peek(part0 + 0x1832, 8), port.peek(part1 + 0x1832, 8)
        v.check('Any enabled pattern migrates its Part; first enabled settings win',
                port.peek(part0 + 0x1822, 2) == port.peek(part1 + 0x1822, 2) == b'M\x01'
                and tuple((x + 64) & 127 for x in p0[:6]) == (127,5,100,30,1,2)
                and tuple((x + 64) & 127 for x in p1[:4]) == (80,64,127,96))
        v.check('Migration preserves TRAN/KEY, forces arp off, ignores FIRST',
                port.peek(part0 + 0x3e2 + 12, 3) == bytes((70,0,0))
                and port.peek(part0 + 0x4e2 + 17, 1) == b'\x05'
                and not (port.peek(v.SETTINGS + 20, 1)[0] & 1))
        c0, c1, c2 = (raw_cell(port,0,q,0) for q in range(3))
        v.check('Migration keeps per-pattern MODE and independent 64-bit registers',
                (c0['on'],c1['on'],c2['on']) == (0,1,1)
                and c1['bits'] == 0x12345678beef0001 and c2['bits'] == 0x0001000200030004)
        v.check('Current-bank Part migration updates the battery mirror',
                port.peek(0x100a4ece + 0x1832, 8) == p0)
        note = 0x47eff000
        port.cmd('poke 0x8000666e 00')  # MIDI track's own bank context
        port.cmd('poke 0x80006676 01')  # Part 1 OFF scale, while UI/pattern uses Part 0 D major
        port.cmd(f'poke {note:#x} 00')
        owned = call(port,'tm_note_key',0,note)
        v.check('Quantizer follows the MIDI playing Part, independently of the UI Part',
                owned == 1 and port.peek(note,1) == b'\x00')
        port.cmd('poke 0x80006676 00')
        call(port,'tm_note_key',0,note)
        v.check('Executed local D-major snap drops note zero',port.peek(note,1) == b'\xff')
        call(port, 'tm_project_begin')
        line(port, '#TURING_S2=1')
        port.cmd(f'poke {part0 + 0x1822:#x} ffff')  # a saved OFF choice
        line(port, '#TURING_B1_P2_T1=1,127,5,100,30')
        call(port, 'tm_project_loaded', 1)
        call(port, 'tm_generator_tick')
        v.check('Saved Part OFF wins over legacy MODE ON lines', port.peek(part0 + 0x1822, 2) == b'\xff\xff')
        v.check('Part OFF also bypasses the live generator engine despite pattern MODE ON',
                call(port,'tm_eval',0,0,1,0,0) == 0)
    finally:
        port.quit()


def storage_run(image, work):
    """Execute reset, saved-comment import and playback with base storage poisoned.

    An unsaved fresh boot must start with empty module-owned DRAM, independently
    of the former battery contents. Full file SAVE/RELOAD is the reload run.
    """
    work.mkdir()
    read = lambda port, at, size: b"".join(port.peek(at+i,min(4096,size-i)) for i in range(0,size,4096))
    for boot in range(2):
        port = v.Port(image, work / str(boot))
        try:
            v.check('Fresh loader state is empty DRAM',
                    read(port,v.CELLS,24576) == bytes(24576)
                    and port.peek(v.RANDOM, 32) == bytes(32)
                    and all(0x40000000 <= a < 0x48000000 for a in
                            (v.CELLS, v.SETTINGS, v.TEST_SEED, v.RANDOM)))
            # Include the entire former cell table AND settings/RNG tail.
            start, size = 0x100f9000, 0x7000
            sentinel = bytes((i * 73 + 19) & 255 for i in range(size))
            for at in range(0,size,1024):
                port.cmd(f'poke {start+at:#x} {sentinel[at:at+1024].hex()}')
            call(port,'tm_project_begin')
            line(port,'#TURING_B1_P1_T1=1,127,16,64,127,4660,22136,48879,1')
            line(port,'#TURING_B16_P16_T8=0,64,16,64,64,1,2,3,4')
            call(port,'tm_project_loaded',1)
            call(port,'tm_generator_tick')
            first,last = raw_cell(port,0,0,0),raw_cell(port,15,15,7)
            v.check('Saved comments restore independent first and last pattern registers',
                    first['on'] == 1 and first['bits'] == 0x12345678beef0001
                    and last['on'] == 0 and last['bits'] == 0x0001000200030004)
            call(port,'tm_eval',0,0,0,0,0)
            call(port,'tm_project_defaults')
            v.check('Defaults clear all module cells',read(port,v.CELLS,24576) == bytes(24576))
            v.check('Reset, import, migration and evaluation leave former battery/log/FX storage untouched',
                    read(port,start,size) == sentinel)
            # Leave an unsaved edit: the second boot must not inherit it.
            line(port,'#TURING_B1_P1_T1=1,127,16,64,127,1,2,3,4')
        finally:
            port.quit()


def key_reference_run(image, work, reference):
    """Compare actual fixed-seed UART notes against the previous Turing image."""
    if reference is None:
        raise ValueError('KEY comparison requires --reference-image with the previous private MAIN image.')
    work.mkdir()
    phrases = []
    dram = v.SETTINGS, v.TEST_SEED, v.RANDOM, v.CELLS
    for old, candidate in ((True, reference), (False, image)):
        v.SETTINGS, v.TEST_SEED, v.RANDOM, v.CELLS = ((0x100ffe00,0x100ffe20,0x100ffe40,0x100f9000) if old else dram)
        v.open_turing = legacy_open_turing if old else open_turing
        v.page_tracks = legacy_page_tracks if old else page_tracks
        port = v.Port(candidate, work / ('previous' if old else 'candidate'))
        try:
            v.fixture(port, (('T1',1,()), ('T2',2,range(1,17))))
            v.seed(port,0x13572468)
            v.page_tracks(port,{1:(True,127,16,64,127)})
            part = current_part(port)
            # Activate TRAN through the stock writer, not only its stored copy.
            for address in (part + 0x3e2 + 12, 0x100a4ece + 0x3e2 + 12):
                port.cmd(f'poke {address:#x} 46')
            reply = port.cmd('call 0x40054cd8 0x8 0xc 0x46')
            if 'err' in reply:
                raise RuntimeError(reply)
            if old:
                for address in (part + 0x4e2 + 17, 0x100a4ece + 0x4e2 + 17):
                    port.cmd(f'poke {address:#x} 01')
                v.page_key(port)
                v.double_tap(port)
                port.enc('F', -1)
                port.enc('F', 1)
                port.press('NO')
                port.run(300)
            else:
                port.press('FUNC','AMP')
                port.enc('A',1)
                port.press('NO')
            active = (
                all(port.peek(at, 1) == b'\x46' for at in
                    (part + 0x3e2 + 12, 0x46c76dc0 + 12, 0x46c76fec))
                and port.peek(0x46c7a124, 1) == b'\x00'
                and port.peek(part + 0x3e2, 1) == b'\x30'
                and port.peek(part + 0x3e2 + 14, 1) == b'\x00'
                and (port.peek(0x46c76dc0 + 49, 1) == b'\x01' if old else
                     port.peek(part + 0x1832 + 4, 2) == bytes((193, 192))))
            v.check(('Previous' if old else 'Candidate') + ' live KEY/SCALE/ROOT/TRAN active before PLAY', active)
            if not active:
                raise RuntimeError('KEY reference fixture activation failed')
            v.watch_midi_out(port)
            events = v.play_timed(port,4300)
            own, grid = v.steps(events,0), v.steps(events,1)
            v.check(('Previous' if old else 'Candidate') + ' KEY-only notes stay on stock grid',
                    len(own) >= 32 and v.lockstep(own,grid)[0])
            phrases.append([(note,velocity) for _,note,velocity in v.onsets(events,0)][:32])
        finally:
            port.quit()
    v.open_turing, v.page_tracks = open_turing, page_tracks
    expected = [62,59,53,64,62,57,48,57,48,57,48,53,43,43,47,52] * 2
    v.check('Active previous KEY/TRAN matches approved phrase',
            [note for note, _ in phrases[0]] == expected)
    v.check('Fixed-seed KEY C major + TRAN: 32 actual notes equal the previous Turing image',
            len(phrases[0]) == len(phrases[1]) == 32 and phrases[0] == phrases[1],str(phrases))


def pattern_run(image, work):
    """S2's shared controls, with the original per-pattern MODE/phrase contract."""
    port = v.Port(image,work)
    try:
        v.fixture(port,(('T1',1,()),('T2',2,range(1,17))))
        v.seed(port,0x13572468)
        page_tracks(port,{1:(True,127,16)})
        port.press('PATTERN','TRIG2')
        port.run(500)
        port.enc('B',-27)
        first,second = cell(port,0,0,0),cell(port,0,1,0)
        v.check('Patterns sharing a Part share LOCK; MODE remains independent',
                (first['on'],second['on'],first['lock'],second['lock']) == (1,0,100,100))
        port.enc('B',27)
        port.enc('C',-11)
        v.check('Patterns sharing a Part also share LEN',
                cell(port,0,0,0)['length'] == cell(port,0,1,0)['length'] == 5)
        port.enc('C',11)
        v.place_trigs(port,'T1',(1,5,9,13))
        v.place_trigs(port,'T2',range(1,17))
        port.press('PATTERN','TRIG1')
        port.run(500)
        v.watch_midi_out(port)
        port.writes_timed()
        port.press('PLAY')
        port.run(1000)
        for pattern in ('TRIG2','TRIG1','TRIG2'):
            port.press('PATTERN',pattern)
            port.run(2000)
        port.press('STOP')
        port.run(400)
        events = v.timed_notes(port.writes_timed())
        grid,notes = v.steps(events,1),v.steps(events,0)
        bars = []
        for b in range(len(grid)//16):
            low,high = grid[16*b][0]-v.SAME,grid[16*b+15][0]+v.SAME
            bars.append([(v.grid_index(grid,t)-16*b,n) for t,n in notes if low <= t <= high])
        kinds = ['A01' if len(bar)==16 and all(len(n)==1 for _,n in bar) else
                 'A02' if [p for p,_ in bar]==[0,4,8,12]
                 and all(n==(v.NOTE_C3,v.NOTE_C3+7) for _,n in bar) else '?' for bar in bars]
        joined = ''.join(k[-1] for k in kinds)
        v.check('Pattern changes alternate Turing and stock bars, with no mixed bar',
                '?' not in kinds and '121' in joined and joined.startswith('1'),str((kinds,bars)))
        generated = [[n[0] for _,n in bar] for bar,k in zip(bars,kinds) if k=='A01']
        model = v.Model(0x13572468,0)
        expected = [[model.note(127,16) for _ in range(16)] for _ in generated]
        v.check('Returning to the pattern preserves its independent locked phrase',
                generated and generated==expected and all(bar==generated[0] for bar in generated))
        v.check('Only the enabled pattern seeds its register',
                raw_cell(port,0,0,0)['seeded'] and not raw_cell(port,0,1,0)['seeded'])
    finally:
        port.quit()


def timer_run(image, work):
    work.mkdir()
    phrases = [v.timer_seed_run(image,work/str(i),delay) for i,delay in enumerate((500,2700))]
    v.check('Timer-seeded boots at different PLAY times give different phrases',
            phrases[0] and phrases[1] and phrases[0] != phrases[1],str(phrases))


def write_trigs(image, work):
    """The historical flags gate also boots OCTABAM10, which still has its ring."""
    if Path(image).resolve() == (v.ROOT / 'out/turing_10.bin').resolve():
        v.open_turing, v.page_tracks = legacy_open_turing, legacy_page_tracks
        dram = v.SETTINGS, v.TEST_SEED, v.RANDOM, v.CELLS
        v.SETTINGS, v.TEST_SEED, v.RANDOM, v.CELLS = 0x100ffe00,0x100ffe20,0x100ffe40,0x100f9000
        try:
            return legacy_write_trigs(image,work)
        finally:
            v.SETTINGS, v.TEST_SEED, v.RANDOM, v.CELLS = dram
            v.open_turing, v.page_tracks = open_turing, page_tracks
    return legacy_write_trigs(image,work)



def oldlines_run(image, work):
    """Keep the legacy parser assertion on imported DRAM cells, then check S2's shared Part.

    The generic adapter's cell() includes current Part controls. Those are deliberately
    shared after migration, unlike the per-pattern legacy fields this parser gate checks.
    """
    previous = v.cell
    def imported(port, bank, pattern, track):
        result = raw_cell(port, bank, pattern, track)
        if (bank, pattern, track) == (0, 0, 1):
            a, b = cell(port, 0, 0, 1), cell(port, 0, 1, 1)
            fields = lambda c: tuple(c[k] for k in ('on', 'lock', 'length', 'scale', 'density'))
            v.check('Legacy file migration: A01/A02 share T2 Part controls, while MODE stays per pattern',
                    part_address(port, 0, 0) == part_address(port, 0, 1)
                    and fields(a) == (0, 100, 5, 64, 127)
                    and fields(b) == (1, 100, 5, 64, 127))
        return result
    v.cell = imported
    try:
        return v.oldlines_run(image, work)
    finally:
        v.cell = previous


def scale_run(image, work):
    """(d) under the port: SCAL 0, 64, 127 on poked registers (NOTE C3) and against the model; SCAL on the page
    (knob D); a NOTE lock (C4 on step 5) centres that step at SCAL 127; generator SCALE quantises SCAL 127."""
    port = v.Port(image, work)
    try:
        v.fixture(port, (("T1", 1, (5,)), ("T2", 2, range(1, 17))))
        port.press("T1")
        port.press("SRC")
        port.press("REC")
        v.hold_lock(port, 5, "A", 12)                     # step 5: NOTE C4
        port.press("REC")
        v.watch_midi_out(port)
        rnd = __import__("random").Random(17)
        results = []
        for scale in (0, 64, 127):
            for lock in (25, 127):
                bits, rng = rnd.getrandbits(64), rnd.getrandbits(32) | 1
                v.poke_cell(port, 0, 0, 0, True, lock, 16, (bits, rng), scale=scale)
                ev = v.play_timed(port, 2300)
                pos, _n = v.grid_steps(ev, 0, 1)
                m = v.Model(0, 0, state=(bits, rng))
                want = {i: m.note(lock, 16, 60 if i % 16 == 4 else v.NOTE_C3, scale) for i in range(max(pos, default=0) + 1)}
                got = {i: n[0] for i, n in pos.items()}
                w = v.span(scale) // 2
                inside = all(c - w <= n <= c + w for i, n in got.items() for c in [60 if i % 16 == 4 else v.NOTE_C3])
                results.append((scale, lock, got == want and len(got) >= 16, inside, min(got.values()), max(got.values())))
        v.check("(d) SCAL 0 / 64 / 127 under the port: every note as the model (NOTE C3, C4 on the NOTE-locked step 5), "
              "within NOTE, +-12, +-24", all(r[2] and r[3] for r in results), f"{results}")
        v.check("(d) SCAL 0: only NOTE (C3, and C4 on the locked step)",
              all(r[4] >= v.NOTE_C3 and r[5] <= 60 for r in results if r[0] == 0), f"{results}")
        v.open_turing(port)
        page = v.drawn(port, lambda: v.turn_to(port, "D", 100))
        c = v.cell(port, 0, 0, 0)
        v.check("(d) SCAL on the page: knob D sets it (100, a dial with its number)", c["scale"] == 100
              and page.get(3) == ("dial", 100), f"{c} {page}")
        # The generator owns its SCALE/ROOT page; stock ARP SETUP is retired here.
        port.press("FUNC", "AMP")
        port.enc("A", 1)
        port.press("NO")
        port.run(300)
        v.check("SCAL fixture: generator SCALE C MAJ / ROOT C active before playback",
                port.peek(current_part(port) + 0x1832 + 4, 2) == bytes((193, 192)))
        bits, rng = rnd.getrandbits(64), rnd.getrandbits(32) | 1
        v.poke_cell(port, 0, 0, 0, True, 64, 16, (bits, rng), scale=127)
        keyed = [n for _t, n, _v in v.onsets(v.play_timed(port, 2300), 0)]
        v.check("(d) SCAL 127 with generator SCALE C MAJ: every note in C major, the range still wide",
              len(keyed) >= 16 and all(n % 12 in {0, 2, 4, 5, 7, 9, 11} for n in keyed) and max(keyed) - min(keyed) >= 24,
              f"{keyed}")
    finally:
        port.quit()

def func_contract_run(image, work):
    """Approved stock-host UI: FUNC yields; release before SCALE/ROOT edits."""
    port = v.Port(image, work)
    try:
        v.fixture(port, (('T1', 1, ()),))
        open_turing(port)
        port.enc('B', -127)
        port.enc('B', 64)
        part = current_part(port)
        settings = port.peek(part + 0x1832, 16)
        port.key('FUNC', True, 60)
        v.drawn(port, lambda: port.enc('B', 1))
        v.check('Held FUNC yields the descriptor and leaves Turing LOCK unchanged',
                call(port, 'mg_page', 0x1234) == 0x1234
                and port.peek(part + 0x1832, 16) == settings)
        port.key('FUNC', False, 60)
        shown = v.drawn(port, lambda: port.enc('B', 1))
        v.check('Released FUNC restores LOCK; plain B advances by one, without snapping',
                cell(port, 0, 0, 0)['lock'] == 65 and shown.get(1) == ('dial', 65))
        port.key('FUNC', True, 60)
        port.key('AMP', True, 60)
        port.key('AMP', False, 60)
        v.check('FUNC+AMP yields to stock while FUNC remains held',
                call(port, 'mg_page', 0x1234) == 0x1234)
        port.key('FUNC', False, 60)
        port.enc('A', 1)
        port.enc('B', 2)
        desc = call(port, 'mg_page', 0)
        v.check('After releasing FUNC, second-page SCALE/ROOT edits and labels agree',
                port.peek(part + 0x1832 + 4, 2) == bytes((193,194))
                and desc != 0 and port.peek(desc + 0x16, 5) == b'SCALE'
                and port.peek(desc + 0x1c, 4) == b'ROOT')
    finally:
        port.quit()


def reference_arpgen_run(image,work,reference):
    """Actual MIDI UART equality with the read-only previous generator image."""
    if reference is None:
        raise ValueError('reference run requires --reference-arpgen DIRECTORY')
    work.mkdir()
    phrases=[]
    for tag,candidate in (('reference',reference/'MAIN.raw'),('candidate',image)):
        port=v.Port(candidate,work/tag)
        captured=[]
        def capture():
            port.wire()
            events=v.play_timed(port,4300)
            wire=v.timed_notes(list(enumerate(port.wire())))
            v.check(tag+' actual UART messages equal the timed queue capture',
                    [(k,c,n,vel) for _,k,c,n,vel in wire]
                    ==[(k,c,n,vel) for _,k,c,n,vel in events])
            return events
        try:
            v.fixture(port,(('T1',1,()),('T2',2,range(1,17))))
            v.seed(port,0x13572468)
            page_tracks(port,{1:(True,127,16,64,127)})
            part=current_part(port)
            for at in (part+0x3e2+12,0x100a4ece+0x3e2+12):
                port.cmd(f'poke {at:#x} 46')
            reply=port.cmd('call 0x40054cd8 0x8 0xc 0x46')
            if 'err' in reply:
                raise RuntimeError(reply)
            for scale,root in ((0,0),(1,0),(1,2),(2,0),(2,11)):
                open_turing(port)
                port.press('FUNC','AMP')  # press releases FUNC before edits
                prior=port.peek(part+0x1832+4,2)
                old_scale,old_root=((x+64)&127 for x in prior)
                port.enc('A',scale-old_scale)
                port.enc('B',root-old_root)
                port.press('NO')
                poke_cell(port,0,0,0,True,127,16,(0x12345678beef0001,0x13572469),64,127)
                v.check(tag+f' SCALE {scale} ROOT {root} active before PLAY',
                        port.peek(part+0x1832+4,2)==bytes(((scale-64)&255,(root-64)&255))
                        and port.peek(0x46c76dc0+12,1)==bytes((70,)))
                v.watch_midi_out(port)
                events=capture()
                own,grid=v.steps(events,0),v.steps(events,1)
                v.check(tag+f' SCALE {scale} ROOT {root} has 32 notes on the stock grid',
                        len(own)>=32 and v.lockstep(own,grid)[0])
                captured.append([(n,vel) for _,n,vel in v.onsets(events,0)][:32])
            # Exercise flips, byte-note loops, rests and pitch-range extremes.
            # Both actual firmwares receive the same explicit register/RNG.
            for lock,length,span in ((25,5,0),(25,7,127),(64,5,127),(64,7,0)):
                page_tracks(port,{1:(True,lock,length,span,64)})
                port.press('FUNC','AMP')
                prior=port.peek(part+0x1832+4,2)
                old_scale,old_root=((x+64)&127 for x in prior)
                port.enc('A',-old_scale);port.enc('B',-old_root);port.press('NO')
                # MODE's panel cycle above retires any live register from the
                # previous length. Seed the anchor AND RNG only after that.
                poke_cell(port,0,0,0,True,lock,length,(0x12345678beef0001,0x13572469),span,64)
                config=cell(port,0,0,0)
                v.check(tag+f' unlocked fixture {lock}/{length}/{span}/64 active',
                        (config['on'],config['lock'],config['length'],config['scale'],config['density'],config['bits'])
                        ==(1,lock,length,span,64,0x12345678beef0001),str(config))
                v.watch_midi_out(port)
                events=capture()
                own,grid=v.grid_steps(events,0,1)
                phrase=tuple((i,*own[i]) for i in sorted(own) if i<32)
                v.check(tag+f' unlocked LOCK {lock} LEN {length} SCAL {span} DENS 64 has notes and rests',
                        grid>=32 and 0<len(phrase)<32, f'grid={grid} phrase={phrase} config={cell(port,0,0,0)}')
                captured.append(phrase)
        finally:
            port.quit()
        (work/(tag+'-phrases.json')).write_text(json.dumps(captured,indent=2))
        phrases.append(captured)
    v.check('Fixed register/seed UART equality: OFF/four keys plus unlocked short loops, density and range extremes',
            len(phrases)==2 and phrases[0]==phrases[1] and all(len(p)==32 for p in phrases[1][:5]) and len(phrases[1])==9,str(phrases))


def stock_contract_run(image,work):
    """The historical MODE-OFF messages and transport/ISR checks, unchanged."""
    work.mkdir()
    ours=v.stock_run(image,work/'ours',True)
    stock=v.stock_run(v.STOCK,work/'stock',False)
    full=lambda w: [m[1:] for m in v.messages([(0,x) for x in w])]
    v.check('MODE OFF: MIDI OUT messages identical to stock 1.40C (running status written out)',
            full(ours[0])==full(stock[0]) and len(full(stock[0]))>50,
            f'{len(full(ours[0]))} vs {len(full(stock[0]))} messages')
    count=lambda w: v.collections.Counter(x for x in w if x>=0xf8)
    o,k=count(ours[1]),count(stock[1])
    v.check('T1 ON, CLOCK SEND: F8 as stock, one FA and one FC',
            abs(o[0xf8]-k[0xf8])<=1 and k[0xf8]>100
            and o[0xfa]==k[0xfa]==1 and o[0xfc]==k[0xfc]==1,f'ours {dict(o)} stock {dict(k)}')
    v.check('T1 ON, CLOCK SEND: sequencer tick ISRs as stock',
            abs(ours[2]-stock[2])<=1 and stock[2]>300,f'ours {ours[2]} stock {stock[2]}')
    v.check('T1 ON, CLOCK SEND: T1 plays one note a step, as many as T2',
            len(v.track_ons(v.notes(ours[1]),0))==len(v.track_ons(v.notes(ours[1]),1))>=16)


def review_run(image,work):
    """Panel/UART regressions with the independently packaged Arp Key Locks."""
    port=v.Port(image,work)
    try:
        v.check('Both Turing and Arp Key Locks installed',call(port,'modwerk_runtime_active')==2)
        v.fixture(port,(('T1',1,range(1,17)),('T2',2,range(1,17))))
        port.enc('E',12);port.enc('F',16) # SRC NOT3/NOT4; fixture already sets NOT2
        for step in range(16):
            port.cmd(f'poke {v.BANK0+0x4900+32*step+30:#x} 54ff')
        v.watch_midi_out(port)
        events=v.play_timed(port,4300)
        chord=v.onsets(events,0);grid=v.onsets(events,1)
        v.check('AKL B-Locrian on non-Turing T1 retains NOT2/NOT3/NOT4',
                len(grid)>=32 and len(chord)==4*len(grid),f'{len(chord)} notes / {len(grid)} steps')
        page_tracks(port,{1:(True,127,16,64,127)})
        locks=v.BANK0+0x4900
        for step in range(16):port.cmd(f'poke {locks+32*step+30:#x} 543f')
        saved=[port.peek(locks+32*step+30,2) for step in range(16)]
        v.push_a(port)
        v.check('WRITE leaves all AKL KEY and shift lock bytes unchanged',
                [port.peek(locks+32*step+30,2) for step in range(16)]==saved)
        ui=v.elf_symbol('tm_ui')
        writes=port.peek(ui+24,4)
        port.press('FUNC','SRC')
        v.push_a(port)
        v.check('Encoder A push in NOTE SETUP does not WRITE',port.peek(ui+24,4)==writes)
        port.press('NO');open_turing(port)
        port.press('MENU')
        overlays=port.peek(0x46c7d34c,280)
        assert any(int.from_bytes(overlays[i+32:i+36],'big') & 0x20 for i in range(0,280,56)), 'PROJECT menu must cover the page'
        v.push_a(port)
        v.check('Encoder A push under the PROJECT menu does not WRITE',port.peek(ui+24,4)==writes)
        v.dismiss_windows(port);open_turing(port)
        part=current_part(port)
        settings=port.peek(part+0x1832,16)
        trans=port.peek(part+0x3e2+12,1)[0]
        # Use an unwritten pattern so WRITE-centre persistence is independent.
        port.press('PATTERN','TRIG2');port.run(300)
        open_turing(port)
        part=current_part(port)
        state=(0x12345678beef0001,0x13572469)
        open_turing(port);port.enc('A',-4);port.enc('A',4)
        poke_cell(port,0,1,0,True,127,16,state,64,127)
        v.watch_midi_out(port);port.wire()
        first_events=v.play_timed(port,4300)
        first_wire=port.wire()
        before=[n for _,n,_ in v.onsets(first_events,0)]
        v.check('TRAN before: actual UART messages agree with queued capture',
                [(k,c,n,vel) for _,k,c,n,vel in v.timed_notes(list(enumerate(first_wire)))]
                ==[(k,c,n,vel) for _,k,c,n,vel in first_events])
        port.key('FUNC',True,60);port.enc('A',1);port.key('FUNC',False,60)
        changed=port.peek(part+0x3e2+12,1)[0]
        v.check('Held FUNC edits stock TRAN and leaves Turing Part settings unchanged',
                changed==trans+1 and port.peek(part+0x1832,16)==settings)
        open_turing(port);port.enc('A',-4);port.enc('A',4)
        poke_cell(port,0,1,0,True,127,16,state,64,127)
        v.watch_midi_out(port);port.wire()
        after_events=v.play_timed(port,4300)
        after_wire=port.wire()
        after=[n for _,n,_ in v.onsets(after_events,0)]
        v.check('TRAN after: actual UART messages agree with queued capture',
                [(k,c,n,vel) for _,k,c,n,vel in v.timed_notes(list(enumerate(after_wire)))]
                ==[(k,c,n,vel) for _,k,c,n,vel in after_events])
        v.check('Held-FUNC TRAN transposes the fixed generated phrase by one semitone',
                len(before)>=32 and after==[n+1 for n in before],f'{before[:8]} / {after[:8]}')
    finally:
        port.quit()


def project_change(port, work):
    """Normal UI change; T2 is legacy, T1 already owns retained S2 settings."""
    import lcd_view
    def capture(name):
        data=port.peek(0x46c7e0ea,1024)+port.peek(0x46c7d34c,280)
        data+=b''.join(port.peek(0x460d1f7b+i,min(4096,0x2800-i)) for i in range(0,0x2800,4096))
        lcd_view.png(lcd_view.screen(data),work/(name+'.png'))
    capture('before-change')
    try:
        v.project_menu(port,0)
    finally:
        capture('change-list')
    port.press('DOWN');port.press('YES');port.run(500);capture('change-answer')
    v.settle_card(port,at_least_ms=20000);port.press('NO');port.run(500)
    capture('change-loaded')
    pointer=int(port.cmd('call 0x40025230 0 0').split('d0=')[1],16)
    directory=port.peek(pointer,256).split(b'\0',1)[0]
    v.check('PROJECT CHANGE selected the second saved project',directory.endswith(b'PROJECT 000001'),repr(directory))
    got=cell(port,0,0,1)
    v.check('PROJECT CHANGE imports and migrates legacy T2 settings',
            (got['on'],got['lock'],got['length'],got['scale'],got['density'])==(1,100,5,64,127),str(got))
    retained=cell(port,0,0,0)
    v.check('PROJECT CHANGE preserves already-selected T1 Part settings',
            (retained['lock'],retained['length'],retained['scale'],retained['density'])==(127,8,64,127),str(retained))


def change_run(image, work, kept_tree):
    """Repeat normal project change from a real saved-set writer fixture."""
    import shutil
    work.mkdir();tree=work/'tree';shutil.copytree(kept_tree,tree)
    current=next(f.parent for f in tree.rglob('*') if f.name.lower()=='project.work' and f.parent.name=='PROJECT 000000')
    (current.parent/'AUDIO').mkdir(exist_ok=True)
    legacy=current.parent/'PROJECT 000001'
    saved=next(f for f in legacy.iterdir() if f.name.lower()=='project.work')
    text=saved.read_text(encoding='latin1')
    text='\r\n'.join(line for line in text.splitlines() if not line.startswith('#TURING_'))+'\r\n#TURING_T2=1,100,5\r\n'
    saved.write_bytes(text.encode('latin1'))
    port=v.Port(image,work/'boot',tree=tree,card_megabytes=128,restore_only=True,
                extra=('--mount','--set',current.parent.name,'--project',current.name))
    try:
        v.check('Cached real Kept set restores exact package without reinstall or manual wake',
                call(port,'modwerk_runtime_active')==1
                and int.from_bytes(port.peek(v.elf_symbol('tm_ready_events'),4),'big')>=1)
        v.mounted_startup(port)
        project_change(port,work)
    finally:port.quit()


def lifecycle_run(image,work,kept_tree,legacy_tree):
    """Real card writer, natural Kept restore, then PROJECT CHANGE to legacy.

    --kept-tree is a saved one-project card tree; --legacy-tree supplies a
    second saved stock project. Neither is checked into the repository.
    """
    import shutil
    sys.path.insert(0,str(v.ROOT/'tools/emu'))
    import emu_card
    if kept_tree is None or legacy_tree is None:
        raise ValueError('lifecycle requires --kept-tree and --legacy-tree')
    def project(tree):
        files=[f for f in tree.rglob('*') if f.name.lower()=='project.work']
        if len(files)!=1:raise ValueError('fixture must contain one saved project')
        return files[0].parent
    work.mkdir()
    # emu_card.extract_image retains files only. Restore the empty AUDIO
    # directory stock uses to recognize a SET before testing its menus.
    prepared=work/'input-tree'
    shutil.copytree(kept_tree,prepared)
    home=project(prepared)
    (home.parent/'AUDIO').mkdir(exist_ok=True)
    port=v.Port(image,work/'save',writable=True,tree=prepared,
                extra=('--mount','--set',home.parent.name,'--project',home.name))
    try:
        expected=cell(port,0,0,0)
        v.midi_mode(port);v.watch_midi_out(port)
        before=v.bar_phrase(v.play_timed(port,4300))
        v.check('Kept fixture has a repeatable saved phrase',bool(before))
        package=v.runtime_package;address=0x41000000
        for at in range(0,len(package),4096):port.cmd(f'poke {address+at:#x} {package[at:at+4096].hex()}')
        call(port,'modwerk_modset_candidate',address,len(package))
        call(port,'modwerk_modset_accepted')
        v.check('Base accepted the exact package into its saved-set owner',
                int.from_bytes(port.peek(v.elf_symbol('modwerk_modset_count'),4),'big')==1)
        # The normal installed-backend fixture must wake its queue to service
        # the card writer. The restoring boot below sends no such message.
        wake=v.elf_symbol('core:wake_message')
        port.cmd(f'call 0x40000c3c 0x460d17ce {wake:#x}')
        v.settle_card(port,at_least_ms=8000)
        v.check('Base saved the package set through its real card writer',
                int.from_bytes(port.peek(v.elf_symbol('modwerk_modset_result'),4),'big')==7)
    finally:port.quit()
    tree=work/'tree'
    emu_card.extract_image(port.card.read_bytes(),str(tree))
    assert any(f.name.upper() in ('MODWERK0.SET','MODWERK1.SET') for f in tree.iterdir())
    current=project(tree);legacy=current.parent/'PROJECT 000001'
    (current.parent/'AUDIO').mkdir(exist_ok=True)
    shutil.copytree(project(legacy_tree),legacy)
    saved=next(f for f in legacy.iterdir() if f.name.lower()=='project.work')
    text=saved.read_text(encoding='latin1')
    # T1 is already selected in the supplied saved Part. Keep its settings;
    # exercise legacy migration on the previously unselected T2 instead.
    text='\r\n'.join(line for line in text.splitlines() if not line.startswith('#TURING_'))+'\r\n#TURING_T2=1,100,5\r\n'
    saved.write_bytes(text.encode('latin1'))
    # restore_only forbids backend publication and queue wake; the normal
    # base startup must restore the set and deliver modules-ready itself.
    port=v.Port(image,work/'restore',tree=tree,card_megabytes=128,restore_only=True,
                extra=('--mount','--set',current.parent.name,'--project',current.name))
    try:
        v.check('Fresh boot restores Kept Turing without backend install or manual wake',
                call(port,'modwerk_runtime_active')==1)
        v.check('Natural modules-ready imports the saved state',
                int.from_bytes(port.peek(v.elf_symbol('tm_ready_events'),4),'big')>=1
                and int.from_bytes(port.peek(v.elf_symbol('tm_install_read_done'),4),'big')==1
                and cell(port,0,0,0)==expected)
        v.mounted_startup(port)
        v.midi_mode(port);v.watch_midi_out(port)
        after=v.bar_phrase(v.play_timed(port,4300))
        v.check('Kept-set fresh boot retains the exact saved phrase',after==before and bool(before))
        project_change(port,work)
    finally:port.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image_file', type=Path, nargs='?')
    parser.add_argument('--image', type=Path)
    parser.add_argument('--emulator', type=Path)
    parser.add_argument('--native', type=Path, default=Path(os.environ.get('TM_NATIVE',HERE.parents[1])))
    parser.add_argument('--symbols', type=Path)
    parser.add_argument('--kept-tree',type=Path)
    parser.add_argument('--legacy-tree',type=Path)
    parser.add_argument('--reference-image', type=Path)
    parser.add_argument('--reference-arpgen', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--runs', default='stock,func,storage,s2,migration,replace,locks,nei,range,lfo,clock,model,lock,live,fresh,scale,density,write,flags,toggle,pattern,timer,reload,oldlines')
    args = parser.parse_args()
    args.image = args.image or args.image_file or args.native / 'out/mainos_bus.bin'
    args.emulator = args.emulator or Path(os.environ.get('TM_EMULATOR',args.native / 'out/emu/ot_emu'))
    args.symbols = args.symbols or Path(os.environ.get('TM_SYMBOLS',args.image.parent / 'symbols.json'))
    # The port starts with cwd=work: resolve caller paths before that change.
    args.image = args.image.resolve()
    args.reference_image = args.reference_image.resolve() if args.reference_image else None
    args.output = args.output.resolve() if args.output else None
    v.ROOT, v.EMU = args.native.resolve(), args.emulator.resolve()
    v.STOCK = v.ROOT / 'out/raw/section_3_MAIN_OS.bin'
    v.open_turing, v.page_tracks, v.poke_cell, v.cell = open_turing, page_tracks, poke_cell, cell
    v.write_trigs = write_trigs
    symbols = json.loads(args.symbols.read_text())
    v.elf_symbol = lambda name: symbols['turing-machine:' + name]
    v.SETTINGS, v.TEST_SEED, v.RANDOM, v.CELLS = (v.elf_symbol(n) for n in
        ('tm_settings', 'tm_test_seed', 'tm_random_states', 'tm_cells'))
    runs = {'projectchange':lambda i,w:change_run(i,w,args.kept_tree),'lifecycle':lambda i,w:lifecycle_run(i,w,args.kept_tree,args.legacy_tree),'review': review_run, 'stock': stock_contract_run, 'reference': lambda i,w: reference_arpgen_run(i,w,args.reference_arpgen), 'func': func_contract_run, 'storage': storage_run, 's2': s2_run, 'migration': migration_run,
            'key': lambda i,w: key_reference_run(i,w,args.reference_image),
            'replace': v.replace_run, 'locks': v.locks_run, 'nei': v.nei_run,
            'range': v.range_run, 'lfo': v.lfo_run, 'clock': v.clock_run, 'live': v.live_length_run,
            'lock': v.lock_run, 'pattern': pattern_run, 'timer': timer_run,
            'fresh': v.fresh_run, 'scale': scale_run, 'density': v.density_run,
            'write': v.write_run, 'flags': v.write_flags_check, 'toggle': v.toggle_run, 'reload': v.reload_run,
            'oldlines': oldlines_run,
            'model': lambda _i, _w: (v.range_model_check(), v.lock_model_check(), v.scale_model_check(),
                                     v.density_model_check(), v.fresh_model_check())}
    with tempfile.TemporaryDirectory(prefix='turing-arpgen-') as temporary:
        output = args.output or Path(temporary)
        output.mkdir(parents=True, exist_ok=True)
        for name in args.runs.split(','):
            runs[name](args.image.resolve(), output / name)
    if v.failures:
        raise SystemExit(f'FAIL: {len(v.failures)} checks')
    print('PASS: Turing generator emulator gates')


if __name__ == '__main__':
    main()
