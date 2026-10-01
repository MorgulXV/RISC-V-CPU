`timescale 1ns/1ps
module tb_bus;
    reg clk = 0, rst = 1;
    integer failures = 0, checks = 0, i;
    topmodule uut(.clk(clk), .rst(rst), .miso(1'b1));
    always #5 clk = ~clk;
    task check(input condition, input string description);
        begin
            checks = checks + 1;
            if (condition !== 1'b1) begin
                failures = failures + 1;
                $display("FAIL: %s", description);
            end
        end
    endtask
    task store_word(input [31:0] address, value);
        begin
            rst = 1;
            repeat (2) @(negedge clk);
            rst = 0;
            uut.machine.regfile[1] = address;
            uut.machine.regfile[2] = value;
            uut.imem.rom_mem[0] = 32'h0020a023; // SW x2,0(x1)
            repeat (6) @(negedge clk);
        end
    endtask
    task load_rom(input [31:0] address, expected);
        begin
            rst = 1;
            repeat (2) @(negedge clk);
            rst = 0;
            uut.machine.regfile[1] = address;
            uut.imem.rom_mem[0] = 32'h0000a183; // LW x3,0(x1)
            repeat (6) @(negedge clk);
            check(uut.machine.regfile[3] === expected, "CPU ROM load at range boundary");
            check(uut.rom_re === 0, "ROM port returns to instruction fetch after load");
        end
    endtask
    initial begin
        repeat (2) @(negedge clk);
        store_word(32'h10000, 32'h12345678);
        check(uut.dmem.ram_mem[0] === 32'h12345678, "mapped DRAM word store");
        store_word(32'h20000, 32'habcdef05);
        check(uut.fb_inst.mem_a[0] === 32'habcdef05 && uut.fb_inst.mem_b[0] === 32'habcdef05,
              "CPU framebuffer store updates both read banks");
        check(uut.dmem.ram_mem[0] === 32'h12345678, "framebuffer store leaves DRAM intact");
        store_word(32'h00000, 32'hdeadbeef);
        check(uut.dmem.ram_mem[0] === 32'h12345678, "store to read-only ROM must not corrupt DRAM");
        store_word(32'h10000, 32'h12345678);
        store_word(32'h30000, 32'hdeadbeef);
        check(uut.dmem.ram_mem[0] === 32'h12345678, "store to SPI region must not corrupt DRAM");
        store_word(32'h10000, 32'h12345678);
        store_word(32'h40000, 32'hdeadbeef);
        check(uut.dmem.ram_mem[0] === 32'h12345678, "unmapped store must not corrupt DRAM");
        load_rom(32'h00000, 32'h0000a183);
        uut.imem.rom_mem[4095] = 32'h89abcdef;
        load_rom(32'h03ffc, 32'h89abcdef);
        if (failures) $fatal(1, "%0d/%0d bus isolation checks failed", failures, checks);
        $display("PASS: %0d bus isolation checks", checks);
        $finish;
    end
    initial begin #10000; $fatal(1, "Bus test timeout"); end
endmodule
