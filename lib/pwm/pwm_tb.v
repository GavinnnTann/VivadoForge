`timescale 1ns / 1ps
module pwm_tb;
    reg clk = 1'b0;
    reg [3:0] duty = 4'd0;
    wire out;
    integer d, k, highs;

    pwm #(.WIDTH(4)) dut (.clk(clk), .duty(duty), .out(out));   // 16-cycle period

    `include "forge_tb.vh"
    `TEST_TIMEOUT(1_000_000)

    always #5 clk = ~clk;

    initial begin
        for (d = 0; d < 16; d = d + 3) begin
            duty = d;
            repeat (32) @(posedge clk);          // let the new duty settle
            highs = 0;
            for (k = 0; k < 16; k = k + 1) begin
                @(posedge clk); #1;
                if (out) highs = highs + 1;
            end
            `CHECK_EQ(highs, d, "high cycles per period equal duty")
        end
        duty = 4'd15;
        repeat (32) @(posedge clk);
        highs = 0;
        for (k = 0; k < 16; k = k + 1) begin
            @(posedge clk); #1;
            if (out) highs = highs + 1;
        end
        `CHECK_EQ(highs, 15, "maximum duty is 15/16")
        `TEST_DONE
    end
endmodule
