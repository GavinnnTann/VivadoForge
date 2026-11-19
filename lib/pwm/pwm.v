`timescale 1ns / 1ps
// pwm - pulse-width modulator. out is high for `duty` out of every 2**WIDTH clock cycles.
//
//   pwm #(.WIDTH(8)) u_dim (.clk(clk), .duty(8'd32), .out(led_dim));   // about 12% brightness
//
// PWM frequency = CLK_HZ / 2**WIDTH (100 MHz / 256 = 390 kHz; 12 MHz / 256 = 47 kHz).
// duty = 0 is always off; the maximum duty (all ones) is on for 255/256 of the time.
module pwm #(
    parameter integer WIDTH = 8
) (
    input  wire             clk,
    input  wire [WIDTH-1:0] duty,
    output reg              out
);
    reg [WIDTH-1:0] count = {WIDTH{1'b0}};
    initial out = 1'b0;

    always @(posedge clk) begin
        count <= count + 1'b1;
        out   <= (count < duty);
    end
endmodule
