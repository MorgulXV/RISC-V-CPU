`timescale 1ns/1ps
module tb_rv32;
    reg clk = 0, rst = 1;
    wire [31:0] pc, instr_addr, instr, bus_addr, bus_wdata, bus_rdata;
    wire imem_ce, dmem_ce, dmem_read;
    wire [3:0] dmem_we;
    reg [31:0] program_words [0:4095];
    reg [31:0] stop_pc, retired_pc, retired_instr;
    integer cycle, r;
    always #5 clk = ~clk;
`ifdef REAL_RAM
    // Use the complete SoC so ROM arbitration and bus wiring are exercised.
    topmodule uut(.clk(clk), .rst(rst), .miso(1'b1));
    assign pc = uut.pc;
    assign instr = uut.instr;
`define CORE uut.machine
`define RAM_WORD(index) uut.dmem.ram_mem[index]
`else
    // Ideal memory isolates ISA behavior from the physical memory handshake.
    wire rom_re;
    wire [31:0] ram_data;
    reg [31:0] memory [0:4095];
    integer lane;
    initial $readmemh("ram.mi", memory);
    assign instr = imem_ce ? program_words[(rom_re ? bus_addr : instr_addr) >> 2] : 0;
    assign ram_data = memory[bus_addr[13:2]];
    assign bus_rdata = rom_re ? instr : ram_data;
    fsm dut(.clk(clk), .rst(rst), .instr(instr), .instr_addr(instr_addr),
        .imem_ce(imem_ce), .rom_re(rom_re), .pc(pc), .bus_addr(bus_addr), .bus_wdata(bus_wdata),
        .bus_rdata(bus_rdata), .dmem_ce(dmem_ce), .dmem_read(dmem_read),
        .dmem_we(dmem_we), .controller_state(16'b0));
    always @(posedge clk)
        if (dmem_ce)
            for (lane = 0; lane < 4; lane = lane + 1)
                if (dmem_we[lane])
                    memory[bus_addr[13:2]][8*lane +: 8] <= bus_wdata[8*lane +: 8];
`define CORE dut
`define RAM_WORD(index) memory[index]
`endif

    initial begin
        if (!$value$plusargs("stop=%h", stop_pc)) $fatal(1, "Missing stop PC");
        $readmemh("rom.mi", program_words);
        repeat (2) @(negedge clk);
        rst = 0;
        // Spike starts at 0x1000 without a boot ROM. All instructions after
        // this initial PC setup are fetched and executed by the CPU itself.
        `CORE.pc = 32'h1000;
        for (cycle = 0; cycle < 100000; cycle = cycle + 1) begin
            @(posedge clk);
            if (`CORE.state == `CORE.WRITEBACK) begin
                retired_pc = pc;
                retired_instr = instr;
                #1;
                $write("TRACE %08h %08h %08h", retired_pc, retired_instr, pc);
                for (r = 0; r < 32; r = r + 1) $write(" %08h", `CORE.regfile[r]);
                $write("\n");
                if (pc === stop_pc) begin
                    for (r = 0; r < 64; r = r + 1) begin
                        $display("MEM %08h %08h", 32'h10000 + r*4, `RAM_WORD(r));
                    end
                    $display("MEM 00013ffc %08h", `RAM_WORD(4095));
                    $finish;
                end
            end
        end
        $fatal(1, "CPU did not reach the end of the program");
    end
endmodule
`undef CORE
`undef RAM_WORD
