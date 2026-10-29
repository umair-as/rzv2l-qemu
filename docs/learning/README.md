# Learning docs

How this project's QEMU model works, explained from real monitor output, code and test runs. They explain *how* the RZ/V2L model is put together; *what* it must do is set by the spec ([`../spec/project.md`](../spec/project.md)) and does not change here.

**Who these docs are for.** Two readers at once: someone who has not modelled a machine in QEMU before, and someone who is about to model a Renesas SoC and wants to know where the manual, the silicon and the drivers disagree. The docs are a result of the project, not a by-product. Each milestone page ends with a **Pitfalls** section written for both readers: what the concept is and how it shows in QEMU, and what surprised us on this SoC, with the cite.

| File | Read it for |
|---|---|
| [`qemu-basics.md`](qemu-basics.md) | what QEMU is; the memory map; devices, objects and properties; how a register gets from the manual into the model |
| [`m1-machine-tour.md`](m1-machine-tour.md) | how the M1 board, SoC and devices fit together; a hands-on monitor tour |
| [`m2-first-character.md`](m2-first-character.md) | M2: reading the EVK registers at the U-Boot prompt; the SCIFA model, its tests, the hello probe, the first Linux lines; what the review found; the SCIFA pitfalls |
| [`testing.md`](testing.md) | qtests, the guest probe, the acceptance run, the device-tree check |
| [`building-and-testing.md`](building-and-testing.md) | the commands: building, running tests, style check, tracing, editor setup |
| [`glossary.md`](glossary.md) | the terms |
| [`STYLE.md`](STYLE.md) | how these docs are written (adapted Simple Technical English); read it before you add to them |

Read them in that order the first time. Each unit adds one page at its end (one file per milestone, extended per unit), and the general files do not grow. A file about a milestone starts with a context box that links the spec and unit files of that milestone.

**Conventions.** Quotes come from QEMU's own docs in the `qemu/` submodule (v11.1.2) and are cited by path. Code references are `qemu/<file>:<line>` on `rzv2l-dev`; each file names the fork commit its line numbers are at. `§N` means a section of the same file, `` `file.md` §N `` a section of another one.
