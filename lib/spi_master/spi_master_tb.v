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

    // WIDTH = 1, the smallest legal size: one SCLK pulse per transfer. MISO is looped back.
    reg  start1 = 1'b0;
    reg  tx1 = 1'b0;
    wire rx1, done1, sclk1, mosi1, cs1_n, busy1;
    integer edges1;
    spi_master #(.WIDTH(1), .CLK_DIV(2)) dut1 (
        .clk(clk), .rst(1'b0), .start(start1), .tx_data(tx1), .rx_data(rx1), .busy(busy1),
        .done(done1), .sclk(sclk1), .mosi(mosi1), .miso(mosi1), .cs_n(cs1_n));
    always @(negedge cs1_n) edges1 = 0;
    always @(posedge sclk1) if (!cs1_n) edges1 = edges1 + 1;

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

    task transfer1(input bit_value);
        begin
            @(posedge clk);
            tx1 <= bit_value; start1 <= 1'b1;
            @(posedge clk);
            start1 <= 1'b0;
            @(posedge done1); #1;
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

        `CHECK(cs1_n == 1'b1 && sclk1 == 1'b0, "WIDTH=1: idle")
        transfer1(1'b1);
        `CHECK_EQ(rx1, 1'b1, "WIDTH=1: looped-back 1 received")
        `CHECK_EQ(edges1, 1, "WIDTH=1: one SCLK rising edge")
        transfer1(1'b0);
        `CHECK_EQ(rx1, 1'b0, "WIDTH=1: looped-back 0 received")
        `CHECK(cs1_n == 1'b1 && busy1 == 1'b0, "WIDTH=1: released after the transfer")
        `TEST_DONE
    end
endmodule
