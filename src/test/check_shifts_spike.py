#!/usr/bin/env python3
"""Check the RTL testbench's exact shift encodings and results against Spike."""

from pathlib import Path
import subprocess
import tempfile


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, timeout=30, **kwargs)


def main():
    source = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="cpu-shifts-") as directory:
        work = Path(directory)
        simulation = work / "shifts.vvp"
        run("iverilog", "-g2012", "-s", "tb_shifts", "-o", str(simulation),
            str(source / "test/tb_shifts.sv"), str(source / "cpu.sv"))
        result = run("vvp", str(simulation), "+vectors", capture_output=True)
        vectors = [line.split()[1:] for line in result.stdout.splitlines()
                   if line.startswith("VECTOR ")]
        if len(vectors) != 31:
            raise RuntimeError(f"Expected 31 RTL vectors, got {len(vectors)}")

        assembly = [".section .text", ".globl _start", "_start:"]
        for index, (instruction, value, amount, expected) in enumerate(vectors, 1):
            assembly += [
                f"li x1, 0x{value}", f"li x2, 0x{amount}",
                f".word 0x{instruction}", f"li x4, 0x{expected}",
                f"li x5, {index * 2 + 1}", "bne x3, x4, report",
            ]
        # Spike's HTIF exit protocol: 1 means success, odd values encode failure.
        assembly += [
            "li x5, 1", "report:", "la x6, tohost", "sw x5, 0(x6)",
            "1: j 1b", '.section .tohost,"aw",@progbits', ".balign 64",
            ".globl tohost", "tohost: .dword 0", ".balign 64",
            ".globl fromhost", "fromhost: .dword 0",
        ]
        program = work / "shifts.s"
        program.write_text("\n".join(assembly) + "\n")
        executable = work / "shifts.elf"
        object_file = work / "shifts.o"
        run("riscv64-unknown-elf-as", "-march=rv32i", "-mabi=ilp32",
            "-o", str(object_file), str(program))
        # With no device tree or boot ROM, execute directly at Spike's reset PC.
        linker_script = work / "shifts.ld"
        linker_script.write_text(
            "ENTRY(_start) SECTIONS { . = 0x1000; "
            ".text : { *(.text) } .tohost : { *(.tohost) } }\n")
        run("riscv64-unknown-elf-ld", "-m", "elf32lriscv", "-T", str(linker_script),
            "--no-relax", "-o", str(executable), str(object_file))
        run("spike", "--isa=RV32I", "--disable-dtb", "-m0x1000:0x20000", str(executable))
        print(f"PASS: RTL and Spike agree on all {len(vectors)} shift checks")


if __name__ == "__main__":
    main()
