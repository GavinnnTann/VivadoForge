// forge_tb.vh - self-checking testbench helpers (Verilog-2001, works in xsim and Icarus Verilog).
//
// `include this INSIDE your testbench module, after the signal declarations:
//
//   module counter_tb;
//       reg clk = 0;
//       ...
//       `include "forge_tb.vh"
//       `TEST_TIMEOUT(1_000_000)               // fail if the test is still running after 1 ms
//       always #5 clk = ~clk;
//       initial begin
//           ...
//           `CHECK(count == 4'd3, "count after three ticks")
//           `CHECK_EQ(count, 4'd3, "count after three ticks")   // also prints got/expected
//           `TEST_DONE                         // prints TEST PASSED / TEST FAILED and calls $finish
//       end
//   endmodule
//
// `python scripts/forge.py sim` passes a test only when the log contains "TEST PASSED" and no
// "TEST FAILED", "CHECK FAILED", "Error:" or "Fatal:" line.
//
// Macro arguments have UPPER_ names because some simulators also substitute them inside strings.

`ifndef FORGE_TB_VH
`define FORGE_TB_VH

`define CHECK(COND_, MSG_) \
    begin \
        forge_checks = forge_checks + 1; \
        if (!(COND_)) begin \
            forge_errors = forge_errors + 1; \
            $display("CHECK FAILED at %0t: %s", $time, MSG_); \
        end \
    end

`define CHECK_EQ(ACT_, EXP_, MSG_) \
    begin \
        forge_checks = forge_checks + 1; \
        if ((ACT_) !== (EXP_)) begin \
            forge_errors = forge_errors + 1; \
            $display("CHECK FAILED at %0t: %s (got 'h%0h, expected 'h%0h)", $time, MSG_, (ACT_), (EXP_)); \
        end \
    end

`define TEST_DONE \
    begin \
        if (forge_errors == 0 && forge_checks > 0) \
            $display("TEST PASSED (%0d checks)", forge_checks); \
        else if (forge_checks == 0) \
            $display("TEST FAILED (no checks ran)"); \
        else \
            $display("TEST FAILED (%0d of %0d checks failed)", forge_errors, forge_checks); \
        $finish; \
    end

`define TEST_TIMEOUT(LIMIT_) \
    initial begin \
        #(LIMIT_); \
        $display("TEST FAILED: timeout at %0t, the test did not finish", $time); \
        $finish; \
    end

`endif

integer forge_checks = 0;
integer forge_errors = 0;
