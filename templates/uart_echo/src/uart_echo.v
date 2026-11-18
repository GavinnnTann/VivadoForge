`timescale 1ns / 1ps
// uart_echo - sends back every byte received on the USB-UART and shows the last byte on the LEDs.
//
// Try it: open a serial terminal (115200 baud, 8N1) on the board's USB COM port and type.
// A small FIFO sits between receiver and transmitter so back-to-back bytes are not lost when the
// PC's baud clock is slightly faster than ours.
module uart_echo #(
    parameter integer CLK_HZ         = {{CLK_HZ}},
    parameter integer BAUD           = 115_200,
    parameter integer N_LED          = {{N_LED}},
    parameter         LED_ACTIVE_LOW = {{LED_ACTIVE_LOW}}
) (
    input  wire             clk,
    input  wire             uart_rx,    // from the PC
    output wire             uart_tx,    // to the PC
    output wire [N_LED-1:0] led
);
    wire [7:0] rx_data;
    wire       rx_valid;

    uart_rx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_rx (
        .clk(clk), .rst(1'b0), .rx(uart_rx), .data(rx_data), .valid(rx_valid), .frame_error());

    wire [7:0] tx_data;
    wire       empty;
    wire       tx_ready;
    wire       send = tx_ready & ~empty;   // transmitter idle and a byte is waiting

    fifo_sync #(.WIDTH(8), .DEPTH(16)) u_fifo (
        .clk(clk), .rst(1'b0), .wr_en(rx_valid), .wr_data(rx_data), .full(),
        .rd_en(send), .rd_data(tx_data), .empty(empty), .count());

    uart_tx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_tx (
        .clk(clk), .rst(1'b0), .data(tx_data), .valid(send), .ready(tx_ready), .tx(uart_tx));

    // Low bits of the last byte received, as many as there are LEDs
    reg [N_LED-1:0] last = {N_LED{1'b0}};
    always @(posedge clk)
        if (rx_valid) last <= rx_data[N_LED-1:0];

    assign led = LED_ACTIVE_LOW ? ~last : last;
endmodule
