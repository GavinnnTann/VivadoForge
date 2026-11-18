`timescale 1ns / 1ps
// fifo_sync - single-clock FIFO with first-word fall-through output.
//
//   fifo_sync #(.WIDTH(8), .DEPTH(16)) u_fifo (
//       .clk(clk), .rst(1'b0),
//       .wr_en(rx_valid), .wr_data(rx_byte), .full(),
//       .rd_en(tx_ready && !empty), .rd_data(next_byte), .empty(empty), .count());
//
// rd_data always shows the oldest entry while empty is low; assert rd_en for one cycle to pop it.
// Writes while full and reads while empty are ignored. DEPTH must be a power of two (>= 2).
// Small FIFOs map to LUT RAM; for deep buffers use block RAM (see lib/ram_sp).
module fifo_sync #(
    parameter integer WIDTH = 8,
    parameter integer DEPTH = 16
) (
    input  wire                   clk,
    input  wire                   rst,       // synchronous, active-high: empties the FIFO
    input  wire                   wr_en,
    input  wire [WIDTH-1:0]       wr_data,
    output wire                   full,
    input  wire                   rd_en,
    output wire [WIDTH-1:0]       rd_data,
    output wire                   empty,
    output wire [$clog2(DEPTH):0] count
);
    localparam integer AW = $clog2(DEPTH);

    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [AW:0] wp = {(AW+1){1'b0}};
    reg [AW:0] rp = {(AW+1){1'b0}};

    initial begin
        if ((1 << AW) != DEPTH || DEPTH < 2)
            $display("Error: fifo_sync DEPTH must be a power of two >= 2 (got %0d)", DEPTH);
    end

    assign empty   = (wp == rp);
    assign full    = (wp[AW] != rp[AW]) && (wp[AW-1:0] == rp[AW-1:0]);
    assign count   = wp - rp;
    assign rd_data = mem[rp[AW-1:0]];

    wire do_write = wr_en && !full;
    wire do_read  = rd_en && !empty;

    always @(posedge clk) begin
        if (rst) begin
            wp <= {(AW+1){1'b0}};
            rp <= {(AW+1){1'b0}};
        end else begin
            if (do_write) begin
                mem[wp[AW-1:0]] <= wr_data;
                wp <= wp + 1'b1;
            end
            if (do_read)
                rp <= rp + 1'b1;
        end
    end
endmodule
