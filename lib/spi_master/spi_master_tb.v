`timescale 1ns / 1ps
module spi_master_tb;
    reg clk = 1'b0;
    reg start = 1'b0;
    reg [7:0] tx_data = 8'h00;
    wire [7:0] rx_data;
    wire busy, done, sclk, mosi, cs_n;
    reg  miso = 1'b0;

    // SPI mode-0 slave model: shifts MOSI in on rising SCLK, drives MISO MSB first,
    // changing MISO on falling SCLK (first bit as soon as CS goes low).
    reg [7:0] slave_out, slave_in, slave_sh;
    integer edges, n;

    spi_master #(.WIDTH(8), .CLK_DIV(3)) dut (
        .clk(clk), .rst(1'b0), .start(start), .tx_data(tx_data), .rx_data(rx_data), .busy(busy),
        .done(done), .sclk(sclk), .mosi(mosi), .miso(miso), .cs_n(cs_n));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(1_000_000)

    always #5 clk = ~clk;

    always @(negedge cs_n) begin
        slave_sh = slave_out;
        miso     = slave_sh[7];
        edges    = 0;
    end
    always @(posedge sclk) if (!cs_n) begin
        slave_in = {slave_in[6:0], mosi};
        edges    = edges + 1;
    end
    always @(negedge sclk) if (!cs_n) begin
        slave_sh = {slave_sh[6:0], 1'b0};
        miso     = slave_sh[7];
    end

    task transfer(input [7:0] m2s, input [7:0] s2m);
        begin
            slave_out = s2m;
            @(posedge clk);
            tx_data <= m2s; start <= 1'b1;
            @(posedge clk);
            start <= 1'b0;
            @(posedge done); #1;
        end
    endtask

    reg [7:0] a [0:3];
    reg [7:0] b [0:3];
    initial begin
        a[0] = 8'hA5; b[0] = 8'h3C;
        a[1] = 8'h00; b[1] = 8'hFF;
        a[2] = 8'hFF; b[2] = 8'h00;
        a[3] = 8'h81; b[3] = 8'h7E;
        #20;
        `CHECK(cs_n == 1'b1 && sclk == 1'b0, "idle: CS high, SCLK low")
        for (n = 0; n < 4; n = n + 1) begin
            transfer(a[n], b[n]);
            `CHECK_EQ(slave_in, a[n], "slave received the master's byte")
            `CHECK_EQ(rx_data, b[n], "master received the slave's byte")
            `CHECK_EQ(edges, 8, "eight SCLK rising edges per transfer")
            `CHECK(cs_n == 1'b1, "CS released after the transfer")
            `CHECK(busy == 1'b0, "not busy after done")
        end
        `TEST_DONE
    end
endmodule
