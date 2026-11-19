| Appended to the generated turing.s by generate.py.
        .text
        .balign 4
        .global tm_chord_hook

| The MIDI note routine 0x4009f794, a track's step firing (0x4009fa2a): the
| chord fp@(-4..-1) = NOTE, NOT2..NOT4 (-1 = none) is built from the
| track's resolved (LFO-modulated) bytes and about to go to the
| arpeggiator's input (0x40099c08) and out. The tick ISR has just copied the
| fired step's record to 0x46c7a000 + 32 * track. tm_fired uses Turing's
| scheduling/track ownership, never saved bytes 30-31, and
| NOT2..NOT4 are dropped, one note a step. Before the mute and VEL checks,
| so a muted step counts as played. d7 = track; d0/d1/a0/a1 are written
| before they are read again; the displaced instructions set no flag
| anyone reads.
tm_chord_hook:
        move.l  %d7,-(%sp)
        jsr     tm_fired
        addq.l  #4,%sp
        tst.l   %d0
        beq.s   1f
        moveq   #-1,%d0
        move.b  %d0,-3(%fp)
        move.b  %d0,-2(%fp)
        move.b  %d0,-1(%fp)
1:      move.l  %fp,%d2             | displaced
        subq.l  #4,%d2              | displaced
        move.l  %d2,-(%sp)          | displaced
        jmp     0x4009fa30

| The entry of the MIDI sequencer's per-step trig evaluator 0x4009cf4c(track,
| bank, pattern, step, slot), a C function (it saves d2-d7/a2-a5): on a track
| whose MODE is ON, tm_eval schedules the step's Turing note and returns
| nonzero, and stock's evaluator does not run.
        .global tm_eval_hook
tm_eval_hook:
        move.l  20(%sp),-(%sp)
        move.l  20(%sp),-(%sp)
        move.l  20(%sp),-(%sp)
        move.l  20(%sp),-(%sp)
        move.l  20(%sp),-(%sp)
        jsr     tm_eval
        lea     20(%sp),%sp
        tst.l   %d0
        beq.s   1f
        rts
1:      lea     -40(%sp),%sp        | displaced
        movem.l %d2-%d7/%a2-%a5,(%sp) | displaced
        jmp     0x4009cf54

| The stock evaluator called from C (tm_eval's first step): its own entry,
| displaced here, and it returns to the caller.
        .global tm_stock_eval
tm_stock_eval:
        lea     -40(%sp),%sp
        movem.l %d2-%d7/%a2-%a5,(%sp)
        jmp     0x4009cf54

| PLAY, before it copies each MIDI track's first step (0x4009c076): d0-d1
| and a0-a1 are written before they are read again.
        .global tm_play_hook
tm_play_hook:
        jsr     tm_play
        lea     0x46c769e0,%a3      | displaced
        jmp     0x4009c07c

| The project file. The loader 0x400866c4 runs twice per load, a parse-only
| pass then a storing pass; 58(%sp) in its frame is nonzero on the
| parse-only pass. The base owns the adjacent take-hook/fxmap seams;
| these guarded detours leave those sites intact. Shared project call hooks
| require a separate owner-reviewed base change, not a private host patch.

| Loader entry, after the frame is set up (0x400866ee): a storing load
| starts from the defaults.
        .global tm_load_entry_hook
tm_load_entry_hook:
        tst.l   58(%sp)
        bne.s   1f
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     tm_project_begin
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
1:      pea     0x400b44b5          | displaced
        jmp     0x400866f4

| The loader's next-line continuation (0x4008822a), reached once per complete line
| (comments, Scale Quantizer's lines and every stock key) with d3 -> the
| line, before the buffer is cleared.
        .global tm_load_line_hook
tm_load_line_hook:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l  16+62(%sp),-(%sp)
        move.l  %d3,-(%sp)
        jsr     tm_project_line
        addq.l  #8,%sp
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        move.l  %d3,-(%sp)         | displaced; the line-clear call
        move.l  %d7,%a0
        jsr     (%a0)
        jmp     0x40088230

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

| 0x4004ecfc(code, down), the stock encoder-push handler (a C function: it
| reads both from the stack and sets the knob's x7): tm_push sees knob A
| pushed and released on the TURING page (WRITE), then stock runs as for
| any push. d0-d1/a0-a1 are free at a C function's entry.
        .global tm_push_hook
tm_push_hook:
        move.l  8(%sp),-(%sp)
        move.l  8(%sp),-(%sp)
        jsr     tm_push
        addq.l  #8,%sp
        lea     -16(%sp),%sp        | displaced
        movem.l %d2-%d5,(%sp)       | displaced
        jmp     0x4004ed04

| Runtime-package storage. The USB loader zeros BSS before publication.
| Card firmware builds are not a supported delivery route for this module.
        .bss
        .balign 4
        .global tm_globals, tm_ui, tm_desc, tm_first_steps, tm_live
tm_first_steps:                     | each track's last first-step evaluation (TmFirst)
        .zero   480
tm_globals:
        .zero   8
tm_live:                            | the register each track plays (TmLive)
        .zero   96
tm_ui:
        .zero   28
tm_desc:                            | the TURING page's descriptor, built on first use
        .zero   0x194

| Session storage belongs entirely to this linked DRAM unit. Keep it in
| BSS: the runtime loader clears it; saved comments restore project state.
        .balign 4
        .global tm_settings, tm_test_seed, tm_random_states, tm_cells
tm_settings:
        .zero 32
tm_test_seed:
        .zero 12
tm_random_states:
        .zero 32
tm_cells:
        .zero 24576

| MIDI note key stage: after stock TRAN and its range check, before stock KEY.
| The own quantizer bypasses stock KEY only on this generator's tracks.
        .text
        .balign 2
        .global tm_note_key_entry
 tm_note_key_entry:
        lea -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l %a2,-(%sp)
        move.l %d7,-(%sp)
        jsr tm_note_key
        addq.l #8,%sp
        tst.l %d0
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea 16(%sp),%sp
        bne.s 1f
        tst.l -64(%fp)
        bgt.s 2f
1:      jmp 0x4009fb80
2:      jmp 0x4009fb5e
        .ifdef MODWERK_EVENTS
        .global tm_take_note_key
 tm_take_note_key:
        .long tm_note_claims,tm_note_key_entry
        .endif

| Final project-load result, directly before the base's project-end seam.
        .text
        .global tm_project_loaded_hook
 tm_project_loaded_hook:
        tst.l %d0
        bge.s 1f
        tst.l %d2
        ble.s 1f
        move.l %d0,%d2
1:      lea -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l %d2,-(%sp)
        jsr tm_project_loaded
        addq.l #4,%sp
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea 16(%sp),%sp
        jmp 0x4008540e
