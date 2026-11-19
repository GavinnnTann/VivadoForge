`timescale 1ns / 1ps
// tick_gen - one-clock-wide enable pulse at TICK_HZ, derived from CLK_HZ.
//
// Use the tick as a clock ENABLE for slow logic (`if (tick) ...`). Do not use it as a clock:
// logic-generated clocks cause timing and clock-domain problems on FPGAs.
//
//   tick_gen #(.CLK_HZ(12_000_000), .TICK_HZ(1_000)) u_ms (.clk(clk), .rst(1'b0), .tick(ms_tick));
//
// The tick period is CLK_HZ / TICK_HZ clock cycles (integer division, so choose values that divide).
module tick_gen #(
    parameter integer CLK_HZ  = 100_000_000,
    parameter integer TICK_HZ = 1_000
) (
    input  wire clk,
    input  wire rst,    // synchronous, active-high
    output reg  tick
);
    localparam integer DIV = (CLK_HZ / TICK_HZ < 1) ? 1 : CLK_HZ / TICK_HZ;
    localparam integer W   = (DIV > 1) ? $clog2(DIV) : 1;

    reg [W-1:0] count = {W{1'b0}};
    initial tick = 1'b0;

    always @(posedge clk) begin
        if (rst) begin
            count <= {W{1'b0}};
            tick  <= 1'b0;
        end else if (count == DIV - 1) begin
            count <= {W{1'b0}};
            tick  <= 1'b1;
        end else begin
            count <= count + 1'b1;
            tick  <= 1'b0;
        end
    end
endmodule
