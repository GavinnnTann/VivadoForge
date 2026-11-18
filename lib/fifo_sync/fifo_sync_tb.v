`timescale 1ns / 1ps
module fifo_sync_tb;
    reg clk = 1'b0;
    reg rst = 1'b0;
    reg wr_en = 1'b0, rd_en = 1'b0;
    reg [7:0] wr_data = 8'h00;
    wire [7:0] rd_data;
    wire full, empty;
    wire [3:0] count;
    integer i, errors;

    fifo_sync #(.WIDTH(8), .DEPTH(8)) dut (
        .clk(clk), .rst(rst), .wr_en(wr_en), .wr_data(wr_data), .full(full),
        .rd_en(rd_en), .rd_data(rd_data), .empty(empty), .count(count));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(1_000_000)

    always #5 clk = ~clk;

    task push(input [7:0] d);
        begin
            @(posedge clk); wr_data <= d; wr_en <= 1'b1;
            @(posedge clk); wr_en <= 1'b0;
        end
    endtask

    initial begin
        errors = 0;
        #12;
        `CHECK(empty && !full && count == 0, "starts empty")

        for (i = 0; i < 8; i = i + 1) push(8'h10 + i);
        #1;
        `CHECK(full && !empty, "full after DEPTH writes")
        `CHECK_EQ(count, 4'd8, "count = 8 when full")
        push(8'hEE);                                // ignored while full
        #1;
        `CHECK_EQ(count, 4'd8, "write while full is ignored")
        `CHECK_EQ(rd_data, 8'h10, "first word falls through")

        for (i = 0; i < 8; i = i + 1) begin
            if (rd_data !== 8'h10 + i) errors = errors + 1;
            @(posedge clk); rd_en <= 1'b1;
            @(posedge clk); rd_en <= 1'b0;
            #1;
        end
        `CHECK_EQ(errors, 0, "data comes out in order")
        `CHECK(empty && count == 0, "empty after reading everything")

        // simultaneous read and write keeps the count steady
        push(8'hA1); push(8'hA2);
        @(posedge clk); wr_data <= 8'hA3; wr_en <= 1'b1; rd_en <= 1'b1;
        @(posedge clk); wr_en <= 1'b0; rd_en <= 1'b0;
        #1;
        `CHECK_EQ(count, 4'd2, "read+write in one cycle keeps the count")
        `CHECK_EQ(rd_data, 8'hA2, "oldest word popped")

        rst = 1'b1; @(posedge clk); #1 rst = 1'b0;
        `CHECK(empty, "reset empties the FIFO")
        `TEST_DONE
    end
endmodule
