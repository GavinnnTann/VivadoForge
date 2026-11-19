`timescale 1ns / 1ps
module uart_tx_tb;
    // 1 MHz clock, 100 kBd -> 10 clocks per bit (1 bit = 10 us)
    localparam integer BIT_NS = 10_000;
    reg clk = 1'b0;
    reg rst = 1'b0;
    reg [7:0] data = 8'h00;
    reg valid = 1'b0;
    wire ready, tx;
    reg [7:0] got;
    reg stop_bit;
    integer n;

    uart_tx #(.CLK_HZ(1_000_000), .BAUD(100_000)) dut (
        .clk(clk), .rst(rst), .data(data), .valid(valid), .ready(ready), .tx(tx));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(20_000_000)

    always #500 clk = ~clk;

    // Independent receiver model: sample the middle of each bit.
    task receive(output [7:0] byte_out, output stop);
        integer b;
        begin
            @(negedge tx);                    // start bit begins
            #(BIT_NS / 2);
            `CHECK(tx == 1'b0, "start bit is low")
            for (b = 0; b < 8; b = b + 1) begin
                #(BIT_NS);
                byte_out[b] = tx;
            end
            #(BIT_NS);
            stop = tx;
        end
    endtask

    task send(input [7:0] b);
        begin
            @(posedge clk);
            while (!ready) @(posedge clk);
            data <= b; valid <= 1'b1;
            @(posedge clk);
            valid <= 1'b0;
        end
    endtask

    reg [7:0] patterns [0:3];
    initial begin
        patterns[0] = 8'h55; patterns[1] = 8'h00; patterns[2] = 8'hFF; patterns[3] = 8'hA7;
        #2_000;
        `CHECK(tx == 1'b1, "line idles high")
        `CHECK(ready == 1'b1, "ready while idle")
        for (n = 0; n < 4; n = n + 1) begin
            fork
                send(patterns[n]);
                receive(got, stop_bit);
            join
            `CHECK_EQ(got, patterns[n], "received byte matches")
            `CHECK(stop_bit == 1'b1, "stop bit is high")
        end
        // ready drops while sending and returns after the stop bit
        send(8'h3C);
        #(BIT_NS);
        `CHECK(ready == 1'b0, "busy while transmitting")
        #(BIT_NS * 10);
        `CHECK(ready == 1'b1, "ready again after 10 bit times")
        `CHECK(tx == 1'b1, "line back to idle")
        `TEST_DONE
    end
endmodule
