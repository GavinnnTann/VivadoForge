`timescale 1ns / 1ps
// uart_echo_tb - a model PC sends "Hi!\n" back to back; every byte must come back unchanged.
// The design runs at 1 MHz / 100 kBd here (10 clocks per bit) to keep the simulation short.
module uart_echo_tb;
    localparam integer N_LED          = {{N_LED}};
    localparam         LED_ACTIVE_LOW = {{LED_ACTIVE_LOW}};
    localparam integer BIT_NS         = 10_000;

    reg  clk = 1'b0;
    reg  rx  = 1'b1;
    wire tx;
    wire [N_LED-1:0] led;
    reg  [7:0] msg [0:3];
    reg  [7:0] got [0:3];
    reg  [7:0] b;
    integer i, j, k;

    uart_echo #(.CLK_HZ(1_000_000), .BAUD(100_000), .N_LED(N_LED), .LED_ACTIVE_LOW(LED_ACTIVE_LOW)) dut (
        .clk(clk), .uart_rx(rx), .uart_tx(tx), .led(led));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(20_000_000)

    always #500 clk = ~clk;                 // 1 MHz

    initial begin
        msg[0] = "H"; msg[1] = "i"; msg[2] = "!"; msg[3] = 8'h0A;
        #(BIT_NS * 2);
        fork
            begin : pc_sends                // 8N1 frames, back to back
                for (i = 0; i < 4; i = i + 1) begin
                    rx = 1'b0; #(BIT_NS);
                    for (k = 0; k < 8; k = k + 1) begin rx = msg[i][k]; #(BIT_NS); end
                    rx = 1'b1; #(BIT_NS);
                end
            end
            begin : pc_receives             // sample the middle of each bit
                for (j = 0; j < 4; j = j + 1) begin
                    @(negedge tx);
                    #(BIT_NS / 2);
                    `CHECK(tx == 1'b0, "start bit")
                    b = 8'h00;
                    repeat (8) begin #(BIT_NS); b = {tx, b[7:1]}; end
                    #(BIT_NS);
                    `CHECK(tx == 1'b1, "stop bit")
                    got[j] = b;
                end
            end
        join
        for (i = 0; i < 4; i = i + 1)
            `CHECK_EQ(got[i], msg[i], "echoed byte matches what was sent")
        `CHECK_EQ(LED_ACTIVE_LOW ? ~led : led, msg[3][N_LED-1:0], "LEDs show the last byte received")
        `TEST_DONE
    end
endmodule
