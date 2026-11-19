`timescale 1ns / 1ps
module lfsr_tb;
    reg clk = 1'b0;
    reg rst = 1'b1;
    wire [7:0]  v8;
    wire [15:0] v16;
    integer steps, zero8, zero16, period8, period16;
    reg [7:0]  start8;
    reg [15:0] start16;

    lfsr #(.WIDTH(8))  dut8  (.clk(clk), .rst(rst), .en(1'b1), .seed(8'h00),    .value(v8));
    lfsr #(.WIDTH(16)) dut16 (.clk(clk), .rst(rst), .en(1'b1), .seed(16'hACE1), .value(v16));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(5_000_000)

    always #5 clk = ~clk;

    initial begin
        @(posedge clk); #1;
        `CHECK_EQ(v8, 8'h01, "seed 0 is replaced by 1")
        `CHECK_EQ(v16, 16'hACE1, "seed loads on reset")
        rst = 1'b0;
        start8 = v8; start16 = v16;
        period8 = 0; period16 = 0; zero8 = 0; zero16 = 0;
        for (steps = 1; steps <= 65535; steps = steps + 1) begin
            @(posedge clk); #1;
            if (v8 == 0)  zero8 = zero8 + 1;
            if (v16 == 0) zero16 = zero16 + 1;
            if (period8 == 0 && v8 == start8)    period8 = steps;
            if (period16 == 0 && v16 == start16) period16 = steps;
        end
        `CHECK_EQ(period8, 255, "8-bit LFSR has a period of 255")
        `CHECK_EQ(period16, 65535, "16-bit LFSR has a period of 65535")
        `CHECK_EQ(zero8 + zero16, 0, "never reaches the all-zero state")
        `TEST_DONE
    end
endmodule
