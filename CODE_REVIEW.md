# Coding-style assessment and future rebuild

This assessment covers the original C emulator (`emulator/emulator.c`, currently
identical to `../../../C/src/main.c`) and `src/cpu.sv`. The verification tooling
added during this review is not evidence of the original coding style.

The style is direct, explicit and close to the instruction set. Individual ALU
operations are easy to trace. The main improvement needed is to give shared
rules one owner: address decoding, operand capture, sign extension, instruction
retirement and error handling currently appear in many branches or files.

## What works well

- Fixed-width C register types and explicit byte assembly make the intended
  RV32 representation visible. Signed comparisons and arithmetic shifts are
  distinguished from their unsigned counterparts.
- Instruction decoding follows the ISA fields directly, making it useful for
  learning and debugging. Most individual instruction cases are straightforward.
- The RTL separates ROM, RAM, framebuffer, SPI and display controller modules.
  The multicycle FSM has recognizable fetch/decode/execute/memory/writeback stages.
- The project covers a complete vertical slice: emulator, RTL, linker/startup,
  application code and physical peripherals. That supplies useful concrete
  requirements for a rebuild.

## Where the style causes correctness problems

1. **Shared policy is copied into instruction cases.** In the emulator, memory
   guards compare absolute addresses to a 16 KiB array size, then subtract the
   64 KiB RAM base for indexing. A valid load at `0x10000` is rejected; lower
   addresses can pass the guard and underflow the index. One checked bus-access
   function should own region selection, offset calculation and access width.
2. **Reading operands and committing results are mixed.** Emulator JALR writes
   `rd` before reading `rs1`. For `jalr x1,0(x1)`, this overwrites the target.
   An isolated check produced PC `0x104` instead of `0x2000`. Capture operands,
   calculate the result/next PC, then commit state once.
3. **Bit-manipulation helpers depend on host C behavior.** `SIGN_EXTEND` shifts
   a signed value left; UBSan reports undefined behavior for sign-extending
   `255` from eight bits. Use helpers with explicitly defined unsigned operations
   and deliberate conversion, then test boundary values independently.
4. **Hardware timing is implicit.** The earlier shift and RAM-load bugs both
   came from using a value before the intended update was available. Document
   when an interface accepts a request and when its response is valid. Assert
   those timing rules in simulation, rather than relying on remembered stage names.
5. **Several concerns share one large function/file.** The C decoder updates
   state, prints traces, checks memory and handles interactive execution. Some
   prints ignore `show_instruction`. The RTL also contains disassembly helpers,
   unused trace aliases and commented-out alternatives alongside functional logic.
   Keep execution independent of presentation and debug output.
6. **Buildability and edge-case tests need to be routine.** The current emulator
   fails C11 compilation because `handle_ecall` is called before its static
   declaration. Its legacy tests also contain incorrect fixtures/decoding.
   A test target should compile from source and fail decisively before a binary
   is treated as a reference model.

I ran `cc -std=c11 -Wall -Wextra -Wconversion -Wshadow -fsyntax-only`:
11 warnings and two errors. Temporary isolated checks reproduced the JALR and
RAM-load problems; only a forward declaration was supplied to compile that
harness. UBSan reproduced the sign-extension problem. The emulator itself was
not modified as part of the ROM/startup repair.

## Habits worth changing

Use one naming/formatting convention, descriptive address-map constants and
small helpers for repeated decode/byte-lane operations. Remove obsolete code
from source once version control preserves it. Comments are most valuable for
an invariant or timing requirement; `// add` beside an addition carries little
information. Keep an exception or error result explicit instead of silently
falling through a default case or merely printing an error.

The switch-based approach is reasonable for this size of emulator. A rebuild
does not need a class hierarchy or one function per instruction. Useful boundaries
would be `decode`, `execute`, checked `bus_read/bus_write`, `commit`, and tracing,
with CPU state passed explicitly rather than accessed as a global everywhere.
For RTL, give the decoder, register file, execution units, load/store unit and
trap controller clear inputs/outputs as their responsibilities grow.

## Suggested order for a future rebuild

1. Define the memory map, reset/boot contract and bus request/response/error
   interface first. Keep linker scripts, startup and tests consistent with it.
2. Make the C model a deterministic, headless step function with explicit traps,
   and compare retirement state against Spike. Reuse the same programs for RTL.
3. Establish a verified RV32I baseline with architectural faults and a stable
   retirement trace. Keep a simple multicycle core until the interfaces are sound.
4. Add M operations behind an execution-unit interface. Then add the chosen
   machine-privilege/CSR/trap/interrupt behavior with focused tests for each.
5. Put networking behind the peripheral bus, with a documented register/FIFO
   interface and a small driver. Start with polling and add interrupt-driven
   behavior once the interrupt mechanism is verified.

This order is a design suggestion, not work implemented in the current patch.
It lets new features fit defined interfaces instead of requiring every device
or instruction to add special cases throughout the CPU.
