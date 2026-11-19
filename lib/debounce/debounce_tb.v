`timescale 1ns / 1ps
module debounce_tb;
    // 1 MHz clock, 1 ms debounce -> 1000 stable cycles needed
    localparam integer CLK_HZ = 1_000_000;
    reg clk = 1'b0;
    reg btn = 1'b0;          // active-high button
    reg btn_n = 1'b1;        // active-low button (reads 0 when pressed)
    wire level, pressed, released;
    wire level_n, pressed_n, released_n;
    integer presses, releases, presses_n, i;

    debounce #(.CLK_HZ(CLK_HZ), .DEBOUNCE_MS(1), .ACTIVE_LOW(0)) dut (
        .clk(clk), .btn_in(btn), .level(level), .pressed(pressed), .released(released));
    debounce #(.CLK_HZ(CLK_HZ), .DEBOUNCE_MS(1), .ACTIVE_LOW(1)) dut_n (
        .clk(clk), .btn_in(btn_n), .level(level_n), .pressed(pressed_n), .released(released_n));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(50_000_000)

    always #500 clk = ~clk;   // 1 MHz

    always @(posedge clk) begin
        if (pressed)   presses   = presses + 1;
        if (released)  releases  = releases + 1;
        if (pressed_n) presses_n = presses_n + 1;
    end

    // Bounce the contacts for a while, then settle at `final_level`
    task bounce(input final_level);
        begin
            for (i = 0; i < 20; i = i + 1) begin
                btn = ~btn; btn_n = ~btn;
                #(37_000 + i * 1_000);           // 37..56 us: always shorter than 1 ms
            end
            btn = final_level; btn_n = ~final_level;
        end
    endtask

    initial begin
        presses = 0; releases = 0; presses_n = 0;
        #10_000;
        `CHECK(level == 1'b0 && level_n == 1'b0, "idle level is 0 for both polarities")

        bounce(1'b1);
        #500_000;                                // 0.5 ms: not yet stable long enough
        `CHECK(level == 1'b0, "no press accepted before the debounce time")
        `CHECK_EQ(presses, 0, "no press pulse during bounce")
        #1_000_000;                              // now well past 1 ms stable
        `CHECK(level == 1'b1, "level follows a stable press")
        `CHECK_EQ(presses, 1, "exactly one press pulse")
        `CHECK(level_n == 1'b1, "active-low instance reports pressed")
        `CHECK_EQ(presses_n, 1, "active-low instance: exactly one press pulse")

        bounce(1'b0);
        #2_000_000;
        `CHECK(level == 1'b0, "level follows a stable release")
        `CHECK_EQ(releases, 1, "exactly one release pulse")
        `CHECK_EQ(presses, 1, "release bounce does not create extra presses")

        // A short glitch (less than the debounce time) is ignored
        btn = 1'b1; #200_000; btn = 1'b0;
        #2_000_000;
        `CHECK_EQ(presses, 1, "200 us glitch is ignored")
        `TEST_DONE
    end
endmodule
