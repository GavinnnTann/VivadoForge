`timescale 1ns / 1ps
// seven_seg - multiplexed driver for an N-digit 7-segment display, with a built-in hex decoder.
//
//   seven_seg #(.CLK_HZ(100_000_000), .DIGITS(4), .SEG_ACTIVE_LOW(1), .DIGIT_ACTIVE_LOW(1)) u_disp (
//       .clk(clk), .value(16'h12AF), .blank(4'b0000), .dots(4'b0000),
//       .seg(seg), .dp(dp), .digit(an));
//
// value   4 bits per digit; value[3:0] is digit 0 (the rightmost)
// blank   1 turns a digit off (e.g. leading zeros)
// dots    1 lights that digit's decimal point
// seg     seg[0] = segment A ... seg[6] = segment G
// digit   digit enables, digit[0] = rightmost
//
// Polarity comes from the board: Basys 3 / Nexys A7 are active-low for both segments and digits;
// the SUTD DSL kit has active-high segments and active-low digit selects. `forge.py board`
// prints them. Each digit is lit for 1/DIGITS of the time, refreshed REFRESH_HZ times per second.
module seven_seg #(
    parameter integer CLK_HZ           = 100_000_000,
    parameter integer DIGITS           = 4,
    parameter integer REFRESH_HZ       = 1_000,
    parameter         SEG_ACTIVE_LOW   = 1,
    parameter         DIGIT_ACTIVE_LOW = 1
) (
    input  wire                clk,
    input  wire [4*DIGITS-1:0] value,
    input  wire [DIGITS-1:0]   blank,
    input  wire [DIGITS-1:0]   dots,
    output reg  [6:0]          seg,
    output reg                 dp,
    output reg  [DIGITS-1:0]   digit
);
    localparam integer SCAN_HZ  = REFRESH_HZ * DIGITS;
    localparam integer DIV      = (CLK_HZ / SCAN_HZ < 1) ? 1 : CLK_HZ / SCAN_HZ;
    localparam integer DW       = (DIV > 1) ? $clog2(DIV) : 1;
    localparam integer IW       = (DIGITS > 1) ? $clog2(DIGITS) : 1;

    reg [DW-1:0] div   = {DW{1'b0}};
    reg [IW-1:0] index = {IW{1'b0}};

    // Hex digit -> segments {G,F,E,D,C,B,A}, 1 = lit
    function [6:0] hex_to_seg(input [3:0] h);
        case (h)
            4'h0: hex_to_seg = 7'b0111111;
            4'h1: hex_to_seg = 7'b0000110;
            4'h2: hex_to_seg = 7'b1011011;
            4'h3: hex_to_seg = 7'b1001111;
            4'h4: hex_to_seg = 7'b1100110;
            4'h5: hex_to_seg = 7'b1101101;
            4'h6: hex_to_seg = 7'b1111101;
            4'h7: hex_to_seg = 7'b0000111;
            4'h8: hex_to_seg = 7'b1111111;
            4'h9: hex_to_seg = 7'b1101111;
            4'hA: hex_to_seg = 7'b1110111;
            4'hB: hex_to_seg = 7'b1111100;
            4'hC: hex_to_seg = 7'b0111001;
            4'hD: hex_to_seg = 7'b1011110;
            4'hE: hex_to_seg = 7'b1111001;
            default: hex_to_seg = 7'b1110001;   // F
        endcase
    endfunction

    wire [3:0]        nibble = value[4*index +: 4];
    wire              off    = blank[index];
    wire [6:0]        lit    = off ? 7'b0000000 : hex_to_seg(nibble);
    wire              dot    = ~off & dots[index];
    localparam [DIGITS-1:0] ONE = 1;
    wire [DIGITS-1:0] onehot = off ? {DIGITS{1'b0}} : (ONE << index);

    initial begin
        seg   = SEG_ACTIVE_LOW ? 7'h7F : 7'h00;
        dp    = SEG_ACTIVE_LOW ? 1'b1 : 1'b0;
        digit = DIGIT_ACTIVE_LOW ? {DIGITS{1'b1}} : {DIGITS{1'b0}};
    end

    always @(posedge clk) begin
        if (div == DIV - 1) begin
            div   <= {DW{1'b0}};
            index <= (index == DIGITS - 1) ? {IW{1'b0}} : index + 1'b1;
        end else begin
            div <= div + 1'b1;
        end
        seg   <= SEG_ACTIVE_LOW   ? ~lit    : lit;
        dp    <= SEG_ACTIVE_LOW   ? ~dot    : dot;
        digit <= DIGIT_ACTIVE_LOW ? ~onehot : onehot;
    end
endmodule
