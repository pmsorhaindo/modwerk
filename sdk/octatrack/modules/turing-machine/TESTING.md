# Turing Machine 0.5.0-experimental — software qualification in progress

**Hardware untested / #1697 draft.** No physical USB write, flash, MIDI send, listening or reboot was performed. This record applies only to the module port on base 0.7.9; prior turing-arpgen results are historical and do not qualify it.

The current package uses the stock ABI-2 generator host, with no base changes. FUNC+LOCK is retired by Michael's 18 November 2026 decision; FUNC+AMP must be released before editing SCALE/ROOT. The integer note engine and all other expected behavior remain the reference contract. Saved SCALE IDs are still OFF/MAJ/MIN, mapped to shared SDK IDs 0/1/6. A negative down-snap at note zero is dropped.

Final commands, sizes and observations will be recorded after the software runs finish. Hardware, physical Keep/Undo, concurrent-module audio and physical reboot remain not tested.
