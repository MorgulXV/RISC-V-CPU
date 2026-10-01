`timescale 1ns/1ps
module tb_devices;
    reg clk = 0, rst = 1;
    integer failures = 0, checks = 0, i;
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

    reg ce = 0, re = 0;
    reg [3:0] we = 0;
    reg [31:0] addr = 0, din = 0, expected_word;
    reg [31:0] rom_addr = 0;
    wire [31:0] dout, rom_out;
    ram_module ram(.clk(clk), .rst(rst), .ce(ce), .re(re), .we(we),
        .addr(addr), .data_in(din), .data_out(dout));
    rom_module rom(.clk(clk), .rst(rst), .ce(ce), .oce(1'b1), .addr(rom_addr), .dout(rom_out));

    reg fb_we = 0, fb_re = 0;
    reg [31:0] fb_addr = 0, fb_din = 0;
    wire [3:0] a, b;
    framebuffer fb(.clk(clk), .rst(rst), .ce(1'b1), .re(fb_re), .we(fb_we),
        .waddr(fb_addr), .din(fb_din), .raddr_a(32'h20000), .raddr_b(32'h23ffc),
        .dout_a(a), .dout_b(b));

    wire [4:0] row;
    wire [5:0] col;
    wire oe, latch, pixel_clk, fb_read;
    LED_Controller led(.clk(clk), .rst(rst), .row_addr(row), .col_addr(col),
        .display_oe(oe), .latch(latch), .display_clk(pixel_clk), .fbuf_re(fb_read));
    integer pixels = 0, rows = 0;
    integer previous_row = -1;
    reg scan_done = 0;
    always @(posedge pixel_clk) if (!rst && !scan_done) begin
        check(col === pixels[5:0], "LED column order");
        check(oe === 1'b1, "LED blanked while shifting");
        pixels = pixels + 1;
    end
    always @(posedge latch) if (!rst && !scan_done) begin
        check(pixels == 64, "64 pixel clocks per row");
        check(row == ((previous_row + 1) % 32), "LED row order and wraparound");
        check(oe === 1'b1, "LED blanked while latching");
        previous_row = row;
        pixels = 0;
        rows = rows + 1;
        if (rows == 33) scan_done = 1;
    end
    always @(negedge oe) if (!rst && !scan_done)
        check(latch === 1'b0 && pixel_clk === 1'b0, "LED stable during display");

    task write_ram(input [31:0] address, value, input [3:0] mask);
        begin
            addr = address; din = value; we = mask; ce = 1; re = 0;
            @(negedge clk); we = 0;
        end
    endtask
    task read_ram(input [31:0] address, value);
        begin
            addr = address; re = 1; ce = 1;
            @(negedge clk);
            check(dout === value, $sformatf("One-cycle RAM read at %h expected %h, got %h", address, value, dout));
            re = 0;
            @(negedge clk);
            check(dout === value, "RAM result holds after a single-cycle read request");
        end
    endtask

    initial begin
        repeat (2) @(negedge clk);
        check(dout === 0 && a === 0 && b === 0, "memory output reset");
        check(row === 0 && col === 0 && oe === 1 && latch === 0, "LED reset");
        check(rom_out === 0, "ROM chip enable masks output");
        rst = 0;
        write_ram(32'h10000, 32'h12345678, 4'b1111);
        read_ram(32'h10000, 32'h12345678);
        check(rom_out === 32'h000300b7, "ROM initialization and read");
        rom_addr = 32'h3ffc;
        #1;
        check(rom_out === 32'h00000013, "ROM last implemented word");
        @(negedge clk);
        expected_word = 32'h12345678;
        for (i = 0; i < 4; i = i + 1) begin
            write_ram(32'h10000, 32'haabbccdd, 4'b0001 << i);
            expected_word = (expected_word & ~(32'hff << (8*i))) |
                            (32'haabbccdd & (32'hff << (8*i)));
            read_ram(32'h10000, expected_word);
        end
        read_ram(32'h10000, 32'haabbccdd);
        write_ram(32'h13ffc, 32'hdeadbeef, 4'b1111);
        read_ram(32'h13ffc, 32'hdeadbeef);
        ce = 0; we = 4'b1111; din = 0;
        @(negedge clk); we = 0;
        read_ram(32'h13ffc, 32'hdeadbeef);
        ce = 0; re = 0; addr = 32'h10000;
        repeat (2) @(negedge clk);
        check(dout === 32'hdeadbeef, "RAM holds output when read disabled");
        fb_we = 1; fb_addr = 32'h20000; fb_din = 32'h1234567a;
        @(negedge clk); fb_addr = 32'h23ffc; fb_din = 32'habcdef05;
        @(negedge clk); fb_we = 0; fb_re = 1;
        repeat (2) @(negedge clk);
        check(a === 4'ha && b === 4'h5, "framebuffer dual read ports and boundary addresses");
        fb_re = 0;
        repeat (2) @(negedge clk);
        check(a === 4'ha && b === 4'h5, "framebuffer read hold");
        wait(scan_done);
        @(negedge clk); rst = 1;
        repeat (2) @(negedge clk);
        check(dout === 0 && a === 0 && b === 0, "memory outputs reset after use");
        check(row === 0 && col === 0 && oe === 1, "LED reset after complete scan");
        if (failures) $fatal(1, "%0d/%0d device checks failed", failures, checks);
        $display("PASS: %0d device checks; 33 LED rows including wraparound", checks);
        $finish;
    end
    initial begin #2000000; $fatal(1, "Device test timeout"); end
endmodule
