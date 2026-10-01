#!/usr/bin/env python3
"""Run memory, LED and SPI integration tests with isolated initialization files."""
import argparse
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--suite', choices=('all', 'devices', 'system', 'bus'), default='all')
args = parser.parse_args()
failed = False
with tempfile.TemporaryDirectory(prefix='cpu-devices-') as directory:
    work = Path(directory)
    # LUI x1,0x30; LW x5,0(x1); JAL x0,-4: poll the gamepad register.
    words = [0x000300b7, 0x0000a283, 0xffdff06f] + [0x13] * 4093
    (work / 'rom.mi').write_text(''.join(f'{word:08x}\n' for word in words))
    (work / 'ram.mi').write_text('00000000\n' * 4096)
    (work / 'led.mi').write_text('0000\n' * 4096)
    for suite, name, bench in [('devices', 'tb_devices', 'tb_devices.sv'),
                               ('system', 'tb_cpu', 'tb.sv'), ('bus', 'tb_bus', 'tb_bus.sv')]:
        if args.suite not in ('all', suite):
            continue
        executable = work / f'{name}.vvp'
        subprocess.run(['iverilog', '-g2012', '-DSYNTHESIS', '-s', name, '-o', str(executable),
                        str(source / 'test' / bench), str(source / 'cpu.sv')], check=True)
        result = subprocess.run(['vvp', str(executable)], cwd=work, text=True,
                                capture_output=True, timeout=30)
        for line in result.stdout.splitlines():
            if line.startswith(('PASS:', 'FAIL:', 'FATAL:', 'ERROR:')):
                print(line)
        if result.returncode:
            failed = True
            print(f'FAIL: {name} exited with status {result.returncode}')
            print(result.stderr)
raise SystemExit(failed)
