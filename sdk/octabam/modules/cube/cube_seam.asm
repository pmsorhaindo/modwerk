; ---------------------------------------------------------------------------
; cube_seam -- the resident half of CUBE on each core: the source seam.
;
; The stock `move a,x:>$20e` just before each track's source (payload A
; P:$39c, B P:$1a2; Analog BD's seam, schema.DspHook) is a jsr here. Every
; track's source record comes through. A record cube.c wrote carries the
; signature $cb01 / $1e1e in w0 / w2 (stock w0/w2 are a ring position's
; halves; Analog BD's $ab09 / $0909 is the precedent). Anything else
; returns into the stock source untouched: this path clobbers r4, b, x0,
; which the stock source loads before it reads.
;
; A CUBE record: the next track's FLEX ring base is kept as the stock
; source keeps it, then the engine runs if the dynload loader has bound
; it -- X:$235+$1f (id $1f's proc entry) is no longer the build's null
; stub (NULLPROC, per payload) -- and the stock source is skipped (the
; seam's return is dropped, CONTADDR is the code after it). Unbound, the
; track's 16 frames are silence: the "silent source" a track the core
; cannot carry renders. The engine lives in the arena, not here.
; Labels csNN, one length.
; ---------------------------------------------------------------------------

cs01:
        move    a,x:>$20e               ; the stock instruction the jsr replaced
        move    x:>$209,r4              ; this track's source record
        move    #>$00cb01,x0
        move    x:(r4),b
        and     #>$ffff,b
        eor     x0,b                    ; Z from b1 (b2 holds the word's top
        bne     cs02                    ; byte: AGENTS.md stale A2)
        move    #>$001e1e,x0
        move    x:(r4+$2),b
        and     #>$ffff,b
        eor     x0,b
        beq     cs03
cs02:
        rts                             ; not CUBE: the stock source
cs03:
        move    x:>$20b,a               ; keep the next track's FLEX ring base
        add     #>$80,a
        move    a,x:>$20b
        move    x:>$254,b               ; id $1f's proc
        move    #>NULLPROC,x0
        cmp     x0,b
        beq     cs04
        move    b1,r1
        jsr     (r1)                    ; the engine, r4 = the record
        bra     cs05
cs04:
        clr     a                       ; not loaded on this core yet: silence
        move    #$0,r0
        do      #<$20,cs06
        move    a,x:(r0)+
cs06:
        move    #>$10,n7
cs05:
        move    ssh,x0                  ; drop the seam's return: the stock
        jmp     CONTADDR                ; source is skipped
