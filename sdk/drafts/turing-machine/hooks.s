| Appended to the generated turing.s by generate.py.
        .text
        .balign 4
        .global tm_note_hook

| The head of the stock MIDI-track chord loop (0x4009fb2e): d7 = track
| 0..7, d4 = chord slot 0..3, a2 -> the slot's resolved note byte. The
| displaced instructions load d0, d1 and d3 and the code after them reloads
| a0 and a1, so the C call may clobber d0-d1/a0-a1. The condition codes are
| set by the displaced moveq, as stock.
tm_note_hook:
        tst.l   %d4
        bne.s   1f
        move.l  %a2,-(%sp)
        move.l  %d7,-(%sp)
        jsr     tm_note
        addq.l  #8,%sp
1:      move.b  (%a2),%d1           | displaced
        mvs.b   %d1,%d0             | displaced
        moveq   #-1,%d3             | displaced
        jmp     0x4009fb34

| The project file. The loader 0x400866c4 runs twice per load, a parse-only
| pass then a storing pass; 58(%sp) in its frame is nonzero on the
| parse-only pass. Scale Quantizer hooks the neighbouring instructions
| (0x400866cc, 0x400867a2, 0x400888aa, 0x40025ac2); these sites are its
| neighbours, so the two compose without sharing a site.

| Loader entry, after the frame is set up (0x400866ee): a storing load
| starts from the defaults.
        .global tm_load_entry_hook
tm_load_entry_hook:
        tst.l   58(%sp)
        bne.s   1f
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     tm_project_defaults
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
1:      pea     0x400b44b5          | displaced
        jmp     0x400866f4

| The loader's next-line point (0x40088224), reached once per complete line
| (comments, Scale Quantizer's lines and every stock key) with d3 -> the
| line, before the buffer is cleared.
        .global tm_load_line_hook
tm_load_line_hook:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l  16+58(%sp),-(%sp)
        move.l  %d3,-(%sp)
        jsr     tm_project_line
        addq.l  #8,%sp
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        pea     0x400b44b5          | displaced
        jmp     0x4008822a

| The serializer 0x40088288, one block after Scale Quantizer's: the Turing
| lines go between PATTERN_CHANGE_AUTO_SILENCE_TRACKS and
| PATTERN_CHANGE_AUTO_TRIG_LFOS (0x400888d2).
| a4 = format, a3 = length, a2 = write, d2 = the line buffer, d3 = the file.
        .global tm_write_hook
tm_write_hook:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l  %d3,-(%sp)
        move.l  %d2,-(%sp)
        move.l  %a2,-(%sp)
        move.l  %a3,-(%sp)
        move.l  %a4,-(%sp)
        jsr     tm_project_write
        lea     20(%sp),%sp
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        mvs.b   0x80000050,%d0      | displaced
        move.l  %d0,-(%sp)          | displaced
        jmp     0x400888da

| Project defaults (0x40025848: cold boot, a boot with no project, a new
| project): every track OFF.
        .global tm_defaults_hook
tm_defaults_hook:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     tm_project_defaults
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        clr.l   0x100b14de          | displaced, last: the caller sees its flags
        rts

| Explicitly initialized, loader-owned DRAM: a DRAM unit's .bss is never
| cleared. The C's static assertions check the sizes.
        .balign 4
        .global tm_states, tm_globals
tm_states:
        .zero   64
tm_globals:
        .zero   8
