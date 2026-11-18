`timescale 1ns / 1ps
module ram_sp_tb;
    reg clk = 1'b0;
    reg we = 1'b0;
    reg [3:0] addr = 4'd0;
    reg [7:0] din = 8'h00;
    wire [7:0] dout;
    integer i, errors;

    // ram_sp_tb.mem holds 16 hex words: 00 11 22 ... FF
    ram_sp #(.WIDTH(8), .DEPTH(16), .INIT_FILE("ram_sp_tb.mem")) dut (
        .clk(clk), .we(we), .addr(addr), .din(din), .dout(dout));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(1_000_000)

    always #5 clk = ~clk;

    initial begin
        errors = 0;
        // initial contents from the .mem file
        for (i = 0; i < 16; i = i + 1) begin
            @(posedge clk); addr <= i;
            @(posedge clk); #1;
            if (dout !== i * 8'h11) errors = errors + 1;
        end
        `CHECK_EQ(errors, 0, "contents loaded from INIT_FILE")

        // read-first: writing returns the old value on the same cycle
        @(posedge clk); addr <= 4'd5; din <= 8'hC5; we <= 1'b1;
        @(posedge clk); we <= 1'b0;
        #1 `CHECK_EQ(dout, 8'h55, "read-first: old data during the write")
        @(posedge clk); #1;
        `CHECK_EQ(dout, 8'hC5, "new data on the next read")

        // other addresses untouched
        @(posedge clk); addr <= 4'd6;
        @(posedge clk); #1;
        `CHECK_EQ(dout, 8'h66, "neighbouring word unchanged")
        `TEST_DONE
    end
endmodule
