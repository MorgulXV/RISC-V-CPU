# RISC-V CPU

A multi-cycle RV32I CPU implemented in SystemVerilog, targeting the Gowin GW5A-25A FPGA (Tang Primer 25K). Designed to drive a 64×64 HUB75E RGB LED matrix and read input from a PS2 DualShock controller over SPI.

## Architecture

The CPU is a 6-stage multi-cycle FSM:

```
FETCH → DECODE → EXECUTE → MEMORY1 → MEMORY2 → WRITEBACK
```

### Memory map

| Address range | Peripheral |
|---|---|
| `0x0000_xxxx` | Instruction ROM (4 KB) |
| `0x0001_xxxx` | Data RAM (4 KB) |
| `0x0002_xxxx` | Framebuffer |
| `0x0003_xxxx` | SPI / gamepad controller |

### Peripherals

- **LED_Controller** — drives a HUB75E 64×64 RGB matrix display, scanning rows and shifting pixel data from the framebuffer
- **spi_controller** — polls a PS2 DualShock controller at regular intervals and exposes button state as a memory-mapped register
- **gowin_clkdiv** — Gowin IP core for clock division

## Repository layout

```
src/
  cpu.sv                  top-level + CPU FSM + all submodules
  Prozessor.cst           pin constraints
  Prozessor.sdc           timing constraints
  rom.mi / ram.mi         BSRAM initialization files
  led.mi                  framebuffer initialization
  boot.s                  boot stub
  link.x                  linker script
  Makefile                simulation targets
  gowin_clkdiv/           Gowin clock-divider IP
  test/tb.sv              iverilog testbench
  apps/                   example programs
    snake/                Snake game (C)
    spinning_cube/        3-D spinning cube (C)
    swiss_flag/           Swiss flag demo (C)
    show-controller/      gamepad input visualizer (C)
    display_controller/   raw display driver demo (C)
    infinity1/, infinity2/  assembly demos
    led-red-asm/          LED demo (assembly)
    led-write-manual/     manual LED write (assembly)
    led-write-sequence/   LED sequence demo (assembly)
    loop-init-c/          C startup / loop demo
    test-datasection-c/   .data section test (C)
    test-dram-minimal/    minimal DRAM test (assembly)
    test-spi/             SPI / gamepad test (C)
  bin/generate_led.py     utility to generate LED init data
```

## Simulation

Requires [iverilog](https://github.com/steveicarus/iverilog) and optionally [GTKWave](https://gtkwave.sourceforge.net/).

```sh
cd src
make sim       # compile and run
make show      # open waveform in GTKWave
```

## Building apps

Each app has a `build.sh` that cross-compiles with a RISC-V toolchain (`riscv32-unknown-elf-gcc` or similar) and produces a `.mi` file suitable for loading into the ROM.

```sh
cd src/apps/snake
./build.sh
```

Copy the resulting `rom.mi` into `src/` before synthesizing.

## Synthesis

Open `Prozessor.gprj` in [Gowin EDA](https://www.gwin-semi.com/en/document/index/id/7) and run synthesis + place-and-route. Pin assignments are in `src/Prozessor.cst`.

See `src/PINOUT.md` for connector and peripheral wiring details.
