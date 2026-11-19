#!/usr/bin/env python3
"""Run the Turing gates on a private browser-built base and real runtime backend.

No physical USB or MIDI. Each boot installs the package through the backend,
then runs the panel gate. Saved-card boots start with fresh module memory.
Historical comparison images are read-only and keep their own UI adapters.
"""
import argparse
import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'sdk/runtime/loader/build.py').is_file())
def load(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def module_symbols(package):
    builder = load('turing_runtime_build', ROOT / 'sdk/runtime/loader/build.py')
    with tempfile.TemporaryDirectory(prefix='turing-symbols-') as folder:
        work = Path(folder)
        objects = []
        for index, source in enumerate((HERE / 'turing.s', ROOT / 'sdk/machines/octatrack/modwerk_scale.s')):
            obj = work / ('%d.o' % index)
            subprocess.run(['m68k-elf-as','-mcpu=54455','--defsym','MODWERK_EVENTS=1',str(source),'-o',str(obj)],check=True)
            objects.append(obj)
        image, symbols, bss, relocations = builder.link_units(objects,'m68k-elf-',0,work,anywhere=True)
    abi = struct.unpack_from('>H',package,4)[0]
    size, actual_bss, relocs, hooks = struct.unpack_from('>4I',package,8)
    header = {8:76,7:72}[abi]
    assert package[header+4*hooks:header+4*hooks+size] == image
    assert (actual_bss,relocs) == (bss,len(relocations))
    return dict(symbols)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base','package','native','emulator','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--runs',default='stock,func,storage,s2,migration,replace,locks,nei,range,lfo,clock,model,lock,live,fresh,scale,density,write,flags,toggle,pattern,timer,reload,oldlines')
    parser.add_argument('--reference-image',type=Path)
    parser.add_argument('--kept-tree',type=Path)
    parser.add_argument('--legacy-tree',type=Path)
    parser.add_argument('--companion',type=Path,action='append',default=[])
    parser.add_argument('--reference-arpgen',type=Path)
    args = parser.parse_args()
    for name in ('base','package','native','emulator','output'):
        setattr(args,name,getattr(args,name).resolve())
    args.output.mkdir(parents=True,exist_ok=True)
    a = load('turing_arpgen_gate',HERE/'verify_arpgen.py')
    v = a.v
    base = json.loads((args.base/'symbols.json').read_text())
    package = args.package.read_bytes()
    offsets = module_symbols(package)
    v.runtime_package = package
    initial = {'turing-machine:'+k:value for k,value in {**base,**offsets}.items()}
    init_symbols = args.output/'initial-symbols.json'
    init_symbols.write_text(json.dumps(initial))
    original_port = v.Port
    class InstalledPort(original_port):
        def __init__(self,image,*pos,**kw):
            restore_only = kw.pop("restore_only",False)
            kw["extra"] = (*kw.get("extra",()), "--max", "250000000")
            super().__init__(image,*pos,**kw)
            if Path(image).resolve() != args.base/'MAIN.raw':
                if args.reference_arpgen and Path(image).resolve() == args.reference_arpgen.resolve()/'MAIN.raw':
                    ref=json.loads((args.reference_arpgen/'symbols.json').read_text())
                    v.elf_symbol=lambda name: ref.get('turing-machine:'+name,ref.get(name))
                    v.SETTINGS,v.TEST_SEED,v.RANDOM,v.CELLS=(v.elf_symbol(n) for n in
                        ('tm_settings','tm_test_seed','tm_random_states','tm_cells'))
                return  # a historical reference image, with its own contract
            self.run(5000)
            backend = struct.unpack('>9I',self.peek(base['modwerk_runtime_backend'],36))
            def invoke(fn,*values):
                reply = self.cmd('call '+hex(fn)+''.join(' '+hex(x) for x in values))
                return int(reply.split('d0=')[1],16)
            if not restore_only:
                address = 0x41000000
                for at in range(0,len(package),4096):
                    self.cmd(f'poke {address+at:#x} {package[at:at+4096].hex()}')
                for index,values in ((1,(0,)),(4,(0,address,len(package))),(6,(0,))):
                    result=invoke(backend[index],*values)
                    if result != 1:
                        refusal=invoke(base['modwerk_runtime_refusal'])
                        self.quit()
                        raise RuntimeError(f'Runtime backend stage {index} refused {refusal}')
                assert invoke(backend[8],0) == invoke(backend[3],0) == 1
                for companion in args.companion:
                    data=companion.resolve().read_bytes()
                    for at in range(0,len(data),4096):
                        self.cmd(f'poke {address+at:#x} {data[at:at+4096].hex()}')
                    for index,values in ((1,(0,)),(4,(0,address,len(data))),(6,(0,))):
                        if invoke(backend[index],*values)!=1:
                            self.quit()
                            raise RuntimeError(f'Companion backend stage {index} refused')
                    assert invoke(backend[8],0) == invoke(backend[3],0) == 1
            record=invoke(base['modwerk_runtime_module'],0)
            assert record and self.peek(record,4) == package[28:32], 'Kept Turing was not restored'
            descriptor=int.from_bytes(self.peek(record+8+4*31,4),'big')
            origin=descriptor-offsets['tm_generator']
            if restore_only:
                # A matching module ID is not an exact-build check: an older
                # Kept version can have the same ID but different offsets.
                # This paused emulator query reads the base's immutable owner.
                scratch=0x41010000
                assert invoke(base['modwerk_runtime_owner_snapshot'],origin,scratch)==1
                assert self.peek(scratch+24,32)==hashlib.sha256(package).digest(), \
                    'Kept package differs from the acceptance artifact'
            resolved={k:origin+value for k,value in offsets.items()}
            self.module_symbols=resolved
            v.elf_symbol=lambda name: resolved[name] if name in resolved else base[name]
            v.SETTINGS,v.TEST_SEED,v.RANDOM,v.CELLS=(resolved[n] for n in
                    ('tm_settings','tm_test_seed','tm_random_states','tm_cells'))
            (self.card.parent/'runtime-symbols.json').write_text(json.dumps({**base,**resolved},indent=2))
            # Direct backend calls omit the transport's engine-queue wake.
            # Use its actual inert message (ep0.c), so the unmodified engine
            # idle path restores the set, then raises modules-ready. A second
            # wake covers a boot whose first service only finishes restoration.
            if not restore_only:
                wake = base['core:wake_message']
                assert self.peek(wake, 4) == b'\xff\0\0\0'
                for _ in range(2):
                    invoke(0x40000c3c, 0x460d17ce, wake)
                    self.run(500)
            assert int.from_bytes(self.peek(resolved['tm_ready_events'], 4), 'big') >= 1, \
                'The base engine did not deliver modules-ready'
    v.Port=InstalledPort
    sys.argv=[str(HERE/'verify_arpgen.py'),str(args.base/'MAIN.raw'),'--symbols',str(init_symbols),
              '--native',str(args.native),'--emulator',str(args.emulator),'--output',str(args.output),
              '--runs',args.runs]
    if args.reference_image:
        sys.argv += ['--reference-image',str(args.reference_image.resolve())]
    if args.reference_arpgen:
        sys.argv += ["--reference-arpgen",str(args.reference_arpgen.resolve())]
    for name in ('kept_tree','legacy_tree'):
        path=getattr(args,name)
        if path:
            sys.argv += ['--'+name.replace('_','-'),str(path.resolve())]
    a.main()
if __name__ == '__main__':
    main()
