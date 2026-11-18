`timescale 1ns / 1ps
// blink_tb - the LED counter must step every half second. CLK_HZ is shrunk to 20 so that one
// simulated "second" is only 20 clock cycles; the logic is identical at the real clock rate.
module blink_tb;
    localparam integer N_LED          = {{N_LED}};
    localparam         LED_ACTIVE_LOW = {{LED_ACTIVE_LOW}};

    reg clk = 1'b0;
    wire [N_LED-1:0] led;
    wire [N_LED-1:0] count = LED_ACTIVE_LOW ? ~led : led;   // undo the board's LED polarity
    integer k;

    blink #(.CLK_HZ(20), .N_LED(N_LED), .LED_ACTIVE_LOW(LED_ACTIVE_LOW)) dut (.clk(clk), .led(led));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(1_000_000)

    always #5 clk = ~clk;

    initial begin
        #1;
        `CHECK_EQ(count, 0, "LEDs start at zero")
        for (k = 1; k <= 5; k = k + 1) begin
            repeat (10) @(posedge clk);
            #1;
            `CHECK_EQ(count, k[N_LED-1:0], "counter steps every half second (10 cycles)")
        end
        `TEST_DONE
    end
endmodule
