#!/usr/bin/env python3
"""Reference-engine equality and actual shared-SDK ColdFire scale compatibility.

Set TURING_REFERENCE_DIR to the read-only turing-arpgen module for the engine
comparison. Neither test boots firmware or communicates with an instrument.
"""
import ctypes
import importlib.util
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0,str(ROOT/'sdk/tests'))
REFERENCE = Path(os.environ['TURING_REFERENCE_DIR']) if os.environ.get('TURING_REFERENCE_DIR') else None

class State(ctypes.Structure):
    _fields_ = [('high',ctypes.c_uint32),('low',ctypes.c_uint32),('rng',ctypes.c_uint32),
                ('seeded',ctypes.c_uint8),('reserved',ctypes.c_uint8*3)]

class PortChecks(unittest.TestCase):
    @unittest.skipUnless(REFERENCE and shutil.which('cc'),'TURING_REFERENCE_DIR or host compiler unavailable')
    def test_fixed_seed_engine_matches_the_previous_implementation(self):
        with tempfile.TemporaryDirectory(prefix='turing-reference-') as folder:
            work=Path(folder)
            libraries=[]
            for name,source in (('reference',REFERENCE),('candidate',HERE)):
                text=(source/'turing.c').read_text().split('/* ---- per-pattern cells')[0]
                text=text.replace('#include "turing.h"','#include "'+str(source/'turing.h')+'"')
                text=text.replace('#include "../../../machines/octatrack/include/modwerk_events.h"','')
                text += '\nTmGlobals tm_globals; volatile TmSettings tm_settings; volatile TmTestSeed tm_test_seed;\n'
                text += 'void test_seed(uint32_t seed) { tm_globals.seed=seed; tm_globals.seeded=1; }\n'
                c=work/(name+'.c'); c.write_text(text)
                lib=work/(name+'.so')
                subprocess.run(['cc','-std=c11','-O2','-shared','-fPIC',str(c),'-o',str(lib)],check=True)
                loaded=ctypes.CDLL(str(lib))
                loaded.test_seed.argtypes=[ctypes.c_uint32]
                loaded.tm_step.argtypes=[ctypes.POINTER(State),*([ctypes.c_uint]*4)]
                loaded.tm_step.restype=ctypes.c_uint
                loaded.tm_turing_note.argtypes=[ctypes.c_uint]*3
                loaded.tm_turing_note.restype=ctypes.c_int
                libraries.append(loaded)
            old,new=libraries
            checked=0
            for seed in (0,1,0x13572468,0x2468ace1,0xffffffff):
                old.test_seed(seed); new.test_seed(seed)
                for track in range(8):
                    for salt in (0,17,255):
                        for length in range(2,65):
                            for lock in (0,25,40,64,80,95,96,127):
                                a,b=State(),State()
                                for step in range(64):
                                    args=(lock,length,track,salt)
                                    x=old.tm_step(ctypes.byref(a),*args)
                                    y=new.tm_step(ctypes.byref(b),*args)
                                    self.assertEqual((x,bytes(a)),(y,bytes(b)),(seed,track,salt,length,lock,step))
                                    for centre,scale in ((0,127),(48,64),(121,127)):
                                        self.assertEqual(old.tm_turing_note(centre,x,scale),new.tm_turing_note(centre,y,scale))
                                    checked+=1
            self.assertEqual(checked,5*8*3*63*8*64)
            print('Reference equality:',checked,'register transitions, three note ranges each')

    @unittest.skipUnless(importlib.util.find_spec('unicorn') and shutil.which('m68k-elf-gcc'),
                         'Unicorn or ColdFire compiler unavailable')
    def test_shared_scale_matches_previous_down_one_drop_rule(self):
        from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, m68k_const as m
        spec=importlib.util.spec_from_file_location('turing_test_builder',ROOT/'sdk/runtime/loader/build.py')
        builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory(prefix='turing-scale-') as folder:
            work=Path(folder)
            wrapper=work/'wrapper.o'; shared=work/'shared.o'
            subprocess.run(['m68k-elf-gcc','-mcpu=54455','-msoft-float','-O2','-ffreestanding','-fno-builtin',
                            '-fno-asynchronous-unwind-tables','-fno-ident','-c',str(HERE/'scale.c'),'-o',str(wrapper)],check=True)
            subprocess.run(['m68k-elf-as','-mcpu=54455',str(ROOT/'sdk/machines/octatrack/modwerk_scale.s'),'-o',str(shared)],check=True)
            image,syms,_,_=builder.link_units([wrapper,shared],'m68k-elf-',0x10000,work,anywhere=True)
            uc=Uc(UC_ARCH_M68K,UC_MODE_BIG_ENDIAN); uc.ctl_set_cpu_model(m.UC_CPU_M68K_CFV4E)
            uc.mem_map(0x10000,0x20000); uc.mem_write(0x10000,image)
            uc.mem_map(0x7e000,0x2000)
            checked=0
            for scale in range(3):
                mask=(0,0xab5,0x5ad)[scale]
                for root in range(12):
                    for note in range(-1,129):
                        expected=-1 if not 0<=note<=127 else note if not scale or mask >> ((note-root)%12)&1 else note-1
                        uc.reg_write(m.UC_M68K_REG_SR,0x2700)
                        uc.reg_write(m.UC_M68K_REG_A7,0x7f000)
                        uc.mem_write(0x7f000,struct.pack('>4I',0x7eff0,note&0xffffffff,scale,root))
                        uc.emu_start(syms['tm_scale_snap'],0x7eff0,count=4000)
                        self.assertEqual(uc.reg_read(m.UC_M68K_REG_PC),0x7eff0)
                        value=ctypes.c_int32(uc.reg_read(m.UC_M68K_REG_D0)).value
                        self.assertEqual(value,expected,(note,scale,root))
                        checked+=1
            self.assertEqual(checked,3*12*130)
            print('Actual ColdFire shared-scale wrapper:',checked,'OFF/MAJ/MIN and range-edge cases')
if __name__ == '__main__':
    unittest.main()
