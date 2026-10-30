# docs

| Path | What it is |
|---|---|
| [`walkthrough.md`](walkthrough.md) | for a user of the repo: build, then run each milestone yourself, with what you should see |
| [`milestones.md`](milestones.md) | progress: milestones, units, SoC blocks, what comes next |
| [`spec/`](spec/) | the specification ([`project.md`](spec/project.md)), the requirement IDs, traceability. Everything else follows from it. |
| [`device-map.md`](device-map.md) | every MMIO window, IRQ, clock and reset of the board, how each is modelled, and the evidence |
| [`sources.md`](sources.md) | the pinned sources, and which source wins in which domain |
| [`decisions/`](decisions/) | decision records (DR-NNNN) |
| [`research/`](research/) | per-block notes from the manual and the pinned guest code |
| [`evidence/`](evidence/) | measurements on the real EVK, each with its image and boot stage; [`requests.md`](evidence/requests.md) lists the read commands and their side effects |
| [`experiments/`](experiments/) | claims checked without full evidence (EXP-NNN) |
| [`units/`](units/) | one folder per work unit: spec, tasks and proofs ([`README`](units/README.md) explains the names) |
| [`learning/`](learning/) | how the model works, explained from real runs |

**Words you will meet everywhere** (full list: [`learning/glossary.md`](learning/glossary.md)):

| Word | Meaning |
|---|---|
| EVK | the physical Renesas RZ/V2L SMARC board; the model imitates it |
| G0 | the plain upstream Linux kernel (kernel.org v6.12.59), its upstream device tree and a BusyBox shell: the first software the model must boot |
| G1, G2 | Renesas's own software stack for the board (G1); products built on it (G2) |
| DTB-U | the upstream device tree for the board, used unmodified |
| M0-M9 | milestones ([spec §17](spec/project.md#17-milestones)): M1 machine skeleton, M2 first character on the serial port, M3 Linux shell |
| M3a, M3b | the two stages of M3: Linux's early console prints (M3a, done in M2), then the real serial driver up to a shell (M3b) |
| M3b-cpg, M3b-shell, … | work units: one block or step each (`units/`) |
| UNIMP | a stub window: QEMU logs every access, reads 0, ignores writes |
| direct mode | QEMU loads the kernel itself (`-kernel`), with no firmware; devices start as the firmware would leave them |
| R30, X01, EVK-R20 | row IDs of measurements on the EVK (`evidence/`) |
| gap 18 | a numbered row in the device map's list of known differences from the board (`device-map.md` §4) |

**Reading order:** `spec/project.md` §1-§9, `device-map.md`, then `learning/README.md`. For a block, its row in the device map, its research note, then its unit folder.
