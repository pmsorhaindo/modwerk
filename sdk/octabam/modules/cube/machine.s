| CUBE registration: Analog BD's measured chooser and Part seams
| (modules/analog-bassdrum/machine.s), with CUBE's signature "CU\x01" in the
| unused NEIGHBOR playback bytes of a FLEX track, plus CUBE's own three:
| the SRC page select (the ring), the knob routine after its resolve (OSC B)
| and the track double-tap (no sample pool for a synthesized source).
| C functions (cube.c) clobber d0-d1/a0-a1; every call here saves what the
| interrupted stock code still needs.
        .text
        .global cube_machine_name, cube_src_names, cube_main_commit
        .global cube_src_commit, cube_src_commit2, cube_name_a, cube_name_b
        .global cube_setup_row, cube_chooser_row, cube_setup_open, cube_chooser_open
        .global cube_setup_edit6, cube_setup_draw6, cube_resolve_pb, cube_validate
        .global cube_stock_validate, cube_tick_hook, cube_pool_open
        .global cube_pagesel_hook, cube_knob_hook, cube_letter, cube_lfo_pmtr
        .global cube_rows_main, cube_rows_setup, cube_rows_draw

        .equ    CUBE_ROW, 5
        .equ    FLEX, 1
        .equ    SRC_CURSOR, 0x460d5c30
        .equ    PART_OFF, 0x8ed80
        .equ    PB_TABLE, 0x400d5f38

| a0 = the Part, d0 = the track, d1 = 1 assign / 0 leave; preserves all.
cube_sig:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l  %d1,-(%sp)
        move.l  %d0,-(%sp)
        move.l  %a0,-(%sp)
        jsr     cube_sig_write
        lea     12(%sp),%sp
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        rts

cube_admit:
        lea     -20(%sp),%sp
        movem.l %d1/%a0-%a1,8(%sp)
        move.l  %a0,(%sp)
        move.l  %d0,4(%sp)
        jsr     cube_admit_track
        movem.l 8(%sp),%d1/%a0-%a1
        lea     20(%sp),%sp
        rts

cube_machine_name:
        move.l  4(%sp),%d0
        cmpi.l  #CUBE_ROW,%d0
        beq.s   1f
        move.l  %d2,-(%sp)
        move.l  8(%sp),%d1
        jmp     (0x400334de).l
1:      lea     cube_name(%pc),%a0
        move.l  %a0,%d0
        rts

        .balign 4
cube_src_names:
        .long   0x400b3eac
        .long   0x400b3e98
        .long   0x400b7c67
        .long   0x400b5413
        .long   0x400b7a63
        .long   cube_name

cube_main_commit:
        lea     -12(%sp),%sp
        movem.l %d0-%d1/%a0,(%sp)
        movea.l %a1,%a0
        adda.l  %d0,%a0
        adda.l  #PART_OFF,%a0
        move.l  %d1,%d0
        cmpi.l  #CUBE_ROW,%d4
        bne.s   .mc_other
        bsr     cube_admit
        tst.l   %d0
        beq.s   .mc_refuse
        move.l  %d1,%d0
        moveq   #1,%d1
        bsr     cube_sig
        moveq   #FLEX,%d4
        bra.s   .mc_store
.mc_other:
        moveq   #0,%d1
        bsr     cube_sig
.mc_store:
        movem.l (%sp),%d0-%d1/%a0
        lea     12(%sp),%sp
        .word   0x7710,0x1084,0xd081
        jmp     (0x40079822).l
.mc_refuse:
        movem.l (%sp),%d0-%d1/%a0
        lea     12(%sp),%sp
        pea     0x30.w
        pea     cube_reject(%pc)
        jsr     (0x4005a2b8).l
        addq.l  #8,%sp
        jmp     (0x4007989c).l

cube_src_commit:
        pea     (0x4005a61c).l
        bra.s   cube_src_common
cube_src_commit2:
        pea     (0x4005a856).l
cube_src_common:
        move.l  (SRC_CURSOR).l,%d1
        lea     -12(%sp),%sp
        movem.l %d0/%d2/%a0,(%sp)
        movea.l %a1,%a0
        adda.l  %d0,%a0
        adda.l  #PART_OFF,%a0
        move.l  %d2,%d0
        cmpi.l  #CUBE_ROW,%d1
        bne.s   .sc_other
        bsr     cube_admit
        tst.l   %d0
        beq.s   .sc_refuse
        move.l  %d2,%d0
        moveq   #1,%d1
        bsr     cube_sig
        moveq   #FLEX,%d1
        bra.s   .sc_go
.sc_other:
        move.l  %d1,-(%sp)
        moveq   #0,%d1
        bsr     cube_sig
        move.l  (%sp)+,%d1
.sc_go:
        movem.l (%sp),%d0/%d2/%a0
        lea     12(%sp),%sp
        rts
.sc_refuse:
        movem.l (%sp),%d0/%d2/%a0
        lea     12(%sp),%sp
        moveq   #0,%d1
        move.b  (%a0),%d1
        move.l  %d1,(SRC_CURSOR).l
        pea     0x30.w
        pea     cube_reject(%pc)
        jsr     (0x4005a2b8).l
        addq.l  #8,%sp
        rts

cube_setup_open:
        move.b  (%a0),%d3
        move.l  %d0,-(%sp)
        mvs.b   %d3,%d0
        bsr     cube_row_type
        move.l  %d0,%d3
        move.l  (%sp)+,%d0
        mvs.b   %d3,%d4
        pea     (0x400bb704).l
        jmp     (0x400585e6).l

cube_setup_edit6:
        cmpi.l  #CUBE_ROW,%d2
        bne.s   1f
        moveq   #FLEX,%d2
1:      move.l  %d2,%d0
        lsl.l   #3,%d0
        add.l   %d2,%d2
        sub.l   %d2,%d0
        jmp     (0x4003a536).l
cube_setup_draw6:
        cmpi.l  #CUBE_ROW,%d6
        bne.s   1f
        moveq   #FLEX,%d6
1:      move.l  %d6,%d7
        lsl.l   #3,%d7
        add.l   %d6,%d6
        sub.l   %d6,%d7
        jmp     (0x4003cda0).l

cube_chooser_open:
        mvs.b   (%a0),%d0
        bsr     cube_row_type
        move.l  %d0,-(%sp)
        pea     (0x460e7386).l
        jmp     (0x40078890).l

cube_name_a:
        bsr.s   cube_name_pick
        jmp     (0x4003d722).l
cube_name_b:
        bsr.s   cube_name_pick
        jmp     (0x4004c374).l
cube_name_pick:
        bsr     cube_row_type
        lea     cube_src_names(%pc),%a0
        move.l  (%a0,%d0.l*4),%d1
        rts

cube_setup_row:
        mvs.b   (%a0),%d0
        lea     24(%sp),%sp
        bsr.s   cube_row_type
        jmp     (0x4003c986).l
cube_chooser_row:
        mvs.b   (%a0),%d0
        bsr.s   cube_row_type
        cmp.l   %d0,%d2
        bne.s   1f
        jmp     (0x400786ce).l
1:      jmp     (0x400786fc).l
cube_row_type:
        lea     -20(%sp),%sp
        movem.l %d1/%a0-%a1,8(%sp)
        move.l  %d0,(%sp)
        move.l  %a0,4(%sp)
        jsr     cube_type
        movem.l 8(%sp),%d1/%a0-%a1
        lea     20(%sp),%sp
        rts

cube_resolve_pb:
        mvs.b   %d5,%d0
        bsr     cube_row_type
        cmpi.l  #CUBE_ROW,%d0
        bne.s   1f
        move.l  %a0,-(%sp)
        jsr     cube_track_page
        addq.l  #4,%sp
        jmp     (0x40031ed6).l
1:      lea     (PB_TABLE).l,%a0
        jmp     (0x40031ece).l

cube_validate:
        jmp     cube_validate_part
cube_stock_validate:
        lea     -96(%sp),%sp
        movem.l %d2-%d7/%a2-%fp,(%sp)
        jmp     (0x40002320).l

cube_tick_hook:
        jsr     0x4005213c
        jsr     0x4007e940
        jsr     cube_ui_tick
        jmp     0x40052228

| Track double-tap (0x400791e4, the sample-slot window's entry): a CUBE
| track has no pool to open.
cube_pool_open:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     cube_selected_source
        tst.l   %d0
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        beq.s   1f
        rts
1:      move.l  %a2,-(%sp)
        tst.l   (0x460e70e0).l
        jmp     (0x400791ec).l

| 0x40055720(code, arg): the page select a page key's event calls.
| cube_page_pre: 0 stock, 1 consumed, 2 stock as a call then cube_page_post.
cube_pagesel_hook:
        move.l  8(%sp),-(%sp)
        move.l  8(%sp),-(%sp)
        jsr     cube_page_pre
        addq.l  #8,%sp
        tst.l   %d0
        beq.s   .ps_stock
        cmpi.l  #1,%d0
        beq.s   .ps_done
        move.l  8(%sp),-(%sp)
        move.l  8(%sp),-(%sp)
        bsr.s   .ps_stock
        addq.l  #8,%sp
        move.l  4(%sp),-(%sp)
        jsr     cube_page_post
        addq.l  #4,%sp
.ps_done:
        rts
.ps_stock:
        move.l  4(%sp),%d1              | displaced
        movea.l 8(%sp),%a1              | displaced
        jmp     (0x40055728).l

| 0x40055030 in the knob routine 0x40055008(slot, ticks), after it
| resolves (a3 = the page's descriptor, d5 = slot, a4 = ticks,
| d2 = slot * 4): OSC B's descriptor
| takes the knob and the routine returns through its epilogue (0x400554d4),
| so no playback byte is stored, sent or marked edited.
cube_knob_hook:
        cmpa.l  #cube_desc+0x1ca+0x38,%a3
        bne.s   1f
        move.l  %a4,-(%sp)
        move.l  %d5,-(%sp)
        jsr     cube_knob
        addq.l  #8,%sp
        jmp     (0x400554d4).l
1:      move.l  %d2,-(%sp)              | displaced
        move.l  398(%a3),-(%sp)         | displaced
        jmp     (0x40055036).l

| 0x40040132 in the track strip's drawer (audio tracks): `pea font` and
| `move.l -24(%fp,type*4),-(%sp)`, the strip glyph for the track's machine
| type (d4 = the track, a4 = its type). A CUBE track gets CUBE's glyph, a
| lowercase c (cube.c cube_glyph); every other track its stock glyph.
cube_letter:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        move.l  %d4,-(%sp)
        jsr     cube_strip_track
        addq.l  #4,%sp
        tst.l   %d0
        movem.l (%sp),%d0-%d1/%a0-%a1   | movem and lea keep the flags
        lea     16(%sp),%sp
        pea     (0x400bf10a).l
        bne.s   1f
        move.l  (-24,%fp,%a4.l*4),-(%sp)
        jmp     (0x4004013c).l
1:      pea     cube_glyph
        jmp     (0x4004013c).l

| 0x4003bff2 in the LFO SETUP page's PMTR formatter, SRC case: d0 = the
| track's machine type, a0 = its type byte. A CUBE track reads CUBE's page
| descriptor (table row 5, cube_ui_tick), so PMTR names CUBE's parameters.
cube_lfo_pmtr:
        bsr     cube_row_type
        lea     (PB_TABLE).l,%a0
        jmp     (0x4003c054).l

| CUBE runs on DSP core 1 only (tracks 1-4): the machine lists of tracks
| 5-8 keep stock's five rows. cube_rows (cube.c) is 6 on T1-T4, else 5.
| 0x40079248 `pea 5.w; pea 6.w` (main chooser: count, visible rows):
cube_rows_main:
        subq.l  #4,%sp
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     cube_rows
        move.l  %d0,16(%sp)
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        pea     0x6.w
        jmp     (0x40079250).l
| 0x400585fa `pea 5.w; pea 5.w` (SRC SETUP selector: count, visible rows):
cube_rows_setup:
        subq.l  #4,%sp
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     cube_rows
        move.l  %d0,16(%sp)
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        pea     0x5.w
        jmp     (0x40058602).l
| 0x40078678 `moveq #4,d0; cmp.l d2,d0; blt.s` (the main chooser draws
| row d2 only up to its last row): the last row is cube_rows - 1.
cube_rows_draw:
        lea     -12(%sp),%sp
        movem.l %d1/%a0-%a1,(%sp)
        jsr     cube_rows
        movem.l (%sp),%d1/%a0-%a1
        lea     12(%sp),%sp
        subq.l  #1,%d0
        cmp.l   %d2,%d0
        blt.s   1f
        jmp     (0x4007867e).l
1:      jmp     (0x400786a2).l

cube_name:
        .asciz  "CUBE"
cube_reject:
        .asciz  "CUBE: NO ROOM"
        .balign 2
