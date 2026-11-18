`timescale 1ns / 1ps
// bin2bcd - sequential binary to BCD converter (shift-and-add-3), one bit per clock.
//
//   bin2bcd #(.BITS(14), .DIGITS(4)) u_bcd (
//       .clk(clk), .start(convert), .bin(ms), .bcd(digits), .busy(), .done(bcd_ready));
//
// Pulse start (while not busy); BITS clocks later done pulses and bcd holds the result,
// 4 bits per decimal digit with bcd[3:0] = ones. DIGITS must cover the largest input
// (e.g. 14 bits -> up to 16383 -> 5 digits; inputs above 9999 need DIGITS >= 5).
// Sequential on purpose: a combinational converter is a long logic path that easily fails
// timing at 100 MHz.
module bin2bcd #(
    parameter integer BITS   = 16,
    parameter integer DIGITS = 5
) (
    input  wire                clk,
    input  wire                start,
    input  wire [BITS-1:0]     bin,
    output reg  [4*DIGITS-1:0] bcd,
    output reg                 busy,
    output reg                 done
);
    localparam integer CW = $clog2(BITS + 1);
    localparam [CW-1:0] NBITS = BITS;

    reg [BITS-1:0]     sh  = {BITS{1'b0}};
    reg [4*DIGITS-1:0] acc = {4*DIGITS{1'b0}};
    reg [CW-1:0]       n   = {CW{1'b0}};

    // add 3 to every BCD digit that is 5 or more, then shift left by one
    reg [4*DIGITS-1:0] adj;
    integer j;
    always @* begin
        adj = acc;
        for (j = 0; j < DIGITS; j = j + 1)
            if (acc[4*j +: 4] > 4'd4) adj[4*j +: 4] = acc[4*j +: 4] + 4'd3;
    end
    wire [4*DIGITS+BITS-1:0] nxt = {adj, sh} << 1;

    initial begin
        bcd  = {4*DIGITS{1'b0}};
        busy = 1'b0;
        done = 1'b0;
    end

    always @(posedge clk) begin
        done <= 1'b0;
        if (!busy) begin
            if (start) begin
                sh   <= bin;
                acc  <= {4*DIGITS{1'b0}};
                n    <= NBITS;
                busy <= 1'b1;
            end
        end else begin
            acc <= nxt[BITS +: 4*DIGITS];
            sh  <= nxt[BITS-1:0];
            n   <= n - 1'b1;
            if (n == 1) begin
                bcd  <= nxt[BITS +: 4*DIGITS];
                busy <= 1'b0;
                done <= 1'b1;
            end
        end
    end
endmodule
