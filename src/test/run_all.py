#!/usr/bin/env python3
"""Run every maintained RTL suite, reporting all failures before exiting."""
from pathlib import Path
import subprocess
import sys

source = Path(__file__).resolve().parent.parent
failed = 0
scripts = ('check_shifts_spike.py', 'check_cpu_spike.py', 'check_startup_spike.py', 'run_devices.py')
for script in scripts:
    print(f'=== {script} ===', flush=True)
    result = subprocess.run([sys.executable, '-B', str(source / 'test' / script)])
    failed += result.returncode != 0
print(f'{len(scripts)-failed}/{len(scripts)} test groups passed', flush=True)
raise SystemExit(bool(failed))
