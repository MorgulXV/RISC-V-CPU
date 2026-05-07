# RISC-V CPU

A custom 32-bit RISC-V CPU (RV32I) built from scratch in SystemVerilog and synthesized on a Gowin GW5A-25A FPGA. It runs bare-metal C and assembly programs on real hardware, drives a 64×64 RGB LED matrix, and reads input from a PS2 DualShock gamepad over SPI.

Built as a *Jahresarbeit* (annual thesis project).  
Full written documentation (German): [`thesis/text.pdf`](thesis/text.pdf)

![Hardware photo](thesis/IMG_3295.png)

---

## Contents

- [Hardware](#hardware)
- [Emulator](#emulator)
- [CPU Architecture](#cpu-architecture)
- [Memory Map](#memory-map)
- [Peripherals](#peripherals)
- [Building an App](#building-an-app)
- [Example Apps](#example-apps)
- [Simulation](#simulation)
- [Synthesis](#synthesis)

---

## Hardware

| Component | Part |
|---|---|
| FPGA | Gowin GW5A-LV25MG121 (Tang Primer 25K) |
| Display | 64×64 HUB75E RGB LED matrix |
| Controller | PS2 DualShock gamepad (SPI) |

Pin assignments and connector wiring: [`src/PINOUT.md`](src/PINOUT.md)

---

## Emulator

Before writing any hardware, a software emulator of the RV32I ISA was written in C. It served as a way to understand and validate the architecture without FPGA toolchain overhead, and its execution traces were used to verify the hardware implementation later.

Source: [`emulator/`](emulator/)

| File | Description |
|---|---|
| `emulator.c` | Full RV32I emulator — fetch/decode/execute loop, 32 registers, 16 KB instruction and data memory |
| `test_immediates.c` | Unit tests for all five immediate encodings (I, S, B, U, J-type) |
| `unit_test.c` | Additional CPU unit tests |

**Build and run** (requires GCC or Clang):

```sh
cd emulator
make              # build
./emulator        # interactive step-through mode
make test-immediates  # run immediate decoding unit tests
```

The emulator runs step-by-step: after each batch of instructions it prints all 32 registers with their ABI names and current values.

---

## CPU Architecture

The CPU implements the **RV32I** base integer ISA. It is a **multi-cycle design** — each instruction takes multiple clock cycles, advancing through these stages:

```
FETCH → DECODE → EXECUTE → MEMORY1 → MEMORY2 → WRITEBACK
```

| Stage | Description |
|---|---|
| **FETCH** | Sends PC to instruction ROM, latches PC + 4 as next PC |
| **DECODE** | Extracts opcode, rd, rs1, rs2, funct3/7, sign-extends immediate |
| **EXECUTE** | ALU operation, branch condition, load/store address calculation |
| **MEMORY1** | Initiates memory read or write, routes store data to correct byte lanes |
| **MEMORY2** | Captures read data; sign/zero-extends for LB, LH, LBU, LHU |
| **WRITEBACK** | Writes result to register file, advances PC |

**Register file:** 32 × 32-bit registers (x0–x31). x0 is hardwired to zero.

**Supported instructions:**

| Type | Instructions |
|---|---|
| R-type | ADD, SUB, AND, OR, XOR, SLL, SRL, SRA, SLT, SLTU |
| I-type arithmetic | ADDI, ANDI, ORI, XORI, SLLI, SRLI, SRAI, SLTI, SLTIU |
| Loads | LW, LH, LB, LHU, LBU |
| Stores | SW, SH, SB |
| Branches | BEQ, BNE, BLT, BGE, BLTU, BGEU |
| Jumps | JAL, JALR |
| Upper immediate | LUI, AUIPC |

---

## Memory Map

Peripherals are memory-mapped — reads and writes to their address ranges are routed to the appropriate hardware block.

| Address range | Size | Device |
|---|---|---|
| `0x0000_0000 – 0x0000_FFFF` | 4 KB | Instruction ROM |
| `0x0001_0000 – 0x0001_FFFF` | 4 KB | Data RAM |
| `0x0002_0000 – 0x0002_FFFF` | 16 KB | Framebuffer |
| `0x0003_0000 – 0x0003_FFFF` | — | SPI / gamepad controller |

**Instruction ROM** is read-only block RAM initialised from `src/rom.mi`. Loading a program means replacing this file before synthesis.

**Data RAM** supports byte-enable writes — SB, SH, and SW all work correctly.

**Framebuffer** is a 64×64 array of 32-bit words, one per pixel. Only the lowest 3 bits are used: `[2]=R [1]=G [0]=B`, giving 8 colours total.

**SPI / gamepad** — reading `0x0003_0000` returns the current 16-bit button state of the DualShock controller (active-high, already inverted from raw SPI).

---

## Peripherals

### LED Controller

Continuously scans the framebuffer and outputs HUB75E signals (`ROW_ADDR`, `COL_ADDR`, `CLK`, `LATCH`, `OE`, `DATA_A/B`). The scan runs independently of the CPU — pixel writes take effect on the next scan pass.

Writing to the display from C:

```c
volatile unsigned int *fb = (volatile unsigned int *) 0x00020000;

fb[row * 64 + col] = 0x4;  // red
fb[row * 64 + col] = 0x2;  // green
fb[row * 64 + col] = 0x1;  // blue
fb[row * 64 + col] = 0x7;  // white
fb[row * 64 + col] = 0x0;  // off
```

### SPI Controller

Polls the PS2 DualShock using the standard 6-byte SPI transaction in a loop. After each transaction the 16-bit button state is latched into a register the CPU can read.

```c
volatile unsigned int *spi = (volatile unsigned int *) 0x00030000;
int buttons = spi[0];

if (buttons & 0x8000) { /* left  */ }
if (buttons & 0x4000) { /* down  */ }
if (buttons & 0x2000) { /* right */ }
if (buttons & 0x1000) { /* up    */ }
```

---

## Building an App

### Toolchain

The build scripts use `riscv64-unknown-elf-gcc`. The 64-bit toolchain targets RV32I correctly via `-march=rv32i`.

**macOS:**
```sh
brew install riscv-gnu-toolchain
```

**Ubuntu / Debian:**
```sh
sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf
```

**From source:** https://github.com/riscv-collab/riscv-gnu-toolchain

### Using the build scripts

Each app in `src/apps/<name>/` has a `build.sh`:

```sh
cd src/apps/snake
./build.sh
```

This compiles, strips to a raw binary, converts to `.mi` hex format, and copies the result to `src/rom.mi` ready for synthesis.

Each app directory contains:

| File | Purpose |
|---|---|
| `main.c` / `*.s` | Application source |
| `boot.s` | Startup stub — copies `.data`, zeroes `.bss`, calls `main()` |
| `link.ld` / `link.x` | Linker script — `.text` at ROM, `.data`/`.bss` at RAM |
| `build.sh` | Build script |

### Manual compilation

```sh
# 1. Compile and link
riscv64-unknown-elf-gcc \
  -march=rv32i -mabi=ilp32 \
  -ffreestanding -nostdlib -static \
  -fno-pic -fno-pie \
  -fdata-sections -ffunction-sections \
  -O2 -Wall -Wextra \
  -Wl,-T,link.ld -Wl,--gc-sections \
  boot.s main.c -o main.elf

# 2. Strip to raw binary
riscv64-unknown-elf-objcopy -O binary main.elf main.bin

# 3. Convert to hex (one 32-bit word per line)
hexdump -v -e '1/4 "%08x\n"' main.bin > rom.mi

# 4. Copy to src/ for synthesis
cp rom.mi ../../rom.mi

# Optional: inspect disassembly
riscv64-unknown-elf-objdump --disassemble-all main.elf > main.disasm
```

**Key compiler flags:**

| Flag | Purpose |
|---|---|
| `-march=rv32i` | Target RV32I base ISA |
| `-mabi=ilp32` | 32-bit integer ABI, no floating point |
| `-ffreestanding -nostdlib` | No hosted C library or crt0 |
| `-fno-pic -fno-pie` | No position-independent code |
| `-fdata-sections -ffunction-sections -Wl,--gc-sections` | Strip unused code and data |

To write a new app from scratch, copy an existing app directory. You need `boot.s` and `link.ld` as-is. Your entry point is `main()`. There is no standard library — use direct memory-mapped writes for all I/O.

---

## Example Apps

| App | Language | Description |
|---|---|---|
| `snake` | C | Snake game controlled with the DualShock d-pad |
| `spinning_cube` | C | Bouncing coloured box on the LED matrix |
| `swiss_flag` | C | Draws the Swiss flag |
| `show-controller` | C | Visualises live gamepad button state on the display |
| `display_controller` | C | Low-level HUB75E display driver demo |
| `infinity1`, `infinity2` | Assembly | Infinite loop demos |
| `led-red-asm` | Assembly | Lights LEDs using raw assembly |
| `led-write-manual` | Assembly | Manually writes pixel values |
| `led-write-sequence` | Assembly | Writes a pixel sequence |
| `loop-init-c` | C | Minimal C startup and loop |
| `test-datasection-c` | C | Tests that initialised `.data` variables are copied correctly |
| `test-dram-minimal` | Assembly | Minimal RAM read/write test |
| `test-spi` | C | Reads and displays gamepad input |

---

## Simulation

Requires [iverilog](https://github.com/steveicarus/iverilog). [GTKWave](https://gtkwave.sourceforge.net/) is optional. Run from `src/` so relative paths to `rom.mi`, `ram.mi`, and `led.mi` resolve correctly.

```sh
cd src
make sim    # compile testbench and run
make show   # open waveform in GTKWave
```

The testbench (`test/tb.sv`) instantiates the full top module, drives clock and reset, simulates SPI MISO responses, and checks that the SPI controller correctly delivers gamepad data to the CPU. A pre-configured signal layout for GTKWave is at `src/cpu_states.gtkw`.

---

## Synthesis

1. Open `Prozessor.gprj` in [Gowin EDA](https://www.gwin-semi.com/en/document/index/id/7)
2. Copy the desired app's `rom.mi` to `src/rom.mi`
3. Run **Synthesize** → **Place & Route** → **Program Device**

Pin constraints: `src/Prozessor.cst`  
Timing constraints: `src/Prozessor.sdc`

---

## License

[CC BY-NC 4.0](LICENSE) — free to use and adapt with attribution, non-commercial only.
