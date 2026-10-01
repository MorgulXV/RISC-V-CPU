#!/usr/bin/env python3
"""Execute the real application startup/linker files on Spike and the full SoC."""
from pathlib import Path
import tempfile

from check_cpu_spike import SOURCE, compare, read_trace, run


def check_startup(work, app, data_size, bss_size):
    payload = bytes((0x81 + i*17) & 255 for i in range(data_size))
    fixture = work / 'fixture.s'
    # Read ROM using every supported load width, then inspect initialized RAM.
    # The string and table are deliberately accessed through addresses.
    fixture.write_text('\n'.join([
        '.section .text', '.globl main', 'main:',
        'la x20, rom_table',
        *[f'{op} x{3+i}, {offset}(x20)' for i, (op, offset) in enumerate(
            [('lb', 0), ('lbu', 0), ('lb', 3), ('lh', 0), ('lhu', 2), ('lw', 0)])],
        'la x21, message', 'lbu x10, 1(x21)',
        'la x22, __data_start',
        *[f'lbu x11, {i}(x22)' for i in range(data_size)],
        'la x23, __bss_start',
        *[f'lbu x12, {i}(x23)' for i in range(bss_size)],
        # Alternate ROM and RAM loads and return to instruction fetch each time.
        'lw x13, 0(x20)', 'lbu x14, 0(x22)', 'lw x15, 0(x20)',
        '.globl done', 'done:', 'li x5, 1', 'la x6, tohost', 'sw x5, 0(x6)',
        '1: j 1b', '.section .rodata', '.balign 4',
        'rom_table: .word 0x80ff7f01', 'message: .asciz "ROM reads work"',
        '.section .data', *([f'.byte {", ".join(map(str, payload))}'] if payload else []),
        '.section .bss', *([f'.zero {bss_size}'] if bss_size else []),
        # Spike reserves addresses below 0x1000 for its debug device. Relocate
        # the app ROM to 0x2000 and use 0x1000 to dirty RAM before app startup.
        '.section .spike_reset,"ax",@progbits',
        'li t0, 0x10000', 'li t1, 0x10100', 'li t2, 0xa5a5a5a5',
        '1: sw t2, 0(t0)', 'addi t0, t0, 4', 'bltu t0, t1, 1b', 'j _start',
        '.section .tohost,"aw",@progbits', '.balign 64',
        '.globl tohost', 'tohost: .dword 0', '.balign 64',
        '.globl fromhost', 'fromhost: .dword 0',
    ]) + '\n')
    linker = work / 'fixture.ld'
    linker.write_text((app / 'link.ld').read_text().replace(
        'ORIGIN = 0x00000000, LENGTH = 16K', 'ORIGIN = 0x00002000, LENGTH = 8K') + '''
MEMORY { RESET (rx) : ORIGIN = 0x1000, LENGTH = 4K
         HTIF (rw) : ORIGIN = 0x18000, LENGTH = 4K }
SECTIONS {
  .spike_reset 0x1000 : { *(.spike_reset) } > RESET
  .tohost : { *(.tohost) } > HTIF
}
''')
    objects = []
    for name, source in [('boot', app / 'boot.s'), ('fixture', fixture)]:
        obj = work / f'{name}.o'
        run('riscv64-unknown-elf-as', '-march=rv32i', '-mabi=ilp32', '-o', str(obj), str(source))
        objects.append(str(obj))
    elf = work / 'fixture.elf'
    run('riscv64-unknown-elf-ld', '-m', 'elf32lriscv', '--no-relax', '-T', str(linker),
        '-o', str(elf), *objects)
    symbols = {line.split()[2]: int(line.split()[0], 16)
               for line in run('riscv64-unknown-elf-nm', str(elf)).splitlines()
               if len(line.split()) == 3}
    assert symbols['__data_end'] - symbols['__data_start'] == data_size
    assert symbols['__bss_end'] - symbols['__bss_start'] == bss_size
    assert symbols['__data_start'] >= 0x10000 and symbols['__bss_end'] < 0x10100
    binary = work / 'rom.bin'
    run('riscv64-unknown-elf-objcopy', '-O', 'binary', '-j', '.text', '-j', '.data',
        '-j', '.spike_reset', str(elf), str(binary))
    image = b'\0' * 0x1000 + binary.read_bytes()
    assert len(image) <= 16384
    image = image.ljust(16384, b'\0')
    (work / 'rom.mi').write_text(''.join(
        f'{int.from_bytes(image[i:i+4], "little"):08x}\n' for i in range(0, 16384, 4)))
    (work / 'ram.mi').write_text('00000000\n' * 4096)
    (work / 'led.mi').write_text('0000\n' * 4096)
    log = work / 'spike.log'
    run('spike', '--isa=RV32I', '--disable-dtb', '-m0x1000:0x20000',
        '-l', '--log-commits', f'--log={log}', str(elf))
    done, expected, memory = read_trace(log, symbols['done'])
    # Check startup semantics independently, so agreement cannot mask a shared
    # startup bug. Verify untouched neighbors as well as initialized bytes.
    for address in range(0x10000, 0x10100):
        if symbols['__data_start'] <= address < symbols['__data_end']:
            want = payload[address - symbols['__data_start']]
        elif symbols['__bss_start'] <= address < symbols['__bss_end']:
            want = 0
        else:
            want = 0xa5
        assert memory.get(address) == want, f'Incorrect startup byte at {address:08x}'
    return compare(work, done, expected, memory, real_ram=True)


def main():
    checks = 0
    # Exercise every maintained startup/linker pair. Snake additionally covers
    # empty, one-byte, partial-word and 50-byte initialized-table sections.
    for app in sorted((SOURCE / 'apps').iterdir()):
        if not (app / 'boot.s').is_file() or not (app / 'link.ld').is_file():
            continue
        sizes = [(3, 5)]
        if app.name == 'snake':
            sizes += [(0, 0), (0, 1), (1, 0), (1, 1), (4, 4), (5, 3), (50, 7)]
        for data_size, bss_size in sizes:
            with tempfile.TemporaryDirectory(prefix='rv32-startup-') as directory:
                count = check_startup(Path(directory), app, data_size, bss_size)
            print(f'PASS: {app.name} .data={data_size}, .bss={bss_size}: '
                  f'{count} retirements match Spike; bytes and guards verified')
            checks += 1
    if checks != 15:
        raise RuntimeError(f'Expected 15 startup cases, ran {checks}')


if __name__ == '__main__':
    main()
