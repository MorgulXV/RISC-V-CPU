# RISC-V CPU

A custom 32-bit RISC-V CPU (RV32I) implemented from scratch in SystemVerilog, synthesized on a Gowin GW5A-25A FPGA. The CPU runs bare-metal C and assembly programs on real hardware, driving a 64×64 RGB LED matrix display and reading input from a PS2 DualShock gamepad.

This project was built as a *Jahresarbeit* (annual project / thesis).

---

## Hardware

| Component | Part |
|---|---|
| FPGA | Gowin GW5A-LV25MG121 (Tang Primer 25K) |
| Display | 64×64 HUB75E RGB LED matrix |
| Controller | PS2 DualShock gamepad (SPI) |

Wiring details for all connectors and FPGA pins are documented in [`src/PINOUT.md`](src/PINOUT.md).

---

## Emulator

Before implementing the CPU in hardware, a software emulator of the RV32I ISA was written in C. The emulator was used to understand and validate the architecture without dealing with FPGA-specific constraints, and its execution traces were used to verify the hardware implementation.

The emulator lives in [`emulator/`](emulator/).

| File | Description |
|---|---|
| `emulator.c` | Full RV32I emulator — fetch/decode/execute loop, 32 registers, 16 KB instruction memory, 16 KB data memory |
| `test_immediates.c` | Unit tests for all five immediate encodings (I, S, B, U, J-type) |
| `unit_test.c` | Additional CPU unit tests |

### Building and running

Requires a C compiler (GCC or Clang).

```sh
cd emulator
make            # build the emulator
./emulator      # run interactively — prompts for number of steps to execute
```

The emulator runs in a step-through mode: after each batch of instructions it prints the full register file (all 32 registers with ABI names and values) so you can inspect state at any point.

```sh
make test-immediates   # compile and run the immediate decoding unit tests
```

### Architecture

The emulator models the same memory map as the hardware:

- Instruction memory: 16 KB array at offset `0x0000`
- Data memory: 16 KB array at offset `0x10000`

A program is loaded by placing machine code into the `program[]` array in `emulator.c`. The interactive loop then lets you step through any number of instructions and inspect registers after each step.

---

## CPU Architecture

The CPU implements the **RV32I** base integer instruction set (no M/F/D/C extensions). It is a **multi-cycle design**: each instruction takes multiple clock cycles to complete, with the datapath advancing through the following stages on each clock edge:

```
FETCH → DECODE → EXECUTE → MEMORY1 → MEMORY2 → WRITEBACK
```

| Stage | What happens |
|---|---|
| **FETCH** | Sends PC to instruction ROM, latches next PC = PC + 4 |
| **DECODE** | Breaks the instruction word into opcode, rd, rs1, rs2, funct3/7 and sign-extends the immediate |
| **EXECUTE** | ALU operation, branch condition evaluation, address calculation for loads/stores |
| **MEMORY1** | Initiates memory read or write, routes store data to the correct byte lanes |
| **MEMORY2** | Captures read data from RAM or SPI peripheral; sign/zero-extends for LB/LH/LBU/LHU |
| **WRITEBACK** | Writes result to the register file, advances PC |

### Register file

32 general-purpose registers (x0–x31). x0 is hardwired to zero (writes are ignored).

### Supported instructions

All RV32I instructions are implemented:

- **R-type**: ADD, SUB, AND, OR, XOR, SLL, SRL, SRA, SLT, SLTU
- **I-type arithmetic**: ADDI, ANDI, ORI, XORI, SLLI, SRLI, SRAI, SLTI, SLTIU
- **Loads**: LW, LH, LB, LHU, LBU
- **Stores**: SW, SH, SB
- **Branches**: BEQ, BNE, BLT, BGE, BLTU, BGEU
- **Jumps**: JAL, JALR
- **Upper immediate**: LUI, AUIPC

---

## Memory Map

The CPU uses a flat 32-bit address space. Peripherals are memory-mapped: reads and writes to their address ranges are routed to the appropriate hardware block instead of RAM.

| Address range | Size | Device |
|---|---|---|
| `0x0000_0000 – 0x0000_FFFF` | 4 KB | Instruction ROM |
| `0x0001_0000 – 0x0001_FFFF` | 4 KB | Data RAM |
| `0x0002_0000 – 0x0002_FFFF` | 16 KB | Framebuffer |
| `0x0003_0000 – 0x0003_FFFF` | — | SPI / gamepad controller |

**Instruction ROM** is read-only block RAM initialised from `src/rom.mi`. A program is loaded by replacing this file before synthesis.

**Data RAM** supports byte-enable writes (SB, SH, SW all work correctly).

**Framebuffer** is a 64×64 array of 32-bit words. Each word represents one pixel. Only the lowest 3 bits are used: `[2]=R [1]=G [0]=B`, giving 8 colours. The LED controller reads the framebuffer continuously and drives the HUB75E panel.

**SPI / gamepad** — a single read from `0x0003_0000` returns the current 16-bit button state of the connected PS2 DualShock controller. Buttons are active-high (already inverted from the raw SPI data).

```c
volatile unsigned int *spi = (volatile unsigned int *) 0x00030000;
int buttons = spi[0];

if (buttons & 0x8000) { /* left  pressed */ }
if (buttons & 0x4000) { /* down  pressed */ }
if (buttons & 0x2000) { /* right pressed */ }
if (buttons & 0x1000) { /* up    pressed */ }
```

---

## Writing to the Display

Write a pixel by indexing into the framebuffer:

```c
volatile unsigned int *fb = (volatile unsigned int *) 0x00020000;

// fb[row * 64 + col] = colour
fb[10 * 64 + 20] = 0x4;  // red pixel at (row=10, col=20)
fb[10 * 64 + 21] = 0x2;  // green
fb[10 * 64 + 22] = 0x1;  // blue
fb[10 * 64 + 23] = 0x7;  // white
fb[10 * 64 + 24] = 0x0;  // off
```

---

## Peripherals

### LED Controller

Continuously scans the 64×64 framebuffer and outputs HUB75E signals (`ROW_ADDR`, `COL_ADDR`, `CLK`, `LATCH`, `OE`, `DATA_A/B`). The scan runs independently of the CPU — writing to the framebuffer takes effect on the next scan pass.

### SPI Controller

Polls the PS2 DualShock controller in a loop using the standard PS2 digital-mode protocol (6-byte SPI transaction). After each complete transaction the 16-bit button word is latched into a register readable by the CPU at `0x0003_0000`.

---

## Building an App

### Prerequisites

You need a RISC-V bare-metal GCC toolchain. The build scripts use `riscv64-unknown-elf-gcc` (the 64-bit toolchain works fine when targeting RV32I via `-march=rv32i`).

**macOS (Homebrew):**
```sh
brew install riscv-gnu-toolchain
```

**Ubuntu / Debian:**
```sh
sudo apt install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf
```

**From source:** https://github.com/riscv-collab/riscv-gnu-toolchain

You also need standard GNU tools: `objcopy`, `objdump`, `hexdump` (all included with the toolchain).

---

### Using the build scripts (recommended)

Each app lives in `src/apps/<name>/` and contains:

| File | Purpose |
|---|---|
| `main.c` / `*.s` | Application source |
| `boot.s` | Startup stub (copies `.data`, zeros `.bss`, calls `main`) |
| `link.ld` / `link.x` | Linker script (places `.text` at ROM, `.data`/`.bss` at RAM) |
| `build.sh` | Build script |

Run the build script from the app directory:

```sh
cd src/apps/snake
./build.sh
```

This produces `main.elf`, `main.bin`, `main.disasm`, and `rom.mi`. The script automatically copies `rom.mi` to `src/rom.mi`, ready for synthesis.

---

### Manual compilation

If you want to compile a C program without using the build scripts, here is the full pipeline:

**1. Compile and link:**
```sh
riscv64-unknown-elf-gcc \
  -march=rv32i -mabi=ilp32 \
  -ffreestanding -nostdlib -static \
  -fno-pic -fno-pie \
  -fdata-sections -ffunction-sections \
  -O2 -Wall -Wextra \
  -Wl,-T,link.ld -Wl,--gc-sections \
  boot.s main.c \
  -o main.elf
```

**2. Strip to a raw binary:**
```sh
riscv64-unknown-elf-objcopy -O binary main.elf main.bin
```

**3. Convert to hex (one 32-bit word per line, big-endian):**
```sh
hexdump -v -e '1/4 "%08x\n"' main.bin > rom.mi
```

**4. Copy into `src/` for synthesis:**
```sh
cp rom.mi ../../rom.mi   # from inside the app directory
```

**Optional — inspect the disassembly:**
```sh
riscv64-unknown-elf-objdump --disassemble-all main.elf > main.disasm
```

#### Flag reference

| Flag | Reason |
|---|---|
| `-march=rv32i` | Target the RV32I base ISA (no extensions) |
| `-mabi=ilp32` | 32-bit integer ABI, no floating point |
| `-ffreestanding` | No hosted C library assumed |
| `-nostdlib` | Do not link against libc or crt0 |
| `-static` | Fully static binary (no dynamic linker) |
| `-fno-pic -fno-pie` | No position-independent code |
| `-fdata-sections -ffunction-sections` | Allow linker to discard unused sections |
| `-Wl,--gc-sections` | Actually discard those unused sections |
| `-Wl,-T,link.ld` | Use the custom linker script |

#### Writing a new app from scratch

Copy an existing app directory as a starting point — you need `boot.s` and `link.ld` as-is. Your entry point is `main()`. There is no standard library; use direct memory-mapped writes for all I/O.

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
| `loop-init-c` | C | Minimal C startup / loop |
| `test-datasection-c` | C | Tests that initialised `.data` variables work |
| `test-dram-minimal` | Assembly | Minimal RAM read/write test |
| `test-spi` | C | Reads and displays gamepad input |

---

## Simulation

Requires [iverilog](https://github.com/steveicarus/iverilog). [GTKWave](https://gtkwave.sourceforge.net/) is optional for waveform viewing. The simulation must be run from the `src/` directory so that relative paths to `rom.mi`, `ram.mi`, and `led.mi` resolve correctly.

```sh
cd src
make sim      # compile testbench and run simulation
make show     # open the resulting tb.vcd in GTKWave
```

The testbench in `test/tb.sv` instantiates the full top module, drives clock and reset, simulates SPI MISO responses, and checks that the SPI controller correctly delivers gamepad data to the CPU.

A pre-configured GTKWave signal layout is saved in `src/cpu_states.gtkw`.

---

## Synthesis

1. Open `Prozessor.gprj` in [Gowin EDA](https://www.gwin-semi.com/en/document/index/id/7).
2. Place the desired app's `rom.mi` at `src/rom.mi`.
3. Run **Synthesize** → **Place & Route** → **Program Device**.

Pin constraints are in `src/Prozessor.cst` and timing constraints in `src/Prozessor.sdc`.

---

## License

[CC BY-NC 4.0](LICENSE) — free to use and adapt with attribution, non-commercial only.
