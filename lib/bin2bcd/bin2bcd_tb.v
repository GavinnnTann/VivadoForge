`timescale 1ns / 1ps
module bin2bcd_tb;
    reg clk = 1'b0;
    reg start = 1'b0;
    reg [13:0] bin = 14'd0;
    wire [19:0] bcd;
    wire busy, done;
    integer v, errors, want;

    bin2bcd #(.BITS(14), .DIGITS(5)) dut (.clk(clk), .start(start), .bin(bin), .bcd(bcd), .busy(busy), .done(done));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(100_000_000)

    always #5 clk = ~clk;

    function integer to_bcd(input integer x);
        integer d, r, shift;
        begin
            r = 0; shift = 0;
            for (d = 0; d < 5; d = d + 1) begin
                r = r | ((x % 10) << shift);
                x = x / 10;
                shift = shift + 4;
            end
            to_bcd = r;
        end
    endfunction

    task convert(input integer x);
        begin
            @(posedge clk);
            bin <= x; start <= 1'b1;
            @(posedge clk);
            start <= 1'b0;
            @(posedge done); #1;
        end
    endtask

    initial begin
        errors = 0;
        // every value 0..2047, then a spread up to the 14-bit maximum
        for (v = 0; v < 2048; v = v + 1) begin
            convert(v);
            want = to_bcd(v);
            if (bcd !== want[19:0]) begin
                if (errors < 5) $display("CHECK FAILED: %0d -> %h, expected %h", v, bcd, want[19:0]);
                errors = errors + 1;
            end
        end
        for (v = 2048; v < 16384; v = v + 997) begin
            convert(v);
            want = to_bcd(v);
            if (bcd !== want[19:0]) errors = errors + 1;
        end
        convert(16383);
        `CHECK_EQ(bcd, 20'h16383, "maximum 14-bit value")
        `CHECK_EQ(errors, 0, "all conversions correct")
        `CHECK(busy == 1'b0, "idle after done")
        `TEST_DONE
    end
endmodule
