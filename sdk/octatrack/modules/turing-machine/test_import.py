#!/usr/bin/env python3
"""Exercise the real modules-ready importer with a memory-backed stock-file model.

This checks chunk boundaries and once-per-install behavior without firmware.
The emulator's saved-project fresh boot remains the actual stock-file gate.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
class Importer(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'),'no host C compiler')
    def test_chunk_boundaries_partial_reads_and_once_per_install(self):
        source=(HERE/'turing.c').read_text().split('unsigned tm_modules_ready(void) {',1)[1]
        source='unsigned tm_modules_ready(void) {'+source
        replacements={
            'uint32_t directory = ((uint32_t (*)(int,int))0x40025230u)(0,0)':
                'uintptr_t directory = test_directory(0,0)',
            '((int (*)(void *,const char *,const char *,void *,unsigned))0x40016864u)': 'test_open',
            '((int (*)(void *,void *,unsigned))0x40016564u)': 'test_read',
            '((int (*)(void *))0x4001677cu)': 'test_close',
        }
        for before,after in replacements.items():
            self.assertEqual(source.count(before),1)
            source=source.replace(before,after)
        prefix=r'''
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
static unsigned tm_install_read_done, tm_project_loading;
static const char *content; static unsigned position, partial_success, opened, closed, begins, matches;
static const char wanted[]="#TURING_B16_P16_T8=1,127,16,64,127,1,2,3,4";
static uintptr_t test_directory(int a,int b) { (void)a;(void)b;return (uintptr_t)"/SET/PROJECT"; }
static int test_open(void *f,const char *path,const char *mode,void *io,unsigned n) {
 (void)f;(void)io;if(strcmp(path,"/SET/PROJECT/project.work")||strcmp(mode,"r")||n!=4096)exit(2);++opened;return 0;
}
static int test_read(void *f,void *dst,unsigned n) {
 (void)f;unsigned left=(unsigned)strlen(content)-position, take=left<n?left:n;
 memcpy(dst,content+position,take);position+=take;return take==n||(partial_success&&take)?1:0;
}
static int test_close(void *f) { (void)f;++closed;return 0; }
static void tm_project_begin(void) { ++begins; }
static void tm_project_line(const char *line,int parse) { if(parse)exit(3);if(!strcmp(line,wanted))++matches; }
static void tm_project_loaded(int result) { if(result<0)exit(4); }
'''
        suffix=r'''
int main(void) {
 char text[4096];unsigned checks=0;
 for(unsigned policy=0;policy<2;++policy)for(unsigned pad=0;pad<1536;++pad) {
  memset(text,'x',pad);text[pad]='\n';strcpy(text+pad+1,wanted);
  if(pad&1)strcat(text,"\r\n"); /* also cover a final line without a newline */
  content=text;position=0;partial_success=policy;opened=closed=begins=matches=0;
  tm_install_read_done=tm_project_loading=0;
  tm_modules_ready();tm_modules_ready();
  if(opened!=1||closed!=1||begins!=1||matches!=1) {
   fprintf(stderr,"pad %u policy %u opens %u closes %u begins %u matches %u\n",pad,policy,opened,closed,begins,matches);return 1;
  }
  ++checks;
 }
 puts("Importer: 3072 chunk/partial-read/final-newline cases, once per install");
 return checks==3072?0:1;
}
'''
        with tempfile.TemporaryDirectory(prefix='turing-import-') as folder:
            work=Path(folder); c=work/'test.c'; c.write_text(prefix+source+suffix)
            binary=work/'test'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(c),'-o',str(binary)],check=True)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            print(result.stdout,end='')
if __name__=='__main__':
    unittest.main()
