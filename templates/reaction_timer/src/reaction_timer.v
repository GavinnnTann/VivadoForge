`timescale 1ns / 1ps
// reaction_timer - how fast can you press the button after the LED lights?
//
//   1. Press the button to start. The display blanks while you wait.
//   2. After a random 1.0-3.0 s delay the LED lights.
//   3. Press again as fast as you can: the time in milliseconds appears on the display (max 9999).
//      Pressing before the LED lights is a false start and shows EEEE.
//
// The measured time includes the 5 ms button debounce. Time is counted directly in BCD (one
// decade counter per digit), so no binary-to-decimal conversion is needed.
module reaction_timer #(
    parameter integer CLK_HZ           = {{CLK_HZ}},
    parameter integer N_DIGIT          = {{N_DIGIT}},
    parameter         BTN_ACTIVE_LOW   = {{BTN_ACTIVE_LOW}},
    parameter         LED_ACTIVE_LOW   = {{LED_ACTIVE_LOW}},
    parameter         SEG_ACTIVE_LOW   = {{SEG_ACTIVE_LOW}},
    parameter         DIGIT_ACTIVE_LOW = {{DIGIT_ACTIVE_LOW}},
    parameter integer MIN_DELAY_MS     = 1000,   // shortest wait before the LED lights
    parameter integer RAND_MASK_MS     = 2047    // plus a random 0..RAND_MASK_MS ms (2^n - 1)
) (
    input  wire               clk,
    input  wire               btn,
    output wire               led,
    output wire [6:0]         seg,
    output wire               dp,
    output wire [N_DIGIT-1:0] an
);
    // ---- inputs: debounced button, 1 kHz tick, free-running random number ----------------------
    wire pressed;
    debounce #(.CLK_HZ(CLK_HZ), .DEBOUNCE_MS(5), .ACTIVE_LOW(BTN_ACTIVE_LOW)) u_btn (
        .clk(clk), .btn_in(btn), .level(), .pressed(pressed), .released());

    wire ms_tick;
    tick_gen #(.CLK_HZ(CLK_HZ), .TICK_HZ(1_000)) u_ms (.clk(clk), .rst(1'b0), .tick(ms_tick));

    wire [15:0] rnd;
    lfsr #(.WIDTH(16)) u_rng (.clk(clk), .rst(1'b0), .en(1'b1), .seed(16'hACE1), .value(rnd));

    // ---- state machine ----------------------------------------------------------------------
    localparam [1:0] S_IDLE = 2'd0, S_WAIT = 2'd1, S_GO = 2'd2;

    reg [1:0]  state     = S_IDLE;
    reg [15:0] wait_left = 16'd0;    // ms until the LED lights
    reg [15:0] timer     = 16'h0000; // running reaction time, 4 BCD digits
    reg [15:0] result    = 16'h0000; // what IDLE shows

    function [15:0] bcd_inc(input [15:0] v);   // +1 in BCD, saturating at 9999
        begin
            if (v == 16'h9999)          bcd_inc = v;
            else if (v[3:0]   != 4'd9)  bcd_inc = {v[15:4], v[3:0] + 4'd1};
            else if (v[7:4]   != 4'd9)  bcd_inc = {v[15:8], v[7:4] + 4'd1, 4'd0};
            else if (v[11:8]  != 4'd9)  bcd_inc = {v[15:12], v[11:8] + 4'd1, 8'd0};
            else                        bcd_inc = {v[15:12] + 4'd1, 12'd0};
        end
    endfunction

    always @(posedge clk) begin
        case (state)
            S_IDLE: if (pressed) begin
                state     <= S_WAIT;
                wait_left <= MIN_DELAY_MS + (rnd & RAND_MASK_MS);
            end
            S_WAIT: begin
                if (pressed) begin                    // false start
                    state  <= S_IDLE;
                    result <= 16'hEEEE;
                end else if (ms_tick) begin
                    if (wait_left == 16'd0) begin
                        state <= S_GO;
                        timer <= 16'h0000;
                    end else begin
                        wait_left <= wait_left - 1'b1;
                    end
                end
            end
            S_GO: begin
                if (pressed) begin
                    state  <= S_IDLE;
                    result <= timer;
                end else if (ms_tick) begin
                    timer <= bcd_inc(timer);
                end
            end
            default: state <= S_IDLE;
        endcase
    end

    // ---- outputs ----------------------------------------------------------------------------
    assign led = LED_ACTIVE_LOW ? ~(state == S_GO) : (state == S_GO);

    localparam [N_DIGIT-1:0] UPPER = {N_DIGIT{1'b1}} << 4;   // digits above the lowest four
    wire [15:0]          shown = (state == S_GO) ? timer : result;
    wire [4*N_DIGIT-1:0] value = shown;                        // zero-extended
    wire [N_DIGIT-1:0]   blank = (state == S_WAIT) ? {N_DIGIT{1'b1}} : UPPER;

    seven_seg #(.CLK_HZ(CLK_HZ), .DIGITS(N_DIGIT), .REFRESH_HZ(1_000),
                .SEG_ACTIVE_LOW(SEG_ACTIVE_LOW), .DIGIT_ACTIVE_LOW(DIGIT_ACTIVE_LOW)) u_disp (
        .clk(clk), .value(value), .blank(blank), .dots({N_DIGIT{1'b0}}),
        .seg(seg), .dp(dp), .digit(an));
endmodule
