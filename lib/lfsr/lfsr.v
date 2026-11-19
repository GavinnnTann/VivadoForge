`timescale 1ns / 1ps
// lfsr - maximal-length Galois LFSR pseudo-random generator (WIDTH = 8, 16, 24 or 32).
//
//   lfsr #(.WIDTH(16)) u_rng (.clk(clk), .rst(1'b0), .en(1'b1), .seed(16'hACE1), .value(rnd));
//
// value steps through all 2**WIDTH - 1 non-zero states before repeating. It is NOT
// cryptographically random. For "human-random" delays (games), let it run every clock and sample
// it when the user presses a button. A seed of 0 is replaced by 1 (0 would lock the register).
module lfsr #(
    parameter integer WIDTH = 16
) (
    input  wire             clk,
    input  wire             rst,     // synchronous, active-high: loads seed
    input  wire             en,      // advance one step per clock while high
    input  wire [WIDTH-1:0] seed,
    output reg  [WIDTH-1:0] value
);
    // Feedback masks for maximal-length sequences (Xilinx XAPP052 taps).
    localparam [WIDTH-1:0] TAPS =
        (WIDTH == 8)  ? 8'hB8 :
        (WIDTH == 16) ? 16'hB400 :
        (WIDTH == 24) ? 24'hE10000 :
        (WIDTH == 32) ? 32'h80200003 : {WIDTH{1'b0}};

    initial begin
        if (TAPS == 0) begin
            $display("Error: lfsr WIDTH must be 8, 16, 24 or 32 (got %0d)", WIDTH);
        end
        value = {{(WIDTH-1){1'b0}}, 1'b1};
    end

    always @(posedge clk) begin
        if (rst)
            value <= (seed == {WIDTH{1'b0}}) ? {{(WIDTH-1){1'b0}}, 1'b1} : seed;
        else if (en)
            value <= (value >> 1) ^ (value[0] ? TAPS : {WIDTH{1'b0}});
    end
endmodule
