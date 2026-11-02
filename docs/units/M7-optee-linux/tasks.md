# M7-optee-linux — tasks

Merged with M7-optee-uboot (no fork change).

| ID | Task | Files | Test | Status |
|---|---|---|---|---|
| T1 | Requirements and decision: REQ-TEE-001/002, DR-0006 (REQ-GUEST-001 exception), project spec M7 line | `docs/spec/`, `docs/decisions/` | — | done |
| T2 | TEE kernel: vendor source and defconfig + `tee.config`; vendor DTB + `optee.dtso` overlay | `tests/guests/g1-tee/build-kernel.sh` | effective `.config` and `fdtget` of the node | done |
| T3 | OP-TEE user space: optee_client and hello_world 4.8.0, static; TA signed with the dev key | `tests/guests/g1-tee/build-optee-user.sh` | the TA call | done |
| T4 | TEE card | `tests/guests/sd/build-image.sh --tee` | the boot | done |
| T5 | Acceptance: driver, devices, supplicant, TA call; REQ-TEE-002 report; in the M7 run and log gate | `tests/acceptance/m7/tee.py`, `run.sh` | M7 ACCEPTANCE | done |

## Proofs (each break: the exact change → the red line)

| # | Break | Red line |
|---|---|---|
| 1 | The TEE card with the vendor DTB (no `/firmware/optee`) | `tee.py` driver: `FAIL driver: the OP-TEE driver probes; OP-TEE 4.8 (82a5cd3b)`; devices, supplicant and TA fail after it |
| 2 | The TEE card with the vendor kernel (no `CONFIG_OPTEE`) | the same four FAIL lines |
| 3 | The TEE card without the hello_world TA file | driver, devices, supplicant PASS; `FAIL trusted application: hello_world TA invoked, 42 -> 43, status 0` |
