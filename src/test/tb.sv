`timescale 1ns/1ps
module tb_cpu;
    reg clk = 0, rst = 1;
    reg miso = 1;
    wire spi_clk, cs_n, mosi;
    integer failures = 0, checks = 0, transaction = 0, bit_number = 0;
    integer cycles, r;
    reg [7:0] response [0:4];
    reg [7:0] command [0:4];
    reg [15:0] expected_state;
    topmodule uut(.clk(clk), .rst(rst), .miso(miso),
        .spi_clk(spi_clk), .cs_n(cs_n), .mosi(mosi));
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

    // Drive LSB-first responses from external SPI edges, not DUT counters.
    always @(negedge cs_n) if (!rst) begin
        bit_number = 0;
        transaction = transaction + 1;
        response[3] = transaction == 1 ? 8'ha6 : 8'h59;
        response[4] = transaction == 1 ? 8'h3c : 8'hc3;
    end
    always @(negedge spi_clk) if (!rst && !cs_n && bit_number < 40)
        miso = response[bit_number / 8][bit_number % 8];
    always @(posedge spi_clk) if (!rst && !cs_n && bit_number < 40) begin
        check(mosi === command[bit_number / 8][bit_number % 8], "SPI MOSI command bit");
        bit_number = bit_number + 1;
    end

    initial begin
        response[0] = 8'hff; response[1] = 8'h41; response[2] = 8'h5a;
        command[0] = 8'h01; command[1] = 8'h42;
        command[2] = 0; command[3] = 0; command[4] = 0;
        repeat (2) @(negedge clk);
        check(uut.pc === 0 && uut.controller_state === 0 && cs_n === 1, "CPU and SPI reset");
        for (r = 0; r < 32; r = r + 1)
            check(uut.machine.regfile[r] === 0, "register reset");
        rst = 0;
        repeat (2) begin
            @(negedge cs_n);
            @(posedge cs_n);
            @(negedge clk);
            expected_state = ~{response[3], response[4]};
            check(bit_number == 40, "SPI transfers five complete bytes");
            check(uut.controller_state === expected_state, "SPI byte order and active-low inversion");
            cycles = 0;
            while (uut.machine.regfile[5] !== {16'b0, expected_state} && cycles < 30) begin
                @(negedge clk); cycles = cycles + 1;
            end
            check(uut.machine.regfile[5] === {16'b0, expected_state}, "CPU LW reads current SPI state");
            check({uut.button_left, uut.button_down, uut.button_right, uut.button_up} ===
                  {~expected_state[15], ~expected_state[11], ~expected_state[14], ~expected_state[10]},
                  "button output mapping");
        end
        // Reset during an active transaction and CPU execution.
        @(negedge cs_n);
        repeat (10) @(negedge clk);
        rst = 1;
        repeat (2) @(negedge clk);
        check(cs_n === 1 && uut.controller_state === 0 && uut.pc === 0, "mid-transaction reset");
        check(uut.dmem_we === 0 && uut.fbuf_we === 0, "reset prevents memory writes");
        for (r = 0; r < 32; r = r + 1)
            check(uut.machine.regfile[r] === 0, "register reset after execution");
        if (failures) $fatal(1, "%0d/%0d system checks failed", failures, checks);
        $display("PASS: %0d system checks; SPI command/response, CPU MMIO, buttons and reset", checks);
        $finish;
    end
    initial begin #2000000; $fatal(1, "System test timeout"); end
endmodule
