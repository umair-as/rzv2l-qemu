# <unit> — design

## Structure
QEMU types, files (`hw/arm/…`, `hw/misc/…`, `include/hw/…`), how they are wired into the SoC object and the machine.

## Register behaviour
| Register | Offset | Reset | Post-firmware | Class (config/command/status) | Behaviour | Evidence |
|---|---|---|---|---|---|---|

## Start states
Firmware mode vs direct mode (spec §9).

## Fidelity
Depth and honesty class per device (spec §7); the gaps this unit accepts.

## Decisions
DRs opened or applied.
