`timescale 1ns / 1ps
// button_counter_tb - bouncy presses must each count exactly once. CLK_HZ is 10 kHz so the
// 10 ms debounce is only 100 clock cycles.
module button_counter_tb;
    localparam integer N_LED          = {{N_LED}};
    localparam         LED_ACTIVE_LOW = {{LED_ACTIVE_LOW}};
    localparam         BTN_ACTIVE_LOW = {{BTN_ACTIVE_LOW}};
    localparam integer MS             = 1_000_000;          // ns

    reg clk = 1'b0;
    reg finger = 1'b0;                                      // 1 = button held down
    wire btn = BTN_ACTIVE_LOW ? ~finger : finger;           // what the pin reads
    wire [N_LED-1:0] led;
    wire [N_LED-1:0] count = LED_ACTIVE_LOW ? ~led : led;

    button_counter #(.CLK_HZ(10_000), .N_LED(N_LED), .LED_ACTIVE_LOW(LED_ACTIVE_LOW),
                     .BTN_ACTIVE_LOW(BTN_ACTIVE_LOW)) dut (.clk(clk), .btn(btn), .led(led));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(2_000_000_000)

    always #50_000 clk = ~clk;                              // 10 kHz

    // One press: contacts bounce for 5 ms going down and coming up.
    task press;
        begin
            repeat (5) begin finger = ~finger; #(1 * MS); end   // ends held down
            #(30 * MS);
            repeat (5) begin finger = ~finger; #(1 * MS); end   // ends released
            #(30 * MS);
        end
    endtask

    initial begin
        #(1 * MS);
        `CHECK_EQ(count, 0, "counter starts at zero")
        press;
        `CHECK_EQ(count, 1, "one bouncy press counts once")
        press;
        press;
        `CHECK_EQ(count, 3, "three presses count three")
        `TEST_DONE
    end
endmodule
