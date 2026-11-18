`timescale 1ns / 1ps
// ram_sp - single-port synchronous RAM written so that Vivado infers block RAM.
//
//   ram_sp #(.WIDTH(8), .DEPTH(1024), .INIT_FILE("table.mem")) u_ram (
//       .clk(clk), .we(we), .addr(addr), .din(din), .dout(dout));
//
// Reads are synchronous: dout shows mem[addr] one clock after addr is presented ("read-first":
// during a write, dout returns the old contents). INIT_FILE is an optional $readmemh file of hex
// words, one per line; list it in [project].sources so Vivado finds it, and refer to it by
// file name only. Without INIT_FILE the RAM powers up as all zeros.
module ram_sp #(
    parameter integer WIDTH     = 8,
    parameter integer DEPTH     = 1024,
    parameter         INIT_FILE = ""
) (
    input  wire                     clk,
    input  wire                     we,
    input  wire [$clog2(DEPTH)-1:0] addr,
    input  wire [WIDTH-1:0]         din,
    output reg  [WIDTH-1:0]         dout
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    integer i;

    initial begin
        dout = {WIDTH{1'b0}};
        for (i = 0; i < DEPTH; i = i + 1)
            mem[i] = {WIDTH{1'b0}};
        if (INIT_FILE != "")
            $readmemh(INIT_FILE, mem);
    end

    always @(posedge clk) begin
        if (we)
            mem[addr] <= din;
        dout <= mem[addr];
    end
endmodule
