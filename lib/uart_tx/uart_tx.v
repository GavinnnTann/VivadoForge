`timescale 1ns / 1ps
// uart_tx - 8N1 UART transmitter (1 start bit, 8 data bits LSB first, 1 stop bit, no parity).
//
//   uart_tx #(.CLK_HZ(12_000_000), .BAUD(115_200)) u_tx (
//       .clk(clk), .rst(1'b0), .data(byte_to_send), .valid(send), .ready(tx_ready), .tx(uart_tx));
//
// A byte is accepted on a clock edge where valid && ready. ready is high while idle.
// tx idles high. Baud error is (CLK_HZ / BAUD) rounding: keep it under about 2 %
// (12 MHz / 115200 = 104.17 -> 104 cycles, 0.2 % error).
module uart_tx #(
    parameter integer CLK_HZ = 100_000_000,
    parameter integer BAUD   = 115_200
) (
    input  wire       clk,
    input  wire       rst,     // synchronous, active-high
    input  wire [7:0] data,
    input  wire       valid,
    output wire       ready,
    output wire       tx
);
    localparam integer DIV = (CLK_HZ + BAUD / 2) / BAUD;
    localparam integer W   = (DIV > 1) ? $clog2(DIV) : 1;

    reg [9:0]   shift     = 10'h3FF;   // {stop, data[7:0], start}; bit 0 drives the line
    reg [3:0]   bits_left = 4'd0;
    reg [W-1:0] baud_cnt  = {W{1'b0}};

    assign ready = (bits_left == 4'd0);
    assign tx    = shift[0];

    always @(posedge clk) begin
        if (rst) begin
            shift     <= 10'h3FF;
            bits_left <= 4'd0;
            baud_cnt  <= {W{1'b0}};
        end else if (bits_left == 4'd0) begin
            if (valid) begin
                shift     <= {1'b1, data, 1'b0};
                bits_left <= 4'd10;
                baud_cnt  <= {W{1'b0}};
            end
        end else if (baud_cnt == DIV - 1) begin
            baud_cnt  <= {W{1'b0}};
            shift     <= {1'b1, shift[9:1]};
            bits_left <= bits_left - 1'b1;
        end else begin
            baud_cnt <= baud_cnt + 1'b1;
        end
    end
endmodule
