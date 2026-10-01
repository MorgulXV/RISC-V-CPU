# CPU verification

Run from `src/`:

```sh
make lint               # Standard Verilator lint (warnings are fatal)
make lint-all           # Extended lint audit; reports existing style/debug warnings
make test               # Run every maintained suite, including Spike comparisons
make test-shifts        # Original 31 shift regressions, Icarus only
make test-shifts-spike  # Shift encodings/results checked by Spike
make test-startup-spike # Real startup/linker files, ROM reads and arbitrary section sizes
make test-cpu-spike     # Arithmetic, control flow, stores, loads and .bss
make test-devices       # RAM, ROM, framebuffer, LED, SPI, reset and bus isolation
make sim                # Standalone SPI/CPU integration test
```

Dependencies: Python 3, Icarus Verilog (`iverilog`, `vvp`), Spike, and
`riscv64-unknown-elf-{as,ld,nm,objcopy}`. Tests use temporary directories and
create deterministic memory images; they do not overwrite the application's
`rom.mi`, `ram.mi`, `led.mi` or simulation artifacts. GCC and a device-tree
compiler are not required. Every simulation has a timeout. Failures return a
nonzero exit status, and `make test` runs all groups before reporting failure.

## Coverage

`check_cpu_spike.py` assembles the same programs for Spike and the RTL. It
compares the instruction address, encoding, next PC and all 32 registers at
every retirement, plus selected final RAM words against Spike's store log.
Each instruction program runs with an ideal memory model and with the complete
`topmodule`, including ROM selection, RAM and peripherals.
The testbench sets only the initial PC to `0x1000`, matching Spike's reset PC;
subsequent registers, addresses and control flow come from executed instructions.

- **Arithmetic:** all register and immediate ALU instructions, signed and
  unsigned comparisons, overflow/wraparound, immediate limits, shifts,
  deterministic random operands (seed `0x52563332`), register dependencies,
  overlapping source/destination registers, x0, LUI and AUIPC.
- **Control flow:** all six branches with taken/not-taken cases, equality and
  signed/unsigned boundaries, a backward loop, forward/backward JAL, JALR link
  values, negative offsets, clearing target bit zero, and `rd == rs1`. FENCE
  is checked for no architectural state change on this serial CPU.
- **Stores:** SB/SH/SW, byte lanes, preserving other bytes, negative offsets,
  zero data and the last implemented DRAM word. Final memory is checked
  independently of the CPU load path.
- **Loads:** LB/LBU/LH/LHU/LW, sign extension, all byte lanes, both aligned
  halfword lanes, negative offsets, consecutive distinct reads, load-use
  dependencies, x0 destinations, and the last implemented DRAM word.
- **Application startup:** all eight real boot/linker pairs run through the
  full SoC. Fifteen cases cover empty, one-byte, odd-sized and word-sized sections,
  including a 50-byte initialized table. RAM starts dirty; independent checks
  verify copied bytes, cleared BSS and untouched neighbors. ROM LB/LBU/LH/LHU/LW,
  a string, interleaved ROM/RAM loads and fetch recovery are compared with Spike.
- **BSS/stack:** a word-aligned `.bss (NOLOAD)` section in RAM is filled with
  nonzero values, cleared using the startup-style loop, read back, and written
  again. Stack store/load behavior at the RAM boundary is also checked.
- **Devices:** ROM initialization/chip enable/boundary, RAM write masks,
  single-cycle read requests, result hold/enable/reset, framebuffer dual read banks and latency,
  33 LED rows including wraparound, column order, blanking and latch behavior.
- **System:** actual external SPI edges and LSB-first bits, command bytes,
  two distinct gamepad replies, byte order/inversion, CPU MMIO reads, button
  output wiring, register reset and reset during an active transaction.
- **Bus isolation:** CPU stores into DRAM and framebuffer, and protection
  of DRAM from stores into ROM, SPI and unmapped regions.

The SPI integration bench replaces the obsolete bench that referenced removed
ports and signals. The test driver supplies a three-instruction polling program
instead of relying on whichever application image is currently installed.

## Results on 2026-09-23

| Test | Result |
| --- | --- |
| Shift regressions | 31/31 pass in RTL and Spike |
| Arithmetic | 709 retirements match Spike with both memory implementations |
| Control flow | 164 retirements match Spike with both memory implementations |
| Stores | 24 retirements and final memory match Spike with both implementations |
| Loads / ideal memory | 69 retirements match Spike |
| Loads / hardware RAM | 69 retirements match Spike |
| BSS/stack | 82 retirements match Spike with both memory implementations |
| Memory and display devices | 4,381 checks pass |
| SPI/CPU/reset integration | 155 checks pass |
| Bus isolation and ROM boundary reads | 10/10 checks pass |
| Real application startup | 15/15 cases match Spike and independent byte/guard checks |
| Standard Verilator lint | Pass, no warnings |

**All maintained Spike comparisons and all RTL test groups pass.** The
arithmetic/control/store/load/BSS programs execute 1,048 instructions for both
the ideal model and full SoC, and the separate shift regression checks 31 cases.
The real-startup suite adds 15 full-SoC cases.
These results describe the included tests, not complete ISA certification.

### Memory fixes verified by these tests

- The RAM now captures read data in one clock, making it available when the CPU
  reaches MEMORY2. The redundant second output register previously caused
  stale loads. `read_ram` explicitly checks a single enabled clock and confirms
  that the result remains valid after the request is deasserted.
- MEMORY1 now enables DRAM writes only for the DRAM address region. Stores to
  ROM, SPI or unmapped regions no longer corrupt DRAM word zero. They are
  ignored; the CPU still has no access-fault trap mechanism.

### BSS, initialized data and ROM

The application linker scripts place writable `.data` and `.bss` in RAM.
Startup now uses byte loads/stores and advances by one byte, so either section
may be empty, odd-sized or start on a non-word boundary. The same correction is
applied to all eight application boot files. ROM remains read-only.

The CPU shares its existing ROM port between instruction fetch and data loads.
`rom_re` selects the data address during the load's memory stages; it drops
before the next instruction fetch. ROM data enters the existing load-width and
sign-extension logic. This enables copying `.data` initializers from ROM and
reading `.rodata` strings/tables without adding another memory read port.

The startup suite uses the real application boot and linker files. To avoid
Spike's reserved debug address range, its fixture relocates only the ROM region
to `0x2000` and places a test prelude at `0x1000` to dirty RAM. The data/BSS layout
and actual startup loops remain those of the application. Boundary tests also
exercise ROM addresses zero and `0x3ffc` at the normal CPU reset address.
The new regressions reject both the former CPU without ROM data reads and the
former word-stepping startup for one-byte sections.

### Assessment and limits

**7/10 as an educational FPGA CPU prototype.** The design has a readable
multicycle execution model, correct tested ALU/control-flow behavior, and working
SPI/display integration. The previously reported RAM-load and store-decoding
bugs are fixed, and ROM data reads plus arbitrary-sized startup sections are now
covered. Exception handling and unsupported framebuffer/unmapped CPU reads remain
limitations; the numeric rating is a qualitative project assessment.

This is functional simulation coverage, not a certification of full RV32I
conformance or FPGA timing closure. ECALL/EBREAK trap handling is absent;
misaligned-access and illegal-instruction exceptions are not implemented or
validated by these tests. FENCE currently falls through the illegal-instruction
path while behaving as a no-op. The [RV32I specification](https://docs.riscv.org/reference/isa/v20240411/unpriv/rv32.html)
defines the system-instruction and instruction-alignment requirements. No
interrupt, CDC/metastability, synthesis-resource, clock-frequency or power claims
are made from these simulations.

`make lint` runs Verilator 5.052 with its standard warning set and passes
without suppressions. Width/index-size issues were corrected and intentional
no-op case defaults made explicit. `make lint-all` additionally enables
`-Wall -Wno-fatal` to report remaining filename, unused-signal/parameter,
debug-task variable-shadowing and synchronous/asynchronous reset-style warnings.
The extended audit is informational, not a claim of zero `-Wall` warnings.
Separate legacy C emulator tests were also run: `test_immediates.c` fails an
S-type fixture that encodes offset zero but expects one, and `unit_test.c`
incorrectly decodes a J immediate as an I immediate. Those files are separate
from the RTL and were not changed by this verification work.
