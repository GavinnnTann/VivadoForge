`timescale 1ns / 1ps
// uart_rx - 8N1 UART receiver with a built-in input synchroniser.
//
//   uart_rx #(.CLK_HZ(12_000_000), .BAUD(115_200)) u_rx (
//       .clk(clk), .rst(1'b0), .rx(uart_rx), .data(rx_byte), .valid(rx_valid), .frame_error());
//
// valid pulses for one clock when a byte has been received; data holds it until the next one.
// frame_error is a status bit for that byte, not a pulse: it updates together with valid (1 when
// the stop bit was 0: wrong baud rate or noise) and holds, like data, until the next byte ends or
// rst is asserted. Sample it when valid is high.
// Bits are sampled in the middle of each bit period.
module uart_rx #(
    parameter integer CLK_HZ = 100_000_000,
    parameter integer BAUD   = 115_200
) (
    input  wire       clk,
    input  wire       rst,     // synchronous, active-high
    input  wire       rx,      // asynchronous serial input, idles high
    output reg  [7:0] data,
    output reg        valid,
    output reg        frame_error
);
    localparam integer DIV  = (CLK_HZ + BAUD / 2) / BAUD;
    localparam integer HALF = (DIV / 2 < 1) ? 1 : DIV / 2;
    localparam integer W    = (DIV > 1) ? $clog2(DIV) : 1;

    localparam [1:0] S_IDLE = 2'd0, S_START = 2'd1, S_DATA = 2'd2, S_STOP = 2'd3;

    (* ASYNC_REG = "TRUE" *) reg [1:0] sync = 2'b11;
    wire rxs = sync[1];

    reg [1:0]   state   = S_IDLE;
    reg [W-1:0] cnt     = {W{1'b0}};
    reg [2:0]   bit_idx = 3'd0;
    reg [7:0]   shift   = 8'h00;

    initial begin
        data        = 8'h00;
        valid       = 1'b0;
        frame_error = 1'b0;
    end

    always @(posedge clk) begin
        sync  <= {sync[0], rx};
        valid <= 1'b0;
        if (rst) begin
            state       <= S_IDLE;
            cnt         <= {W{1'b0}};
            frame_error <= 1'b0;
        end else begin
            case (state)
                S_IDLE: begin
                    cnt <= {W{1'b0}};
                    if (!rxs) state <= S_START;          // falling edge = start bit
                end
                S_START: begin                            // wait to the middle of the start bit
                    if (cnt == HALF - 1) begin
                        cnt     <= {W{1'b0}};
                        bit_idx <= 3'd0;
                        state   <= rxs ? S_IDLE : S_DATA; // a glitch, not a start bit
                    end else begin
                        cnt <= cnt + 1'b1;
                    end
                end
                S_DATA: begin
                    if (cnt == DIV - 1) begin
                        cnt   <= {W{1'b0}};
                        shift <= {rxs, shift[7:1]};       // LSB first
                        if (bit_idx == 3'd7) state <= S_STOP;
                        else                 bit_idx <= bit_idx + 1'b1;
                    end else begin
                        cnt <= cnt + 1'b1;
                    end
                end
                default: begin                            // S_STOP
                    if (cnt == DIV - 1) begin
                        cnt         <= {W{1'b0}};
                        state       <= S_IDLE;
                        data        <= shift;
                        valid       <= 1'b1;
                        frame_error <= ~rxs;
                    end else begin
                        cnt <= cnt + 1'b1;
                    end
                end
            endcase
        end
    end
endmodule
