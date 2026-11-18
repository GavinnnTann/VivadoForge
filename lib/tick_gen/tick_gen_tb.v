`timescale 1ns / 1ps
module tick_gen_tb;
    reg clk = 1'b0;
    reg rst = 1'b0;
    wire tick;
    integer ticks, cycles, last_tick, gap_errors;

    // 1 kHz clock / 100 Hz tick -> one pulse every 10 cycles
    tick_gen #(.CLK_HZ(1_000), .TICK_HZ(100)) dut (.clk(clk), .rst(rst), .tick(tick));

    `include "forge_tb.vh"
    `TEST_TIMEOUT(1_000_000)

    always #5 clk = ~clk;

    initial begin
        ticks = 0; cycles = 0; last_tick = -1; gap_errors = 0;
        repeat (100) begin
            @(posedge clk); #1;
            cycles = cycles + 1;
            if (tick) begin
                if (last_tick >= 0 && cycles - last_tick != 10) gap_errors = gap_errors + 1;
                last_tick = cycles;
                ticks = ticks + 1;
            end
        end
        `CHECK_EQ(ticks, 10, "10 ticks in 100 cycles")
        `CHECK_EQ(gap_errors, 0, "ticks exactly 10 cycles apart")

        // tick is a single-cycle pulse
        @(posedge tick); @(posedge clk); #1;
        `CHECK(tick == 1'b0, "tick lasts one cycle")

        // reset holds the divider
        rst = 1'b1;
        repeat (30) begin
            @(posedge clk); #1;
            `CHECK(tick == 1'b0, "no tick while in reset")
        end
        rst = 1'b0;
        repeat (9) @(posedge clk);
        #1 `CHECK(tick == 1'b0, "no tick 9 cycles after reset")
        @(posedge clk); #1;
        `CHECK(tick == 1'b1, "tick 10 cycles after reset")
        `TEST_DONE
    end
endmodule
