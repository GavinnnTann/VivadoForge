`timescale 1ns / 1ps
// debounce - synchronise, debounce and edge-detect a mechanical button or switch.
//
//   debounce #(.CLK_HZ(12_000_000), .DEBOUNCE_MS(10), .ACTIVE_LOW(0)) u_btn (
//       .clk(clk), .btn_in(btn), .level(btn_down), .pressed(btn_press), .released());
//
// btn_in   raw pin, asynchronous to clk (a 2-flop synchroniser is built in)
// level    debounced state, 1 = pressed (ACTIVE_LOW inverts the pin for buttons that read 0 when pressed)
// pressed  one-cycle pulse when the button goes down
// released one-cycle pulse when the button comes up
//
// The input must hold a new value for DEBOUNCE_MS milliseconds before `level` follows it.
module debounce #(
    parameter integer CLK_HZ      = 100_000_000,
    parameter integer DEBOUNCE_MS = 10,
    parameter         ACTIVE_LOW  = 0
) (
    input  wire clk,
    input  wire btn_in,
    output reg  level,
    output reg  pressed,
    output reg  released
);
    localparam integer COUNT_RAW = (CLK_HZ / 1000) * DEBOUNCE_MS;
    localparam integer COUNT_MAX = (COUNT_RAW < 1) ? 1 : COUNT_RAW;
    localparam integer W         = (COUNT_MAX > 1) ? $clog2(COUNT_MAX) : 1;

    (* ASYNC_REG = "TRUE" *) reg [1:0] sync = ACTIVE_LOW ? 2'b11 : 2'b00;
    wire raw = ACTIVE_LOW ? ~sync[1] : sync[1];
    reg [W-1:0] count = {W{1'b0}};

    initial begin
        level    = 1'b0;
        pressed  = 1'b0;
        released = 1'b0;
    end

    always @(posedge clk) begin
        sync     <= {sync[0], btn_in};
        pressed  <= 1'b0;
        released <= 1'b0;
        if (raw == level) begin
            count <= {W{1'b0}};
        end else if (count == COUNT_MAX - 1) begin
            count    <= {W{1'b0}};
            level    <= raw;
            pressed  <= raw;
            released <= ~raw;
        end else begin
            count <= count + 1'b1;
        end
    end
endmodule
