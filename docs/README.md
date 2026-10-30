# docs

| Path | What it is |
|---|---|
| [`spec/`](spec/) | the specification ([`project.md`](spec/project.md)), the requirement IDs, traceability. Everything else follows from it. |
| [`device-map.md`](device-map.md) | every MMIO window, IRQ, clock and reset of the board, how each is modelled, and the evidence |
| [`sources.md`](sources.md) | the pinned sources, and which source wins in which domain |
| [`decisions/`](decisions/) | decision records (DR-NNNN) |
| [`research/`](research/) | per-block notes from the manual and the pinned guest code |
| [`evidence/`](evidence/) | measurements on the real EVK, each with its image and boot stage; [`requests.md`](evidence/requests.md) lists the read commands and their side effects |
| [`experiments/`](experiments/) | claims checked without full evidence (EXP-NNN) |
| [`units/`](units/) | one folder per work unit: spec, tasks and proofs ([`README`](units/README.md) explains the names) |
| [`learning/`](learning/) | how the model works, explained from real runs |

**Reading order:** `spec/project.md` §1-§9, `device-map.md`, then `learning/README.md`. For a block, its row in the device map, its research note, then its unit folder.
