`timescale 1ns/1ps
module tb_shifts;
    reg clk = 0;
    reg rst = 1;
    reg [31:0] instr;
    wire [31:0] pc;
    integer checks = 0;
    integer failures = 0;
    integer op, n;
    reg [31:0] amounts [0:5];
    reg [31:0] expected [0:2][0:5];

    always #5 clk = ~clk;
    fsm dut(.clk(clk), .rst(rst), .instr(instr), .pc(pc),
            .bus_rdata(32'b0), .controller_state(16'b0));

    // Execute consecutive shifts through decode, execute, and writeback.
    // Set source registers at FETCH without resetting the CPU between cases.
    task check_shift(input [2:0] funct3, input [6:0] funct7,
                     input [31:0] value, amount, want,
                     input immediate_shift);
        begin
            dut.regfile[1] = value;
            dut.regfile[2] = amount;
            if (immediate_shift)
                instr = {funct7, amount[4:0], 5'd1, funct3, 5'd3, 7'h13};
            else
                instr = {funct7, 5'd2, 5'd1, funct3, 5'd3, 7'h33};
            repeat (6) @(negedge clk);
            if ($test$plusargs("vectors"))
                $display("VECTOR %08h %08h %08h %08h", instr, value, amount, want);
            checks = checks + 1;
            if (dut.regfile[3] !== want || pc !== checks * 4) begin
                $display("FAIL #%0d funct3=%b funct7=%h value=%h rs2=%h got=%h expected=%h pc=%h",
                         checks, funct3, funct7, value, amount,
                         dut.regfile[3], want, pc);
                failures = failures + 1;
            end
        end
    endtask

    initial begin
        amounts[0] = 0; amounts[1] = 1; amounts[2] = 31;
        amounts[3] = 32'hffffffe0;
        amounts[4] = 32'h80000021;
        amounts[5] = 32'hffffffff;
        // Explicit results for 0x80000003 at shift amounts 0, 1, 31.
        expected[0][0] = 32'h80000003; expected[0][1] = 32'h00000006; expected[0][2] = 32'h80000000;
        expected[1][0] = 32'h80000003; expected[1][1] = 32'h40000001; expected[1][2] = 32'h00000001;
        expected[2][0] = 32'h80000003; expected[2][1] = 32'hc0000001; expected[2][2] = 32'hffffffff;
        for (op = 0; op < 3; op = op + 1)
            for (n = 3; n < 6; n = n + 1)
                expected[op][n] = expected[op][n-3];
        @(negedge clk);
        rst = 0;
        for (op = 0; op < 3; op = op + 1)
            for (n = 0; n < 6; n = n + 1)
                check_shift(op == 0 ? 3'b001 : 3'b101,
                            op == 2 ? 7'h20 : 7'h00,
                            32'h80000003, amounts[n], expected[op][n], 0);
        // Positive SRA must zero-fill; negative odd inputs must sign-extend.
        check_shift(3'b101, 7'h20, 32'h7fffffff, 0, 32'h7fffffff, 0);
        check_shift(3'b101, 7'h20, 32'h7fffffff, 1, 32'h3fffffff, 0);
        check_shift(3'b101, 7'h20, 32'h7fffffff, 31, 0, 0);
        check_shift(3'b101, 7'h20, 32'hffffffff, 1, 32'hffffffff, 0);
        // Guard the unchanged immediate shift instructions too.
        for (op = 0; op < 3; op = op + 1)
            for (n = 0; n < 3; n = n + 1)
                check_shift(op == 0 ? 3'b001 : 3'b101,
                            op == 2 ? 7'h20 : 7'h00,
                            32'h80000003, amounts[n], expected[op][n], 1);
        if (failures != 0) $fatal(1, "%0d/%0d shift checks failed", failures, checks);
        $display("PASS: %0d shift checks", checks);
        $finish;
    end

    initial begin
        #10000;
        $fatal(1, "Shift test timed out");
    end
endmodule
