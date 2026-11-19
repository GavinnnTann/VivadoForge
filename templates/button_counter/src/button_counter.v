`timescale 1ns / 1ps
// button_counter - each press of the button adds one to a counter shown on the LEDs.
//
// A mechanical button bounces for a few milliseconds and is asynchronous to the clock, so it is
// synchronised and debounced first (lib/debounce), and the counter uses the one-cycle `pressed`
// pulse. Counting raw button edges instead would add several counts per press.
module button_counter #(
    parameter integer CLK_HZ         = {{CLK_HZ}},
    parameter integer N_LED          = {{N_LED}},
    parameter         LED_ACTIVE_LOW = {{LED_ACTIVE_LOW}},
    parameter         BTN_ACTIVE_LOW = {{BTN_ACTIVE_LOW}}
) (
    input  wire             clk,
    input  wire             btn,
    output wire [N_LED-1:0] led
);
    wire pressed;

    debounce #(.CLK_HZ(CLK_HZ), .DEBOUNCE_MS(10), .ACTIVE_LOW(BTN_ACTIVE_LOW)) u_btn (
        .clk(clk), .btn_in(btn), .level(), .pressed(pressed), .released());

    reg [N_LED-1:0] count = {N_LED{1'b0}};
    always @(posedge clk)
        if (pressed) count <= count + 1'b1;

    assign led = LED_ACTIVE_LOW ? ~count : count;
endmodule
