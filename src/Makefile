.PHONY: all run gtkwave schematic schematic-minimal schematic-all clean-schematic

all: sim

tb.vvp: test/tb.sv cpu.sv
	iverilog -g2012 -o tb.vvp test/tb.sv cpu.sv

sim:
	python3 test/run_devices.py --suite system

# Generate flattened schematic
schematic:
	yosys gen_schematic.ys
	dot -Tpdf -Grankdir=LR -Gsplines=ortho cpu_flat_schematic.dot -o cpu_flat.pdf
	@echo "Generated: cpu_flat.pdf"

# Generate minimal optimized schematic
schematic-minimal:
	yosys gen_simple_schematic.ys
	dot -Tpdf -Grankdir=LR -Gsplines=ortho cpu_minimal_schematic.dot -o cpu_minimal.pdf
	@echo "Generated: cpu_minimal.pdf"

# Generate all schematics (flat + minimal + SVG)
schematic-all:
	./gen_all_schematics.sh

clean:
	rm -rf tb.vvp

clean-schematic:
	rm -f *.dot cpu_flat.pdf cpu_minimal.pdf cpu_flat.svg cpu_flat.v

show:
	gtkwave tb.vcd &

.PHONY: sim test test-shifts test-shifts-spike test-cpu-spike test-devices
test:
	python3 test/run_all.py

test-shifts:
	@set -eu; output=$$(mktemp); trap 'rm -f "$$output"' EXIT; \
	iverilog -g2012 -s tb_shifts -o "$$output" test/tb_shifts.sv cpu.sv; \
	vvp "$$output"

# Requires Spike and the riscv64-unknown-elf assembler and linker.
test-shifts-spike:
	python3 test/check_shifts_spike.py

test-cpu-spike:
	python3 test/check_cpu_spike.py

test-devices:
	python3 test/run_devices.py

.PHONY: lint
lint:
	verilator --lint-only --top-module topmodule cpu.sv

.PHONY: lint-all
lint-all:
	verilator --lint-only -Wall -Wno-fatal --top-module topmodule cpu.sv

.PHONY: test-startup-spike
test-startup-spike:
	python3 -B test/check_startup_spike.py
