#!/usr/bin/env python3
"""Private emulator check of beta runtime admission, generator UI and notes.

Uses the real base's backend in the emulator; it does not exercise USB wire
transport or physical Keep/Undo/reboot and never connects to an instrument.
The emulator needs the documented idle and borrowed-call adapters.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('turing_arpgen_gate', HERE / 'verify_arpgen.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
v = a.v


def run(args):
    symbols = json.loads((args.base / 'symbols.json').read_text())
    v.ROOT, v.EMU = args.native.resolve(), args.emulator.resolve()
    v.elf_symbol = lambda name: symbols[name]
    port = v.Port(args.base / 'MAIN.raw', args.output)

    def invoke(fn, *values):
        response = port.cmd('call ' + hex(fn) + ''.join(' ' + hex(x) for x in values))
        return int(response.split('d0=')[1], 16)

    def upload(data, backend):
        # This is emulator scratch RAM, not a physical transport.
        address = 0x41000000
        for offset in range(0,len(data),4096):
            port.cmd(f'poke {address+offset:#x} {data[offset:offset+4096].hex()}')
        for index, values in ((1,(0,)), (4,(0,address,len(data))), (6,(0,))):
            result = invoke(backend[index], *values)
            v.check('Runtime backend ' + ('enter' if index == 1 else 'prepare' if index == 4 else 'publish'), result == 1)
            if result != 1:
                raise RuntimeError('Runtime admission/publication refused: ' + str(a.call(port,'modwerk_runtime_refusal')))

    try:
        port.run(5000)
        port.press('NO')
        backend = struct.unpack('>9I', port.peek(symbols['modwerk_runtime_backend'],36))
        package = args.package.read_bytes()
        upload(package,backend)
        v.check('Runtime backend retires predecessor and leaves', invoke(backend[8],0) == invoke(backend[3],0) == 1)
        v.check('One active intact module', a.call(port,'modwerk_runtime_active') == a.call(port,'modwerk_runtime_intact') == 1)
        port.run(500)
        port.press('MIDI')
        port.press('T1')
        a.open_turing(port)
        v.set_page(port,True,127,16,64,127)
        part = a.current_part(port)
        v.check('Beta registry selects TURING and stores S2 settings',
                port.peek(part+0x1822,2) == b'M\x01' and port.peek(part+0x1832,4) == bytes((63,208,0,63)))
        port.enc('B', -63)  # LOCK 64
        port.key('FUNC', True, 60)
        v.drawn(port, lambda: port.enc('B', 1))
        v.check('Stock host yields held FUNC and leaves LOCK unchanged',
                port.peek(part+0x1832,1) == bytes((0,)) and a.call(port,'mg_page',0x1234) == 0x1234)
        port.key('FUNC', False, 60)
        port.enc('B',63)
        port.press('FUNC','SRC')
        port.enc('A',4)
        port.press('YES')
        port.press('NO')
        port.press('AMP')
        port.press('FUNC','AMP')
        port.enc('A',1)
        port.enc('B',2)
        port.press('NO')
        v.watch_midi_out(port)
        events = v.play_timed(port,4300)
        notes = v.onsets(events,0)
        v.check('Beta note-key event applies own D major', len(notes)>=32
                and all((n-2)%12 in (0,2,4,5,7,9,11) for _,n,_ in notes))
        saved = port.peek(part+0x1832,16)
        upload(package,backend)
        v.check('Runtime backend Undo restores predecessor', invoke(backend[7],0) == 1)
        v.check('Undo keeps one intact module and Part settings',
                a.call(port,'modwerk_runtime_active') == a.call(port,'modwerk_runtime_intact') == 1
                and port.peek(part+0x1832,16) == saved)
        invoke(backend[8],0)
        invoke(backend[3],0)
        # Build the SDK's own empty removal package; do not forge wire records.
        builder_path = HERE.parents[2] / 'runtime/loader/build.py'
        spec = importlib.util.spec_from_file_location('turing_runtime_builder',builder_path)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        empty = builder.package(b'',0,[],[],name='turing-machine',hashed=True,title='TURING')
        upload(empty,backend)
        invoke(backend[8],0)
        invoke(backend[3],0)
        port.run(500)
        v.check('Removal leaves no active module; Part choice/settings retained',
                a.call(port,'modwerk_runtime_active') == 0 and port.peek(part+0x1822,2) == b'M\x01'
                and port.peek(part+0x1832,16) == saved)
    finally:
        port.quit()
    if v.failures:
        raise SystemExit('FAIL: beta emulator checks')
    print('PASS: beta runtime backend emulator checks; USB wire and hardware not tested')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base','package','emulator','native','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args = parser.parse_args()
    for name in ('base','package','emulator','native','output'):
        setattr(args,name,getattr(args,name).resolve())
    run(args)
