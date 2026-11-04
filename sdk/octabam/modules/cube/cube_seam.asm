; ---------------------------------------------------------------------------
; cube_seam -- the resident half of CUBE on core 1: the source seam.
;
; The stock `move a,x:>$20e` just before each track's source (payload B
; P:$1a2, tracks 1-4; Analog BD's seam, schema.DspHook) is a jsr here. Every
; track's source record comes through. A record cube.c wrote carries the
; signature $cb01 / $1e1e in w0 / w2 (stock w0/w2 are a ring position's
; halves; Analog BD's $ab09 / $0909 is the precedent). Anything else
; returns into the stock source untouched: this path clobbers r4, b, x0,
; which the stock source loads before it reads.
;
; A CUBE record: the next track's FLEX ring base is kept as the stock
; source keeps it, the engine (cube_engine.asm, assembled straight after
; this stub in the same section: cube_voice.asm, generate.py) renders the
; track's 16 frames, and the stock source is skipped (the seam's return is
; dropped, CONTADDR is the code after it). Static-stock: the stub and the
; engine are one P record above payload B's stock records (P:$1d9f..,
; schema.DspSection.free_top), booted with the payload, so there is no
; loader, no binding to test and no silent fallback. Payload A (tracks 5-8)
; has no CUBE code; cube.c never signs a track there.
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
        bsr     ce01                    ; the engine, r4 = the record
        move    ssh,x0                  ; drop the seam's return: the stock
        jmp     CONTADDR                ; source is skipped
