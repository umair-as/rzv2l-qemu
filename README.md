# 🖥️ qemu-rzv2l

**A QEMU machine model of the Renesas RZ/V2L SMARC EVK, built to run the board's real software, unmodified.**

![Target](https://img.shields.io/badge/target-RZ%2FV2L%20SMARC%20EVK-0a5ad4)
![SoC](https://img.shields.io/badge/SoC-R9A07G054L2-6f42c1)
![CPU](https://img.shields.io/badge/CPU-2%C3%97%20Cortex--A55-2ea44f)
![QEMU](https://img.shields.io/badge/QEMU-aarch64--softmmu-ff6f00)
![Status](https://img.shields.io/badge/status-M3%20done%3A%20Linux%20to%20a%20shell-2ea44f)

---

## ✨ What this is

The RZ/V2L is a Renesas SoC with two Arm Cortex-A55 cores, a GIC-600 interrupt controller and 2 GB of DDR4 on its evaluation kit. This project adds a machine for it to QEMU, so that software built for the physical board boots in emulation **without changes to that software**:

- 🐧 **mainline Linux** with the upstream device tree
- 📦 **the Renesas vendor BSP** kernel and userspace
- 🔐 later, **the vendor firmware chain**: Trusted Firmware-A, OP-TEE and U-Boot

The point is not a machine that merely boots. It is a machine whose devices behave the way the silicon does, so the emulator can be trusted for development, CI and debugging when the board is not at hand.

## 🎯 Principles

| | Principle | In practice |
|---|---|---|
| 🔎 | **Evidence before implementation** | Every device behaviour traces to the hardware manual, the guest code that depends on it, and measurements on a physical EVK. |
| 🚫 | **Never modify the guest** | No device-tree edits, driver patches or invented boot arguments. Anything the model cannot satisfy is recorded as a fidelity gap. |
| ⚖️ | **Never silently wrong** | A device either behaves as the hardware does, or fails in a way the guest can see. |
| 🧪 | **Booting is not proof** | Device models are verified by tests that assert hardware-manual values (reset values, ID registers), and each test is checked to fail when the model is broken. |
| 🔁 | **Two start states** | Devices start either at the manual's power-on reset values (firmware boot) or at the state the firmware leaves behind, as measured on the board (direct kernel boot). |

## 🧩 Software it targets

```mermaid
flowchart LR
    subgraph G0["🐧 G0 · primary acceptance"]
        A["mainline Linux<br/>+ upstream DTB<br/>+ BusyBox initramfs"]
    end
    subgraph G1["📦 G1 · acceptance"]
        B["Renesas vendor BSP<br/>kernel, TF-A, U-Boot, OP-TEE"]
    end
    subgraph G2["🏭 G2 · integration only"]
        C["products built<br/>on the BSP"]
    end
    G0 --> G1 --> G2
    style G0 fill:#dcfce7,stroke:#16a34a,color:#14532d
    style G1 fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    style G2 fill:#f3f4f6,stroke:#6b7280,color:#374151
```

**G = guest tier**: what QEMU runs, and how much it counts for acceptance. G0 and G1 are built or fetched by this project and pinned; G2 is never a dependency. Defined in [specification](docs/spec/project.md) §2.

## 🗺️ Roadmap

```mermaid
flowchart LR
    M0["M0<br/>research<br/>baseline"] --> M1["M1<br/>machine<br/>skeleton"] --> M2["M2<br/>first<br/>character"] --> M3["M3<br/>mainline Linux<br/>to a shell"] --> M4["M4<br/>vendor<br/>kernel"]
    M4 --> M5["M5<br/>storage"] --> M6["M6<br/>networking"] --> M7["M7<br/>real U-Boot<br/>+ firmware"] --> M8["M8<br/>full boot<br/>chain"] --> M9["M9<br/>platform<br/>behaviour"]
    classDef bring fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef linux fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef fw fill:#ede9fe,stroke:#7c3aed,color:#4c1d95
    class M0,M1,M2 bring
    class M3,M4,M5,M6 linux
    class M7,M8,M9 fw
```

🟧 bring-up · 🟩 Linux · 🟪 firmware and platform. **Where it stands:** ✅ M0-M3: the plain upstream Linux kernel boots to a shell on both CPUs, which is the v1.0 target. ⏭️ Next: M4, Renesas's own kernel. Progress, units and blocks: [Milestones](docs/milestones.md). Exit criteria: the [specification](docs/spec/project.md).

## 🚀 Building

```bash
git clone --recurse-submodules https://github.com/umair-as/rzv2l-qemu.git
cd rzv2l-qemu
mkdir -p build/qemu && cd build/qemu
../../qemu/configure --target-list=aarch64-softmmu --disable-docs
ninja qemu-system-aarch64
```

Rebuilding, running the tests, style checks, tracing and editor setup: [Building and testing by hand](docs/learning/building-and-testing.md).

> [!NOTE]
> The `rzv2l-smarc` machine boots the upstream Linux kernel to a BusyBox shell on the serial console. Storage, Ethernet, I2C and USB are stubs for now, so their drivers fail at boot; [Milestones](docs/milestones.md) shows what is modelled.

The QEMU port lives in a fork, included as the `qemu/` submodule. It carries only code in the shape upstream QEMU would accept; the specification, research, evidence and tests live in this repository.

## 📚 Documentation

| | Document | What it holds |
|---|---|---|
| 🏁 | [Milestones](docs/milestones.md) | progress: what is done, what comes next |
| 📐 | [Specification](docs/spec/project.md) | goals, rules, fidelity classes, milestones |
| 📋 | [Requirements](docs/spec/requirements.md) | the requirement catalogue, traced to tests |
| 🗺️ | [Device map](docs/device-map.md) | every MMIO window, interrupt, clock and reset, with evidence |
| 🧭 | [Decisions](docs/decisions/) | decision records and their alternatives |
| 🎓 | [Learning](docs/learning/) | how QEMU models a machine; building and testing by hand |

> [!NOTE]
> The RZ/V2L hardware manual and board manuals are © Renesas and are not redistributed here. The repository keeps only an index and checksums; obtain the documents from Renesas.

## 🤖 How it is built

> [!IMPORTANT]
> Specifications, designs and reviews are human-led. Much of the research and code is written by AI agents under that review; all model code on the fork's `rzv2l-dev` branch is agent-assisted. QEMU's contribution policy declines AI-generated code, so the device models here serve as a working prototype and test oracle and cannot go upstream as they are. Whether an upstream path exists at all is an open question.

Agent instructions are in [AGENTS.md](AGENTS.md).
