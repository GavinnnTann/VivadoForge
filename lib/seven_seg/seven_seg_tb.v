`timescale 1ns / 1ps
module seven_seg_tb;
    reg clk = 1'b0;
    reg  [15:0] value = 16'h12AF;
    reg  [3:0]  blank = 4'b0000;
    reg  [3:0]  dots  = 4'b0010;
    wire [6:0]  seg_l, seg_h;
    wire        dp_l, dp_h;
    wire [3:0]  dig_l, dig_h;
    integer k, active, which, seen;

    // Basys 3 style (all active-low) and DSL-kit style (segments active-high, digits active-low).
    // CLK_HZ / (REFRESH_HZ * DIGITS) = 4 cycles per digit.
    seven_seg #(.CLK_HZ(16_000), .DIGITS(4), .REFRESH_HZ(1_000), .SEG_ACTIVE_LOW(1), .DIGIT_ACTIVE_LOW(1)) dut_l (
        .clk(clk), .value(value), .blank(blank), .dots(dots), .seg(seg_l), .dp(dp_l), .digit(dig_l));
    seven_seg #(.CLK_HZ(16_000), .DIGITS(4), .REFRESH_HZ(1_000), .SEG_ACTIVE_LOW(0), .DIGIT_ACTIVE_LOW(1)) dut_h (
        .clk(clk), .value(value), .blank(blank), .dots(dots), .seg(seg_h), .dp(dp_h), .digit(dig_h));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(10_000_000)

    always #5 clk = ~clk;

    function [6:0] expect_seg(input [3:0] h);
        case (h)
            4'h1: expect_seg = 7'b0000110;
            4'h2: expect_seg = 7'b1011011;
            4'hA: expect_seg = 7'b1110111;
            4'hF: expect_seg = 7'b1110001;
            default: expect_seg = 7'bxxxxxxx;
        endcase
    endfunction

    initial begin
        seen = 0;
        repeat (4) @(posedge clk);
        // Watch two full scans: whenever exactly one digit is enabled, check its segments.
        for (k = 0; k < 40; k = k + 1) begin
            @(posedge clk); #1;
            active = 0; which = -1;
            if (!dig_l[0]) begin active = active + 1; which = 0; end
            if (!dig_l[1]) begin active = active + 1; which = 1; end
            if (!dig_l[2]) begin active = active + 1; which = 2; end
            if (!dig_l[3]) begin active = active + 1; which = 3; end
            `CHECK(active <= 1, "at most one digit enabled at a time")
            if (active == 1) begin
                seen = seen | (1 << which);
                `CHECK_EQ(~seg_l, expect_seg(value[4*which +: 4]), "active-low segments match the hex digit")
                `CHECK_EQ(seg_h, expect_seg(value[4*which +: 4]), "active-high segments match the hex digit")
                `CHECK_EQ(dig_h, dig_l, "same digit timing for both instances")
                `CHECK_EQ(~dp_l, (which == 1), "decimal point only on digit 1 (active-low)")
                `CHECK_EQ(dp_h, (which == 1), "decimal point only on digit 1 (active-high)")
            end
        end
        `CHECK_EQ(seen, 4'b1111, "every digit was scanned")

        // Blank digit 3: it must never be enabled
        blank = 4'b1000;
        repeat (4) @(posedge clk);
        for (k = 0; k < 40; k = k + 1) begin
            @(posedge clk); #1;
            `CHECK(dig_l[3] == 1'b1, "blanked digit stays off")
        end
        `TEST_DONE
    end
endmodule
