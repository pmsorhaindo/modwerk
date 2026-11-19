#!/usr/bin/env python3
"""Execute linked package code: ownership, WRITE commit, load races and quantizer.

No firmware, physical instrument, or former battery table access. Stock edit
notification and formatting are bounded C-ABI stubs; the module is unmodified.
"""
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p/'sdk/runtime/loader/build.py').is_file())
AVAILABLE = importlib.util.find_spec('unicorn') and shutil.which('m68k-elf-as')
BANK, PART, PATTERN_SIZE = 0x400e21e0, 0x400e21e0+0x8ed80, 36568

@unittest.skipUnless(AVAILABLE, 'Unicorn/ColdFire binutils unavailable')
class Runtime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, m68k_const
        cls.api = Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, m68k_const
        spec=importlib.util.spec_from_file_location('turing_runtime_builder',ROOT/'sdk/runtime/loader/build.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory(prefix='turing-runtime-') as folder:
            work=Path(folder);objects=[]
            for i,source in enumerate((HERE/'turing.s',ROOT/'sdk/machines/octatrack/modwerk_scale.s')):
                obj=work/f'{i}.o';subprocess.run(['m68k-elf-as','-mcpu=54455','--defsym','MODWERK_EVENTS=1',str(source),'-o',str(obj)],check=True);objects.append(obj)
            cls.image,cls.symbols,cls.bss,_=builder.link_units(objects,'m68k-elf-',0x48000000,work,anywhere=True)

    def setUp(self):
        Uc,arch,mode,code,read,write,self.m=self.api
        self.uc=Uc(arch,mode);self.uc.ctl_set_cpu_model(self.m.UC_CPU_M68K_CFV4E)
        for at,size in ((0x40000000,0x1000000),(0x46000000,0x1000000),(0x48000000,0x100000),
                        (0x10000000,0x100000),(0x80000000,0x10000),(0x70000000,0x10000),(0xfc000000,0x100000)):
            self.uc.mem_map(at,size)
        self.uc.mem_write(0x48000000,self.image)
        self.calls={};self.lines=[];self.count=0
        for at in (0x40027e00,0x4004d948,0x4005a2b8,0x400000f0,0x40000100,0x40000110):self.uc.mem_write(at,b'\x4e\x75')
        # tm_stock_eval's displaced 40-byte frame, then the stock return.
        self.uc.mem_write(0x4009cf54,b'\x4f\xef\x00\x28\x4e\x75')
        def forbidden(*args):raise AssertionError('candidate accessed the forbidden former battery table')
        self.uc.hook_add(read|write,forbidden,begin=0x100f9000,end=0x100fefff)
        def trace(uc,at,size,user):
            self.count+=1
            if at in (0x40027e00,0x4004d948,0x4005a2b8):self.calls[at]=self.calls.get(at,0)+1
            if at in (0x400000f0,0x40000100,0x40000110):
                sp=uc.reg_read(self.m.UC_M68K_REG_A7)
                args=struct.unpack('>16I',uc.mem_read(sp+4,64))
                if at==0x400000f0:
                    fmt=self.text(args[1]);text=fmt%args[2:2+fmt.count('%d')]
                    uc.mem_write(args[0],text.encode()+b'\0');result=len(text)
                elif at==0x40000100:result=len(self.text(args[0]))
                else:self.lines.append(bytes(uc.mem_read(args[1],args[2])));result=args[2]
                uc.reg_write(self.m.UC_M68K_REG_D0,result)
        self.uc.hook_add(code,trace)
        self.put(0x46c82456,BANK);self.uc.mem_write(0x100b14cf,b'\0')
        self.putsym('tm_migration_ready',1)
        self.uc.mem_write(self.symbols['tm_globals'],struct.pack('>I4B',0x13572468,1,1,0,0))
        self.select()
        self.cell()

    def put(self,at,value):self.uc.mem_write(at,struct.pack('>I',value&0xffffffff))
    def get(self,at):return int.from_bytes(self.uc.mem_read(at,4),'big')
    def putsym(self,name,value):self.put(self.symbols[name],value)
    def text(self,at):
        data=bytearray()
        while True:
            c=self.uc.mem_read(at+len(data),1)[0]
            if not c:return data.decode()
            data.append(c)
    def select(self,part=0,lock=127,length=16,scale=64,density=127):
        at=PART+6322*part
        self.uc.mem_write(at+0x1822,b'M\x01')
        self.uc.mem_write(at+0x1832,bytes((v-64)&255 for v in (lock,length,scale,density,0,0,1,53)))
        self.uc.mem_write(at+0x3e2,b'\x30')
    def cell(self,track=0,on=True,length=16):
        self.uc.mem_write(self.symbols['tm_cells']+12*track,struct.pack('>4B2I',0x80 if on else 0,0x80|(length^16),0,63,0x12345678,0xbeef0001))
    def call(self,name,*args):
        self.uc.reg_write(self.m.UC_M68K_REG_SR,0x2000)
        self.uc.reg_write(self.m.UC_M68K_REG_A7,0x7000e000)
        self.uc.mem_write(0x7000e000,struct.pack('>'+('I'*(len(args)+1)),0x7000fff0,*(v&0xffffffff for v in args)))
        before=self.count
        self.uc.emu_start(self.symbols[name],0x7000fff0,count=4000000)
        self.assertEqual(self.uc.reg_read(self.m.UC_M68K_REG_PC),0x7000fff0,name)
        return self.uc.reg_read(self.m.UC_M68K_REG_D0),self.count-before

    def test_akl_b_locrian_cannot_claim_a_non_turing_chord(self):
        self.cell(on=False)
        self.uc.mem_write(0x46c7a01e,b'\x54\xff')
        self.call('tm_eval',0,0,0,0,0)
        self.assertEqual(self.call('tm_fired',0)[0],0)
        self.uc.mem_write(PART+0x1822,b'\0\0');self.cell(on=True)
        self.assertEqual(self.call('tm_fired',0)[0],0)
        # Execute the actual chord detour, stopping at its stock continuation.
        self.uc.reg_write(self.m.UC_M68K_REG_A6,0x70004000)
        self.uc.reg_write(self.m.UC_M68K_REG_D7,0)
        self.uc.reg_write(self.m.UC_M68K_REG_A7,0x7000e000)
        self.uc.mem_write(0x70003ffc,bytes((48,55,60,64)))
        self.uc.emu_start(self.symbols['tm_chord_hook'],0x4009fa30,count=4000)
        self.assertEqual(self.uc.mem_read(0x70003ffc,4),bytes((48,55,60,64)))

    def test_queued_turing_ownership_survives_a_pattern_or_part_change(self):
        # Last ON step is already scheduled when the next OFF pattern/Part
        # becomes current. It must still suppress the stock chord notes.
        self.call('tm_eval',0,0,0,15,0)
        self.uc.mem_write(0x800065be,b'\x01')
        self.uc.mem_write(PART+0x1822,b'\0\0')
        self.assertEqual(self.call('tm_fired',0)[0],1)
        # Evaluating the next stock step retires that ownership, even if AKL
        # supplies the formerly colliding B-Locrian KEY byte.
        self.call('tm_eval',0,0,1,0,0)
        self.uc.mem_write(0x46c7a01e,b'\x54\xff')
        self.assertEqual(self.call('tm_fired',0)[0],0)
        self.uc.mem_write(self.symbols['tm_scheduled'],b'\x01')
        self.call('tm_eval',0,0,1,0,-1)
        self.assertEqual(self.call('tm_fired',0)[0],0)

    def test_write_preserves_akl_and_commits_mirror_dirty_and_index(self):
        locks=BANK+0x4900
        for step in range(64):
            self.uc.mem_write(locks+32*step,b'\xff'*30+b'\x54\x3f')
            self.uc.mem_write(0x46c7d2e4+step,b'\x80')
        self.put(BANK+0x8e53-3,0)  # separate length byte below
        self.uc.mem_write(BANK+0x8e53,b'\x10')
        result,cost=self.call('tm_write_track',0);self.assertEqual(result,1)
        for step in range(16):
            record=bytes(self.uc.mem_read(locks+32*step,32))
            self.assertEqual(record[30:],b'\x54\x3f')
            for field in (0,3,4,5):self.assertEqual(self.uc.mem_read(0x1001614e+0x4900+32*step+field,1),record[field:field+1])
            self.assertEqual(self.uc.mem_read(0x46c7d2e4+step,1),b'\x81')
        self.assertEqual(self.get(BANK+0x9b332),1);self.assertEqual(self.get(0x100f8598),1)
        self.assertEqual(self.calls[0x40027e00],1)
        self.assertEqual(self.uc.mem_read(BANK+0x48d0,16),self.uc.mem_read(0x1001614e+0x48d0,16))
        print('Linked WRITE instructions:',cost,'(16 steps; firmware cost not included)')

    def test_legacy_write_centres_are_read_only_and_distinct_from_akl(self):
        locks=BANK+0x4900
        self.uc.mem_write(BANK+0x8e53,b'\x10')
        for marker,centre in ((0x54,60),(0x57,48)):
            self.uc.mem_write(self.symbols['tm_written_centres'],bytes(64))
            self.uc.mem_write(locks,b'\x3c'+b'\xff'*29+bytes((marker,48)))
            self.put(BANK+0x48d4,1)
            self.call('tm_write_track',0)
            self.assertEqual(self.uc.mem_read(locks+30,2),bytes((marker,48)))
            self.assertEqual(self.uc.mem_read(self.symbols['tm_written_centres'],1)[0],centre+1)

    def test_owned_write_centres_round_trip_without_pattern_markers(self):
        values=bytes([49]*16+[0]*48)
        self.uc.mem_write(self.symbols['tm_written_centres'],values)
        self.call('tm_project_write',0x400000f0,0x40000100,0x40000110,0x70001000,1)
        line=next(x for x in self.lines if x.startswith(b'#TURING_WB'))
        self.call('tm_project_begin')
        self.assertEqual(self.uc.mem_read(self.symbols['tm_written_centres'],64),bytes(64))
        self.uc.mem_write(0x70001000,line+b'\0');self.call('tm_project_line',0x70001000,0)
        self.assertEqual(self.uc.mem_read(self.symbols['tm_written_centres'],64),values)
        self.call('tm_project_loaded',0)

    def test_begin_never_exposes_defaults_as_a_completed_load_and_failure_unlatches(self):
        writes=[]
        def during(uc,access,at,size,value,user):
            writes.append(at)
            self.assertEqual(self.get(self.symbols['tm_project_loading']),1)
            self.assertEqual(self.get(self.symbols['tm_migration_ready']),0)
        h=self.uc.hook_add(self.api[5],during,begin=self.symbols['tm_cells'],end=self.symbols['tm_cells']+24575)
        self.call('tm_project_begin');self.uc.hook_del(h);self.assertTrue(writes)
        self.call('tm_project_defaults')
        self.assertEqual(self.get(self.symbols['tm_project_loading']),1)
        self.call('tm_project_loaded',-1)
        self.assertEqual(self.get(self.symbols['tm_project_loading']),0)
        self.assertEqual(self.get(self.symbols['tm_install_read_done']),0)

    def test_load_generation_prevents_old_migration_committing_s2(self):
        self.uc.mem_write(PART+0x1822,b'\0\0');self.putsym('tm_migration_ready',0)
        injected=[]
        def preempt(uc,at,size,user):
            if not injected and self.uc.mem_read(PART+0x1822,2)==b'M\x01' and (uc.reg_read(self.m.UC_M68K_REG_SR)&0x700)<0x200:
                self.putsym('tm_project_loading',1);self.putsym('tm_load_generation',1);injected.append(True)
        h=self.uc.hook_add(self.api[3],preempt)
        self.call('tm_generator_tick');self.uc.hook_del(h)
        self.assertTrue(injected)
        self.assertEqual(self.get(self.symbols['tm_migration_ready']),0)
        self.assertEqual(self.uc.mem_read(self.symbols['tm_settings']+20,1)[0]&4,0)

    def test_window_blocks_write_press_and_release(self):
        self.uc.mem_write(self.symbols['tm_ui'],b'\x01')
        self.put(0x80000012,1);self.put(0x460d1684,2)
        self.put(0x400bcd14,0x70002000);self.put(0x70002008,1)
        self.call('tm_push',0x38,1);self.call('tm_push',0x38,0)
        self.assertEqual(self.get(self.symbols['tm_ui']+24),0)
        self.assertNotIn(0x4005a2b8,self.calls)

    def test_lcd_overlay_blocks_both_write_edges_without_a_setup_window(self):
        self.select();self.cell()
        self.uc.mem_write(self.symbols['tm_ui'],b'\x01')
        self.put(0x80000012,1);self.put(0x460d1684,2)
        for i in range(5):
            flags = 0x46c7d34c + 56*i + 32
            self.put(flags,0x20)
            self.call('tm_push',0x38,1)
            self.assertEqual(self.uc.mem_read(self.symbols['tm_ui']+3,1),b'\0')
            self.call('tm_push',0x38,0)
            self.put(flags,0)
            # It may have been armed before the covering menu appeared.
            self.uc.mem_write(self.symbols['tm_ui']+3,b'\x01')
            self.put(flags,0x20)
            self.call('tm_push',0x38,0)
            self.put(flags,0)
        self.assertEqual(self.get(self.symbols['tm_ui']+24),0)
        self.assertNotIn(0x40027e00,self.calls)
        self.assertNotIn(0x4005a2b8,self.calls)

    def test_cued_part_edit_reads_and_writes_displayed_part(self):
        self.select(part=0,lock=10);self.select(part=1,lock=90)
        self.uc.mem_write(0x100b14cf,b'\x01')
        self.call('tm_knob',1,1)
        self.assertEqual((self.uc.mem_read(PART+0x1832,1)[0]+64)&127,10)
        self.assertEqual((self.uc.mem_read(PART+6322+0x1832,1)[0]+64)&127,91)
        self.assertEqual(self.calls.get(0x40027e00),1)

    def test_worst_catch_up_instruction_counts_for_all_eight_tracks(self):
        maxima=[]
        self.uc.mem_write(BANK+0x8e53,b'\x40')
        for length in range(2,8):
            counts=[]
            for track in range(8):
                self.select_track(track,length)
                self.cell(track=track,length=length)
                self.uc.mem_write(self.symbols['tm_live']+12*track,bytes(12))
                handled,cost=self.call('tm_eval',track,0,0,63,1)
                self.assertEqual(handled,1)
                counts.append(cost)
            maxima.append(max(counts))
            print('Linked catch-up LEN',length,'eight-track instructions',sum(counts),'maximum per track',max(counts))
        self.assertEqual(len(maxima),6)

    def select_track(self,track,length):
        self.uc.mem_write(PART+0x1822+2*track,b'M\x01')
        self.uc.mem_write(PART+0x1832+16*track,bytes((v-64)&255 for v in (64,length,127,64,0,0,1,53)))

    def test_scale_sweep_runs_the_shipped_note_key_entry(self):
        pointer=0x70003000;checked=0
        for scale in range(3):
            mask=(0,0xab5,0x5ad)[scale]
            for root in range(12):
                self.uc.mem_write(PART+0x1836,bytes(((scale-64)&255,(root-64)&255)))
                for note in range(-1,128):
                    self.uc.mem_write(pointer,bytes((note&255,)))
                    self.assertEqual(self.call('tm_note_key',0,pointer)[0],1)
                    result=self.uc.mem_read(pointer,1)[0];result=result-256 if result>127 else result
                    expected=note if note<0 or not scale or mask>>((note-root)%12)&1 else note-1
                    self.assertEqual(result,expected,(scale,root,note));checked+=1
        print('Linked package note-key sweep:',checked,'cases, actual inlined wrapper')

if __name__=='__main__':unittest.main()
