"""Unit tests for the VivadoForge tooling (no Vivado or simulator needed).

Run:  python -m unittest discover -s tests      (or: python scripts/forge.py selftest)
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from forgelib import build as B  # noqa: E402
from forgelib import hdl, reports, xdc  # noqa: E402
from forgelib import manifest as M  # noqa: E402
from forgelib.boards import board_ids, load_board, validate_board  # noqa: E402
from forgelib.build import tcl_quote  # noqa: E402
from forgelib.build_dir import clean_build_dir, ensure_build_dir  # noqa: E402
from forgelib.checks import run_checks  # noqa: E402
from forgelib.cli import main as forge_main  # noqa: E402
from forgelib.common import ForgeError  # noqa: E402
from forgelib.config import load_config  # noqa: E402
from forgelib.sim import judge  # noqa: E402
from forgelib.templates import new_project, pins_add  # noqa: E402


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forge_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestXdc(unittest.TestCase):
    MASTER = """
## Clock
#set_property -dict { PACKAGE_PIN W5   IOSTANDARD LVCMOS33 } [get_ports clk]
#create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports clk]
## LEDs
#set_property -dict { PACKAGE_PIN U16   IOSTANDARD LVCMOS33 } [get_ports {led[0]}]
#set_property -dict { PACKAGE_PIN E19   IOSTANDARD LVCMOS33 } [get_ports { led[1] }]; #IO_L3N Sch=led[1]
"""

    def test_master_commented_lines(self):
        x = xdc.parse_xdc(self.MASTER, include_commented=True)
        self.assertEqual(sorted(x.ports), ["clk", "led[0]", "led[1]"])
        self.assertEqual(x.ports["led[1]"].pin, "E19")
        self.assertEqual(x.ports["led[1]"].section, "LEDs")
        self.assertEqual(x.ports["led[1]"].comment, "IO_L3N Sch=led[1]")
        self.assertEqual(x.clocks[0].period, 10.0)

    def test_project_ignores_commented(self):
        x = xdc.parse_xdc(self.MASTER)
        self.assertEqual(x.ports, {})

    def test_split_properties_and_wildcards(self):
        text = ("set_property PACKAGE_PIN L17 [get_ports clk]\n"
                "set_property IOSTANDARD LVCMOS33 [get_ports {led[*]}]\n"
                "set_property PACKAGE_PIN A17 [get_ports {led[0]}]\n")
        x = xdc.parse_xdc(text)
        self.assertEqual(x.ports["clk"].pin, "L17")
        self.assertIsNone(x.ports["clk"].iostandard)
        self.assertEqual(x.prop_for("led[0]", "IOSTANDARD"), "LVCMOS33")
        self.assertIsNone(x.prop_for("clk", "IOSTANDARD"))

    def test_generated_lines_roundtrip(self):
        port = xdc.parse_xdc(self.MASTER, include_commented=True).ports["led[1]"]
        line = xdc.pin_line(port, "status[3]")
        back = xdc.parse_xdc(line + "\n" + xdc.clock_line(83.333, "clk"))
        self.assertEqual(back.ports["status[3]"].pin, "E19")
        self.assertAlmostEqual(back.clocks[0].period, 83.333)


class TestHdl(unittest.TestCase):
    def parse(self, text: str):
        return hdl.parse_verilog_modules(Path("t.v"), text)

    def test_ansi_with_parameters(self):
        m = self.parse("""
            module top #(parameter integer N = 4, parameter W = N*2) (
                input  wire clk,          // comment
                input  wire [N-1:0] sw, btn,
                output reg  [W-1:0] led = 0,
                output wire [$clog2(12_000_000)-1:0] count
            );
            endmodule""")[0]
        ports = {p.name: p for p in m.ports}
        self.assertEqual(list(ports), ["clk", "sw", "btn", "led", "count"])
        self.assertEqual(ports["sw"].width, 4)
        self.assertEqual(ports["btn"].width, 4)
        self.assertEqual(ports["led"].bits()[-1], "led[7]")
        self.assertEqual(ports["count"].width, 24)
        self.assertEqual(ports["clk"].bits(), ["clk"])

    def test_non_ansi(self):
        m = self.parse("""
            module old(a, b, y);
              parameter W = 3;
              input a;
              input [W:0] b;
              output reg y;
            endmodule""")[0]
        self.assertEqual([(p.name, p.direction, p.width) for p in m.ports],
                         [("a", "input", 1), ("b", "input", 4), ("y", "output", 1)])

    def test_sv_types_and_comments(self):
        m = self.parse("""/* module fake(input x); */
            module svtop (input logic clk, input my_t cfg, output logic signed [7:0] q);
            endmodule""")
        self.assertEqual(len(m), 1)
        self.assertEqual([p.name for p in m[0].ports], ["clk", "cfg", "q"])

    def test_unknown_width_is_reported_not_guessed(self):
        m = self.parse("module t(input wire [DEPTH-1:0] a); endmodule")[0]
        self.assertIsNone(m.ports[0].bits())

    def test_vhdl_entity(self):
        mods = hdl.parse_vhdl_entities(Path("t.vhd"), """
            entity top is
              generic ( N : integer := 4 );
              port ( clk : in std_logic;
                     led : out std_logic_vector(N-1 downto 0) );
            end top;""")
        self.assertEqual([(p.name, p.width) for p in mods[0].ports], [("clk", 1), ("led", 4)])


class TestReports(unittest.TestCase):
    TIMING = """
1. checking no_clock (0)
6. checking no_output_delay (2)
------------------------------------------------------------------------------------------------
| Design Timing Summary
| ---------------------
------------------------------------------------------------------------------------------------

    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints     WPWS(ns)     TPWS(ns)  TPWS Failing Endpoints  TPWS Total Endpoints
    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------     --------     --------  ----------------------  --------------------
     -0.412       -3.100                     12                  520        0.151        0.000                      0                  520       41.160        0.000                       0                   196


Timing constraints are not met.
"""

    def test_timing(self):
        t = reports.parse_timing_summary(self.TIMING)
        self.assertFalse(t["met"])
        self.assertEqual(t["wns"], -0.412)
        self.assertEqual(t["tns_failing"], 12)
        self.assertEqual(t["checks"]["no_output_delay"], 2)

    def test_unconstrained(self):
        t = reports.parse_timing_summary("There are no user specified timing constraints.")
        self.assertFalse(t["constrained"])
        self.assertIsNone(t["met"])

    def test_utilization(self):
        u = reports.parse_utilization("""
| Slice LUTs                 |    7 |     0 |          0 |     20800 |  0.03 |
| Slice Registers            |   25 |     0 |          0 |     41600 |  0.06 |
| Block RAM Tile    |    0 |     0 |          0 |        50 |  0.00 |
| Bonded IOB                  |    3 |     3 |          0 |       106 |  2.83 |
""")
        self.assertEqual(u["lut"], {"used": 7, "available": 20800, "percent": 0.03})
        self.assertEqual(u["io"]["used"], 3)
        tiny = reports.parse_utilization("| Slice LUTs                 |    2 |     0 |          0 |     20800 | <0.01 |\n")
        self.assertEqual(tiny["lut"]["percent"], 0.01)

    def test_messages(self):
        msgs = reports.parse_messages(
            "WARNING: [Synth 8-6014] Unused sequential element x_reg was removed.  [C:/p q/top.v:47]\n"
            "CRITICAL WARNING: [Common 17-55] 'set_property' expects at least one object.\n"
            "WARNING: [Synth 8-6014] Unused sequential element x_reg was removed.  [C:/p q/top.v:47]\n")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["file"], "C:/p q/top.v")
        self.assertEqual(msgs[0]["line"], 47)
        self.assertEqual(msgs[1]["severity"], "critical_warning")


class TestJudge(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(judge("TEST PASSED (3 checks)", 0, False)[0], "passed")
        self.assertEqual(judge("CHECK FAILED at 5: x\nTEST FAILED (1 of 2 checks failed)", 0, False)[0], "failed")
        self.assertEqual(judge("Fatal: boom\nTEST PASSED", 0, False)[0], "failed")       # xsim exits 0 on $fatal
        self.assertEqual(judge("ERROR: t.v:4: bad\nTEST PASSED", 0, False)[0], "failed")  # Icarus $error
        self.assertEqual(judge("hello", 0, False)[0], "no_verdict")
        self.assertEqual(judge("TEST PASSED", 0, True)[0], "timeout")
        self.assertEqual(judge("Error count = 0\nTEST PASSED", 0, False)[0], "passed")  # not an error line


class TestBoards(unittest.TestCase):
    def test_every_board_is_consistent(self):
        ids = board_ids()
        self.assertIn("cmod_a7", ids)
        for b in ids:
            board = load_board(b)
            self.assertEqual(validate_board(board), [], b)
            self.assertTrue(board.clock_pin, b)

    def test_known_pins(self):
        self.assertEqual(load_board("cmod_a7").clock_pin, "L17")
        nexys = load_board("nexys_a7_100t")
        self.assertEqual(nexys.master.ports["SW[8]"].iostandard, "LVCMOS18")
        self.assertEqual(nexys.master.ports["SW[0]"].iostandard, "LVCMOS33")
        self.assertTrue(load_board("basys3").roles["seg"].active_low)
        self.assertFalse(load_board("sutd_dsl_kit").roles["seg"].active_low)


class TestTcl(unittest.TestCase):
    def test_quote(self):
        self.assertEqual(tcl_quote("C:/a b/c.v"), "{C:/a b/c.v}")
        self.assertEqual(tcl_quote(""), "{}")
        self.assertEqual(tcl_quote("a{b"), '"a\\{b"')


class TestBuildDir(TempDir):
    def test_refuses_foreign_folder(self):
        foreign = self.tmp / "mine"
        foreign.mkdir()
        (foreign / "thesis.docx").write_text("precious")
        with self.assertRaises(ForgeError):
            ensure_build_dir(foreign)
        with self.assertRaises(ForgeError):
            clean_build_dir(foreign)
        self.assertTrue((foreign / "thesis.docx").exists())

    def test_creates_and_cleans_own_folder(self):
        b = ensure_build_dir(self.tmp / "build")
        (b / "sub" / "deep").mkdir(parents=True)
        (b / "sub" / "deep" / "x.txt").write_text("generated")
        self.assertTrue(clean_build_dir(b))
        self.assertFalse(b.exists())

    def test_leftover_empty_folders_are_adopted(self):
        # what an interrupted delete can leave behind: folders, no files, no marker
        b = self.tmp / "build"
        (b / "sim" / "tb").mkdir(parents=True)
        self.assertEqual(ensure_build_dir(b), b)
        self.assertTrue((b / ".forge-build").is_file())
        (b / ".forge-build").unlink()
        self.assertTrue(clean_build_dir(b))
        self.assertFalse(b.exists())


class TestProjects(TempDir):
    def test_new_project_checks_clean(self):
        for template, board in (("blink", "cmod_a7"), ("reaction_timer", "basys3"), ("uart_echo", "nexys_a7_100t")):
            dest = self.tmp / f"{template}-{board}"
            new_project(template, board, dest, None, force=False)
            cfg = load_config(dest)
            findings, _ = run_checks(cfg, None, None)
            errors = [f.format() for f in findings if f.severity == "error"]
            self.assertEqual(errors, [], f"{template} on {board}")
            text = (dest / "src" / f"{template}.v").read_text()
            self.assertNotIn("{{", text)

    def test_incompatible_template(self):
        with self.assertRaises(ForgeError):
            new_project("reaction_timer", "cmod_a7", self.tmp / "x", None, force=False)

    def test_refuses_to_overwrite(self):
        new_project("blink", "cmod_a7", self.tmp, None, force=False)
        with self.assertRaises(ForgeError):
            new_project("blink", "basys3", self.tmp, None, force=False)
        new_project("blink", "basys3", self.tmp, None, force=True)
        self.assertIn('board = "basys3"', (self.tmp / "forge.toml").read_text())

    def test_check_catches_pin_mistakes(self):
        new_project("blink", "basys3", self.tmp, None, force=False)
        x = self.tmp / "constraints" / "blink.xdc"
        text = x.read_text().replace("PACKAGE_PIN U16 ", "PACKAGE_PIN Q99 ").replace("-period 10.000", "-period 20.000")
        text = "\n".join(line for line in text.splitlines() if "led[1]" not in line) + "\n"
        x.write_text(text)
        findings, _ = run_checks(load_config(self.tmp), None, None)
        messages = " | ".join(f.message for f in findings if f.severity == "error")
        self.assertIn("Q99", messages)
        self.assertIn("led[1]", messages)
        self.assertIn("20.0 ns", messages)

    def test_pins_add_renames_and_refuses_reuse(self):
        new_project("blink", "cmod_a7", self.tmp, None, force=False)
        cfg = load_config(self.tmp)
        board = load_board("cmod_a7")
        res = pins_add(cfg, board, ["btn[0]=start", "pio1=uart_tx"], None)
        self.assertEqual([a["design"] for a in res["added"]], ["start", "uart_tx"])
        self.assertEqual(res["added"][0]["pin"], "A18")
        with self.assertRaises(ForgeError):
            pins_add(cfg, board, ["btn[0]=again"], None)
        res = pins_add(cfg, board, ["btn[0]=start"], None)
        self.assertEqual(res["added"], [])

    def test_config_errors_are_friendly(self):
        (self.tmp / "forge.toml").write_text('[project]\nname = "x"\ntop = "t"\nboard = "cmod_a7"\nsources = "src/*.v"\n')
        with self.assertRaises(ForgeError) as ctx:
            load_config(self.tmp)
        self.assertIn("sources", str(ctx.exception))

    def test_waivers_need_an_id_and_a_reason(self):
        base = '[project]\nname = "x"\ntop = "t"\nboard = "cmod_a7"\n[build.waive]\n'
        (self.tmp / "forge.toml").write_text(base + '"Common  17-55" = "reviewed: unused debug port"\n')
        self.assertEqual(load_config(self.tmp).waivers, {"Common 17-55": "reviewed: unused debug port"})
        for bad in ('"Common 17-55" = ""\n', '"not an id!" = "why"\n'):
            (self.tmp / "forge.toml").write_text(base + bad)
            with self.assertRaises(ForgeError):
                load_config(self.tmp)

    def test_direction_and_polarity_follow_the_board(self):
        (self.tmp / "forge.toml").write_text('[project]\nname = "t"\ntop = "top"\nboard = "basys3"\n')
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "top.v").write_text(
            "`timescale 1ns / 1ps\n"
            "module top(input wire clk, output wire btnC, input wire [1:0] led, input wire go_n, inout wire sw0);\n"
            "  assign btnC = 1'b0;\nendmodule\n")
        pins_add(load_config(self.tmp), load_board("basys3"), ["clk", "btnC", "led[0]", "led[1]", "btnU=go_n", "sw[0]=sw0"], None)
        findings, _ = run_checks(load_config(self.tmp), None, None)
        got = {(f.code, f.severity, f.message.split("'")[1]) for f in findings if f.code in ("direction", "polarity")}
        self.assertEqual(got, {("direction", "error", "btnC"),       # driving a button pin
                               ("direction", "error", "led[0]"),     # reading an LED pin
                               ("direction", "error", "led[1]"),
                               ("direction", "warning", "sw0"),      # inout on a switch
                               ("polarity", "warning", "go_n")})     # _n name on an active-high button


def _forge_json(*argv: str) -> tuple[int, dict]:
    """Run the CLI in --json mode and return (exit code, parsed stdout)."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        rc = forge_main(["--json", *argv])
    return rc, json.loads(stdout.getvalue())


class TestManifest(TempDir):
    def setUp(self):
        super().setUp()
        new_project("blink", "cmod_a7", self.tmp, None, force=False)
        self.cfg = load_config(self.tmp)
        self.board = load_board("cmod_a7")
        self.src = self.tmp / "src" / "blink.v"

    def fake_build(self, content: bytes = b"bitstream") -> None:
        """What a successful forge build leaves behind, without running Vivado."""
        self.cfg.bitstream.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.bitstream.write_bytes(content)
        M.write(self.cfg, M.collect_inputs(self.cfg, self.board), self.cfg.bitstream,
                {"finished": "now", "status": "passed", "vivado": "test"})

    def test_compare_lists_what_changed(self):
        before = M.collect_inputs(self.cfg, self.board)
        self.assertEqual(M.compare(before, M.collect_inputs(self.cfg, self.board)), [])
        self.src.write_text(self.src.read_text() + "\n// edited\n")
        (self.tmp / "src" / "extra.v").write_text("`timescale 1ns / 1ps\nmodule extra; endmodule\n")
        self.cfg.generics = {"N_LED": "1"}
        changes = M.compare(before, M.collect_inputs(self.cfg, self.board))
        self.assertTrue(any(c.startswith("changed") and c.endswith("blink.v") for c in changes), changes)
        self.assertTrue(any(c.startswith("added") and c.endswith("extra.v") for c in changes), changes)
        self.assertTrue(any(c.startswith("setting generics") for c in changes), changes)

    def test_program_refuses_a_stale_bitstream(self):
        rc, res = _forge_json("-p", str(self.tmp), "program")
        self.assertEqual((rc, res["code"]), (1, "no_build"))

        self.fake_build()
        rc, res = _forge_json("-p", str(self.tmp), "program")    # fresh: stops at Vivado or approval, never programs
        self.assertEqual(rc, 1)
        self.assertIn(res["code"], ("approval_required", "vivado_not_found"))

        self.src.write_text(self.src.read_text() + "\n// edited after the build\n")
        rc, res = _forge_json("-p", str(self.tmp), "program")
        self.assertEqual((rc, res["code"]), (1, "stale_bitstream"))
        self.assertTrue(any(c.endswith("blink.v") for c in res["changes"]), res)
        rc, res = _forge_json("-p", str(self.tmp), "info")
        self.assertIs(res["last_build"], None)                    # no summary.json in a fake build

        self.fake_build()
        self.cfg.bitstream.write_bytes(b"regenerated in the GUI")
        rc, res = _forge_json("-p", str(self.tmp), "flash")
        self.assertEqual((rc, res["code"]), (1, "stale_bitstream"))


class TestVerdicts(unittest.TestCase):
    @staticmethod
    def summary(**changes) -> dict:
        s = {"bitstream": "x.bit", "stage": "done", "reports": {"timing": "t.rpt", "drc": "d.rpt"},
             "timing": {"met": True, "constrained": True, "wns": 1.0, "tns_failing": 0, "checks": {"no_clock": 0}},
             "utilization": {"ff": {"used": 10}}, "drc": [], "critical_warnings": []}
        s.update(changes)
        return s

    def verdict(self, waivers=None, **changes) -> dict:
        return B.evaluate(self.summary(**changes), waivers)

    def test_passed_needs_every_check(self):
        s = self.verdict()
        self.assertEqual(s["status"], "passed")
        self.assertEqual(s["verification"], {"bitstream": "generated", "timing": "met", "drc": "passed",
                                             "critical_warnings": "none", "hardware": "not_tested"})
        self.assertTrue(B.build_ok(s))

    def test_timing(self):
        s = self.verdict(timing={"met": False, "constrained": True, "wns": -0.4, "tns_failing": 3, "checks": {}},
                         critical_warnings=[{"id": "Timing 38-282", "text": "failed to meet timing"}])
        self.assertEqual((s["status"], s["verification"]["timing"]), ("timing_failed", "failed"))
        self.assertFalse(B.build_ok(s, "error"))
        self.assertTrue(B.build_ok(s, "warn"))          # the timing critical warning is not counted twice

        s = self.verdict(timing={"met": True, "constrained": True, "checks": {"no_clock": 8}})
        self.assertEqual((s["status"], s["verification"]["timing"]), ("unverified", "incomplete"))

        s = self.verdict(timing={"met": None, "constrained": False, "checks": {"no_clock": 0}},
                         utilization={"ff": {"used": 0}})
        self.assertEqual((s["status"], s["verification"]["timing"]), ("passed", "not_applicable"))

        s = self.verdict(timing={"met": None, "constrained": False, "checks": {}}, utilization={"ff": {"used": 5}})
        self.assertEqual((s["status"], s["verification"]["timing"]), ("unverified", "unconstrained"))

    def test_missing_reports_are_not_a_pass(self):
        s = self.verdict(reports={})
        self.assertEqual(s["status"], "unverified")
        self.assertEqual((s["verification"]["timing"], s["verification"]["drc"]), ("unknown", "unknown"))
        self.assertFalse(B.build_ok(s, "warn"))         # not a timing problem: "warn" does not excuse it

    def test_critical_warnings_and_waivers(self):
        cw = [{"id": "Common 17-55", "text": "'set_property' expects at least one object."},
              {"id": "Constraints 18-5210", "text": "No constraints selected for write.", "benign": "routine"}]
        s = self.verdict(critical_warnings=cw)
        self.assertEqual((s["status"], s["verification"]["critical_warnings"]), ("unverified", "present"))
        self.assertFalse(B.build_ok(s, "warn"))
        s = self.verdict({"Common 17-55": "reviewed"}, critical_warnings=cw)
        self.assertEqual((s["status"], s["verification"]["critical_warnings"]), ("passed", "waived"))
        self.assertEqual(s["critical_warnings"][0]["waived"], "reviewed")

        drc = [{"rule": "PDCN-1569", "severity": "Critical Warning", "description": "x", "count": 1}]
        self.assertEqual(self.verdict(drc=drc)["verification"]["drc"], "violations")
        self.assertEqual(self.verdict({"DRC PDCN-1569": "ok"}, drc=drc)["status"], "passed")

    def test_no_bitstream_is_failed(self):
        s = self.verdict(bitstream=None, stage="synthesis")
        self.assertEqual((s["status"], s["verification"]["bitstream"]), ("failed", "missing"))
        self.assertFalse(B.build_ok(s, "warn"))


if __name__ == "__main__":
    unittest.main()
