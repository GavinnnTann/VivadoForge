`timescale 1ns / 1ps
module uart_rx_tb;
    // 1 MHz clock, 100 kBd -> 10 clocks per bit
    localparam integer BIT_NS = 10_000;
    reg clk = 1'b0;
    reg rx = 1'b1;
    wire [7:0] data;
    wire valid, frame_error;
    reg [7:0] last;
    reg last_ferr, ferr_seen;
    integer count, n;

    uart_rx #(.CLK_HZ(1_000_000), .BAUD(100_000)) dut (
        .clk(clk), .rst(1'b0), .rx(rx), .data(data), .valid(valid), .frame_error(frame_error));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(50_000_000)

    always #500 clk = ~clk;

    always @(posedge clk) if (valid) begin
        count     = count + 1;
        last      = data;
        last_ferr = frame_error;
        if (frame_error) ferr_seen = 1'b1;
    end

    // Drive one 8N1 frame; bit_ns lets us test a slightly wrong baud rate.
    task send(input [7:0] b, input stop_level, input integer bit_ns);
        integer i;
        begin
            rx = 1'b0;
            #(bit_ns);
            for (i = 0; i < 8; i = i + 1) begin
                rx = b[i];
                #(bit_ns);
            end
            rx = stop_level;
            #(bit_ns);
            rx = 1'b1;
            #(bit_ns);
        end
    endtask

    reg [7:0] patterns [0:4];
    initial begin
        patterns[0] = 8'h55; patterns[1] = 8'h00; patterns[2] = 8'hFF; patterns[3] = 8'h81; patterns[4] = 8'h3C;
        count = 0;
        #(BIT_NS * 3);
        for (n = 0; n < 5; n = n + 1) begin
            send(patterns[n], 1'b1, BIT_NS);
            `CHECK_EQ(count, n + 1, "one valid pulse per byte")
            `CHECK_EQ(last, patterns[n], "received byte matches")
            `CHECK(last_ferr == 1'b0, "no framing error")
        end

        // Sender 3 % fast and 3 % slow must still be received
        send(8'hC3, 1'b1, BIT_NS * 97 / 100);
        `CHECK_EQ(last, 8'hC3, "tolerates a 3 % fast sender")
        send(8'h5A, 1'b1, BIT_NS * 103 / 100);
        `CHECK_EQ(last, 8'h5A, "tolerates a 3 % slow sender")

        // Stop bit low -> frame error flagged. The receiver may then decode one junk frame
        // while it resynchronises, as real UARTs do, so wait for the line to settle.
        ferr_seen = 1'b0;
        send(8'h12, 1'b0, BIT_NS);
        #(BIT_NS * 15);
        `CHECK(ferr_seen == 1'b1, "frame error when the stop bit is low")

        // A short low glitch is not a start bit
        n = count;
        rx = 1'b0; #(BIT_NS / 5); rx = 1'b1;
        #(BIT_NS * 15);
        `CHECK_EQ(count, n, "a short glitch does not produce a byte")
        `TEST_DONE
    end
endmodule
