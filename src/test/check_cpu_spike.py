#!/usr/bin/env python3
"""Deterministic RV32I programs: compare every retired register and PC to Spike."""
import argparse
from pathlib import Path
import random
import re
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parent.parent
R_OPS = ('add', 'sub', 'xor', 'or', 'and', 'sll', 'srl', 'sra', 'slt', 'sltu')
I_OPS = ('addi', 'xori', 'ori', 'andi', 'slti', 'sltiu')


def run(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"{' '.join(map(str, args))}\n{result.stdout}{result.stderr}")
    return result.stdout


def arithmetic():
    code = []
    values = (0, 1, 31, 32, 0x7fffffff, 0x80000000, 0xffffffff, 0xa5a55a5a)
    for index, a in enumerate(values):
        b = values[-index-1]
        code += [f'li x1, {a}', f'li x2, {b}']
        code += [f'{op} x{3+i}, x1, x2' for i, op in enumerate(R_OPS)]
        for imm in (-2048, -1, 0, 1, 2047):
            code += [f'{op} x{3+i}, x1, {imm}' for i, op in enumerate(I_OPS)]
        for amount in (0, 1, 31):
            code += [f'{op} x3, x1, {amount}' for op in ('slli', 'srli', 'srai')]
    # Register aliases, dependencies, x0 writes, and deterministic random operands.
    rng = random.Random(0x52563332)
    for reg in range(1, 32):
        code += [f'li x{reg}, {rng.getrandbits(32)}']
    for _ in range(220):
        rd, rs1, rs2 = (rng.randrange(32) for _ in range(3))
        code += [f'{rng.choice(R_OPS)} x{rd}, x{rs1}, x{rs2}']
    code += ['addi x0, x0, 123', 'add x5, x0, x0', 'addi x5, x5, -1',
             'add x5, x5, x5', 'sub x5, x5, x5']
    for imm in (0, 1, 0x7ffff, 0x80000, 0xfffff):
        code += [f'lui x6, {imm}', f'auipc x7, {imm}']
    return code


def control():
    code = []
    # Both outcomes, equality, and signed/unsigned boundary comparisons.
    for op in ('beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu'):
        for a, b in ((0, 0), (0, 1), (1, 0), (0x80000000, 1), (1, 0xffffffff)):
            code += [f'li x1, {a}', f'li x2, {b}', f'{op} x1, x2, 1f',
                     'addi x3, x3, 1', '1: addi x4, x4, 1']
    code += ['li x5, 6', '2: addi x5, x5, -1', 'bne x5, x0, 2b',
             'jal x6, 3f', 'addi x7, x7, 99', '3: auipc x8, 0',
             'jal x0, 5f', '4: addi x9, x9, 1', 'jalr x0, 0(x6)',
             '5: jal x6, 4b', 'la x10, 6f', 'addi x10, x10, 1',
             'jalr x10, 0(x10)', 'addi x11, x11, 99',
             '6: la x12, 7f', 'addi x12, x12, 16', 'jalr x13, -16(x12)',
             'addi x11, x11, 99', '7: addi x14, x13, 0', 'fence']
    return code


def memory():
    code = ['li x20, 0x10000', 'li x1, 0x80ff7f01', 'sw x1, 0(x20)',
            'li x2, 0x12345678', 'sw x2, 4(x20)', 'lw x3, 0(x20)', 'lw x4, 4(x20)']
    for lane in range(4):
        code += [f'lb x5, {lane}(x20)', f'lbu x6, {lane}(x20)']
    for lane in (0, 2):
        code += [f'lh x7, {lane}(x20)', f'lhu x8, {lane}(x20)']
    for lane in range(4):
        code += [f'li x9, {0x90+lane}', f'sb x9, {lane}(x20)', 'lw x10, 0(x20)']
    for lane in (0, 2):
        code += ['li x9, 0x8001', f'sh x9, {lane}(x20)', 'lw x10, 0(x20)']
    # Negative offsets, boundary addresses, write-after-read and load-use dependencies.
    code += ['addi x21, x20, 16', 'sw x2, -8(x21)', 'lw x11, -8(x21)',
             'add x11, x11, x11', 'sw x11, -4(x21)', 'lw x12, -4(x21)',
             'li x22, 0x13ffc', 'sw x1, 0(x22)', 'lw x13, 0(x22)',
             'lw x0, 0(x20)', 'addi x14, x0, 1']
    for offset in range(0, 64, 4):
        code += [f'lw x15, {offset}(x20)']
    return code


def stores():
    code = ['li x20, 0x10000', 'li x1, 0x12345678', 'sw x1, 0(x20)']
    for lane in range(4):
        code += [f'li x2, {0xa0+lane}', f'sb x2, {lane}(x20)']
    for lane in (0, 2):
        code += ['li x3, 0xbeef', f'sh x3, {4+lane}(x20)']
    code += ['addi x21, x20, 16', 'sw x1, -8(x21)', 'sw x0, -4(x21)',
             'li x22, 0x13ffc', 'sw x3, 0(x22)']
    return code


def bss():
    # Give .bss nonzero contents before exercising the startup zeroing loop.
    return ['la x20, test_bss_start', 'la x21, test_bss_end', 'li x22, 0xdeadbeef',
            '1: sw x22, 0(x20)', 'addi x20, x20, 4', 'bltu x20, x21, 1b',
            'la x20, test_bss_start',
            '2: beq x20, x21, 3f', 'sw x0, 0(x20)', 'addi x20, x20, 4', 'j 2b',
            '3: la x20, test_bss_start',
            *[f'lw x{reg+1}, {reg*4}(x20)' for reg in range(8)],
            'sw x22, 0(x20)', 'lw x23, 0(x20)',
            # Exercise the stack at the RAM boundary used by the app linker.
            'li sp, 0x14000', 'addi sp, sp, -16', 'sw x22, 12(sp)',
            'lw x24, 12(sp)', 'addi sp, sp, 16',
            '.section .bss', '.balign 4', 'test_bss_start:', '.zero 32',
            'test_bss_end:', '.section .text']


def oracle(work, instructions, has_bss=False):
    program = work / 'program.s'
    program.write_text('\n'.join([
        '.section .text', '.globl _start', '_start:', *instructions,
        '.globl done', 'done:', 'li x5, 1', 'la x6, tohost', 'sw x5, 0(x6)',
        '1: j 1b', '.section .tohost,"aw",@progbits', '.balign 64',
        '.globl tohost', 'tohost: .dword 0', '.balign 64',
        '.globl fromhost', 'fromhost: .dword 0',
        '.section .data', '.zero 0' if has_bss else '.zero 16384',
    ]) + '\n')
    linker = work / 'program.ld'
    linker.write_text('ENTRY(_start) SECTIONS { . = 0x1000; .text : { *(.text) } '
                      '. = 0x10000; .data : { *(.data) } .bss (NOLOAD) : { *(.bss) } '
                      '. = 0x18000; .tohost : { *(.tohost) } }\n')
    obj, elf = work / 'program.o', work / 'program.elf'
    run('riscv64-unknown-elf-as', '-march=rv32i', '-mabi=ilp32', '-o', str(obj), str(program))
    run('riscv64-unknown-elf-ld', '-m', 'elf32lriscv', '--no-relax', '-T', str(linker),
        '-o', str(elf), str(obj))
    symbols = run('riscv64-unknown-elf-nm', str(elf))
    done = int(re.search(r'^([0-9a-f]+) T done$', symbols, re.M)[1], 16)
    if done >= 0x4000:
        raise RuntimeError('Program exceeds the hardware instruction ROM')
    binary = work / 'text.bin'
    run('riscv64-unknown-elf-objcopy', '-O', 'binary', '-j', '.text', str(elf), str(binary))
    data = binary.read_bytes()
    words = [0x13] * 4096
    for index in range(0, len(data), 4):
        words[1024+index//4] = int.from_bytes(data[index:index+4], 'little')
    (work / 'rom.mi').write_text(''.join(f'{word:08x}\n' for word in words))
    (work / 'ram.mi').write_text('00000000\n' * 4096)
    (work / 'led.mi').write_text('0000\n' * 4096)
    log = work / 'spike.log'
    run('spike', '--isa=RV32I', '--disable-dtb', '-m0x1000:0x20000', '-l',
        '--log-commits', f'--log={log}', str(elf))
    return read_trace(log, done)


def read_trace(log, done):
    regs, trace, memory_bytes = [0]*32, [], {}
    for line in log.read_text().splitlines():
        match = re.match(r'core\s+0: 3 0x([0-9a-f]+) \(0x([0-9a-f]+)\)(.*)', line)
        if not match:
            continue
        pc, instruction = int(match[1], 16), int(match[2], 16)
        if pc == done:
            break
        for reg, value in re.findall(r'\bx\s*(\d+)\s+0x([0-9a-f]+)', match[3]):
            regs[int(reg)] = int(value, 16)
        if instruction & 0x7f == 0x23:
            store = re.search(r'mem 0x([0-9a-f]+) 0x([0-9a-f]+)', match[3])
            if not store:
                raise RuntimeError('Spike store trace is missing its address/data')
            address, value = int(store[1], 16), int(store[2], 16)
            for lane in range(1 << ((instruction >> 12) & 7)):
                memory_bytes[address+lane] = (value >> (8*lane)) & 255
        regs[0] = 0
        trace.append((pc, instruction, regs.copy()))
    else:
        raise RuntimeError('Spike did not reach the end marker')
    if not trace:
        raise RuntimeError('Spike produced no retirement trace')
    return done, trace, memory_bytes


def compare(work, done, expected, memory_bytes, real_ram):
    executable = work / ('ram.vvp' if real_ram else 'ideal.vvp')
    flags = ['-DREAL_RAM'] if real_ram else []
    run('iverilog', '-g2012', '-DSYNTHESIS', *flags, '-s', 'tb_rv32', '-o', str(executable),
        str(SOURCE / 'test/tb_rv32.sv'), str(SOURCE / 'cpu.sv'))
    output = run('vvp', str(executable), f'+stop={done:x}', cwd=work)
    actual = [line.split()[1:] for line in output.splitlines() if line.startswith('TRACE ')]
    if len(actual) != len(expected):
        raise AssertionError(f'Retired {len(actual)} instructions; Spike retired {len(expected)}')
    errors = []
    for index, (fields, (pc, instruction, regs)) in enumerate(zip(actual, expected)):
        next_pc = expected[index+1][0] if index+1 < len(expected) else done
        wanted = [pc, instruction, next_pc, *regs]
        if len(fields) != len(wanted):
            raise AssertionError('Incomplete RTL register snapshot')
        for field, (got, want) in enumerate(zip(fields, wanted)):
            if got.lower() != f'{want:08x}':
                name = ('PC', 'instruction', 'next PC')[field] if field < 3 else f'x{field-3}'
                errors.append(f'PC {pc:08x}, instruction {instruction:08x}: {name}={got}, Spike={want:08x}')
                break
    memory_lines = [line.split()[1:] for line in output.splitlines() if line.startswith('MEM ')]
    if len(memory_lines) != 65:
        raise AssertionError('Missing final RAM snapshot')
    for address, got in memory_lines:
        address = int(address, 16)
        want = sum(memory_bytes.get(address+lane, 0) << (8*lane) for lane in range(4))
        if got.lower() != f'{want:08x}':
            errors.append(f'RAM[{address:08x}]={got}, Spike={want:08x}')
    if errors:
        raise AssertionError(f'{len(errors)} trace/memory mismatches; first: {errors[0]}')
    return len(actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('all', 'arithmetic', 'control', 'stores', 'memory', 'bss'), default='all')
    args = parser.parse_args()
    failed = 0
    for name, generate in (('arithmetic', arithmetic), ('control', control), ('stores', stores), ('memory', memory), ('bss', bss)):
        if args.suite not in ('all', name):
            continue
        with tempfile.TemporaryDirectory(prefix=f'rv32-{name}-') as directory:
            work = Path(directory)
            done, expected, memory_bytes = oracle(work, generate(), has_bss=name == 'bss')
            for real_ram in (False, True):
                label = f'{name} / {"full SoC" if real_ram else "ideal memory"}'
                try:
                    count = compare(work, done, expected, memory_bytes, real_ram)
                    print(f'PASS: {label}: {count} retirements, all 32 registers and PCs match Spike')
                except (AssertionError, RuntimeError) as error:
                    failed += 1
                    print(f'FAIL: {label}: {error}')
    raise SystemExit(bool(failed))


if __name__ == '__main__':
    main()
