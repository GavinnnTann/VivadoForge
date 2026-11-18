`timescale 1ns / 1ps
// reaction_timer_tb - plays two rounds: a 100 ms reaction and a false start.
// CLK_HZ is 10 kHz (1 ms = 10 clocks) and the random delay is shortened to 50-65 ms.
module reaction_timer_tb;
    localparam integer N_DIGIT          = {{N_DIGIT}};
    localparam         BTN_ACTIVE_LOW   = {{BTN_ACTIVE_LOW}};
    localparam         LED_ACTIVE_LOW   = {{LED_ACTIVE_LOW}};
    localparam         SEG_ACTIVE_LOW   = {{SEG_ACTIVE_LOW}};
    localparam         DIGIT_ACTIVE_LOW = {{DIGIT_ACTIVE_LOW}};
    localparam integer MS               = 1_000_000;   // ns

    reg clk = 1'b0;
    reg finger = 1'b0;                                  // 1 = button held down
    wire btn = BTN_ACTIVE_LOW ? ~finger : finger;
    wire led, dp;
    wire [6:0] seg;
    wire [N_DIGIT-1:0] an;
    wire go = LED_ACTIVE_LOW ? ~led : led;
    wire [N_DIGIT-1:0] digit_on = DIGIT_ACTIVE_LOW ? ~an : an;
    integer waited, two_lit, k;
    reg [N_DIGIT-1:0] seen;

    reaction_timer #(.CLK_HZ(10_000), .N_DIGIT(N_DIGIT), .BTN_ACTIVE_LOW(BTN_ACTIVE_LOW),
                     .LED_ACTIVE_LOW(LED_ACTIVE_LOW), .SEG_ACTIVE_LOW(SEG_ACTIVE_LOW),
                     .DIGIT_ACTIVE_LOW(DIGIT_ACTIVE_LOW), .MIN_DELAY_MS(50), .RAND_MASK_MS(15)) dut (
        .clk(clk), .btn(btn), .led(led), .seg(seg), .dp(dp), .an(an));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(2_000_000_000)

    always #50_000 clk = ~clk;                          // 10 kHz

    function integer bcd_ms(input [15:0] b);
        bcd_ms = b[15:12] * 1000 + b[11:8] * 100 + b[7:4] * 10 + b[3:0];
    endfunction

    initial begin
        #(5 * MS);
        `CHECK(go == 1'b0, "LED off while idle")
        `CHECK_EQ(dut.result, 16'h0000, "display starts at 0000")
        seen = 0; two_lit = 0;
        for (k = 0; k < 200; k = k + 1) begin           // scan: one digit at a time, all four used
            @(posedge clk); #1;
            seen = seen | digit_on;
            if ((digit_on & (digit_on - 1'b1)) != 0) two_lit = two_lit + 1;
        end
        `CHECK_EQ(two_lit, 0, "never two digits lit at once")
        `CHECK_EQ(seen[3:0], 4'b1111, "the four result digits are all scanned")

        // Round 1: start, wait for the LED, react 100 ms later
        finger = 1'b1; #(20 * MS); finger = 1'b0;
        waited = 0;
        while (!go && waited < 200) begin #(1 * MS); waited = waited + 1; end
        `CHECK(go == 1'b1, "LED lights after the random delay")
        `CHECK(waited >= 30 && waited <= 55, "delay within MIN_DELAY_MS .. MIN_DELAY_MS + RAND_MASK_MS")
        #(100 * MS);
        finger = 1'b1; #(20 * MS); finger = 1'b0;
        #(10 * MS);
        `CHECK(go == 1'b0, "LED off after the reaction")
        `CHECK(bcd_ms(dut.result) >= 100 && bcd_ms(dut.result) <= 110,
               "shows about 100 ms (+5 ms debounce)")

        // Round 2: false start
        finger = 1'b1; #(10 * MS); finger = 1'b0;
        #(10 * MS);
        `CHECK(go == 1'b0, "LED still off early in the wait")
        finger = 1'b1; #(10 * MS); finger = 1'b0;
        #(10 * MS);
        `CHECK_EQ(dut.result, 16'hEEEE, "pressing before the LED shows EEEE")
        #(100 * MS);
        `CHECK(go == 1'b0, "LED never lights after a false start")
        `TEST_DONE
    end
endmodule
