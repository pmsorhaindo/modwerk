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

| Explicitly initialized, loader-owned DRAM: a DRAM unit's .bss is never
| cleared. The C's static assertions check the sizes.
        .balign 4
        .global tm_states, tm_globals
tm_states:
        .zero   64
tm_globals:
        .zero   8
