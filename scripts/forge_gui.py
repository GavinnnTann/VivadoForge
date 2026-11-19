#!/usr/bin/env python3
"""VivadoForge desktop helper: a small window over `scripts/forge.py` for people who prefer buttons.

    python scripts/forge_gui.py

Every button runs the same forge.py command you could type, and shows its output. Nothing here
has extra behaviour, so the GUI and the command line always agree.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
FORGE = SCRIPTS / "forge.py"


def forge_json(*args: str) -> dict:
    """Run a quick forge.py command and return its JSON (or an error dict)."""
    try:
        r = subprocess.run([sys.executable, str(FORGE), *args, "--json"], cwd=REPO, capture_output=True,
                           text=True, timeout=120)
        return json.loads(r.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VivadoForge")
        self.geometry("1000x680")
        self.minsize(800, 500)
        self.proc: subprocess.Popen | None = None
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.buttons: list[ttk.Button] = []
        self._build_ui()
        self.refresh()
        self.after(100, self._drain)

    # ---- layout -------------------------------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        self.summary = ttk.Label(top, text="Loading ...", font=("", 10, "bold"))
        self.summary.pack(anchor="w")
        self.detail = ttk.Label(top, text="", foreground="#555")
        self.detail.pack(anchor="w")

        bar = ttk.Frame(self, padding=(10, 0, 10, 6))
        bar.pack(fill="x")
        for label, args, confirm in (
                ("Check", ["check"], None),
                ("Simulate", ["sim"], None),
                ("Build", ["build"], None),
                ("Report", ["report"], None),
                ("Program", ["program", "--yes"], "program"),
                ("Flash", ["flash", "--yes"], "flash"),
                ("Find board", ["devices"], None),
                ("Open in Vivado", ["open"], None),
                ("Clean", ["clean"], "clean")):
            b = ttk.Button(bar, text=label, command=lambda a=args, c=confirm: self.run(a, c))
            b.pack(side="left", padx=(0, 6))
            self.buttons.append(b)
        self.stop_btn = ttk.Button(bar, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="right")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._output_tab()
        self._new_tab()
        self._pins_tab()
        self._settings_tab()

    def _output_tab(self):
        f = ttk.Frame(self.tabs)
        self.tabs.add(f, text="  Output  ")
        self.out = scrolledtext.ScrolledText(f, font=("Consolas", 9), wrap="none")
        self.out.pack(fill="both", expand=True)
        self.out.tag_configure("bad", foreground="#b00020")
        self.out.tag_configure("good", foreground="#1b7f2a")
        self.out.tag_configure("cmd", foreground="#555555")

    def _new_tab(self):
        f = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(f, text="  New project  ")
        ttk.Label(f, text="Create the project in this folder from a template. This replaces src/, tb/ "
                          "and constraints/.", wraplength=800).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Board").grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.board_var = tk.StringVar()
        self.board_box = ttk.Combobox(f, textvariable=self.board_var, state="readonly", width=40)
        self.board_box.grid(row=1, column=1, sticky="w", pady=(12, 4))
        self.board_box.bind("<<ComboboxSelected>>", lambda e: self._filter_templates())
        ttk.Label(f, text="Template").grid(row=2, column=0, sticky="w", pady=4)
        self.tpl_var = tk.StringVar()
        self.tpl_box = ttk.Combobox(f, textvariable=self.tpl_var, state="readonly", width=40)
        self.tpl_box.grid(row=2, column=1, sticky="w", pady=4)
        self.tpl_box.bind("<<ComboboxSelected>>", lambda e: self._describe_template())
        ttk.Label(f, text="Project name").grid(row=3, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.name_var, width=43).grid(row=3, column=1, sticky="w", pady=4)
        self.tpl_desc = ttk.Label(f, text="", wraplength=700, foreground="#555")
        self.tpl_desc.grid(row=4, column=0, columnspan=3, sticky="w", pady=8)
        b = ttk.Button(f, text="Create project", command=self._create)
        b.grid(row=5, column=1, sticky="w")
        self.buttons.append(b)
        self.templates: list[dict] = []
        self.boards: list[dict] = []

    def _pins_tab(self):
        f = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(f, text="  Board pins  ")
        cols = ("port", "pin", "iostandard", "role", "polarity", "used_by")
        self.pins = ttk.Treeview(f, columns=cols, show="headings", height=18)
        for c, w in zip(cols, (150, 70, 100, 110, 90, 150)):
            self.pins.heading(c, text=c.replace("_", " "))
            self.pins.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(f, orient="vertical", command=self.pins.yview)
        self.pins.configure(yscrollcommand=sb.set)
        self.pins.grid(row=0, column=0, columnspan=4, sticky="nsew")
        sb.grid(row=0, column=4, sticky="ns")
        f.rowconfigure(0, weight=1)
        f.columnconfigure(3, weight=1)
        ttk.Label(f, text="Name in your design:").grid(row=1, column=0, sticky="w", pady=6)
        self.pin_name = tk.StringVar()
        ttk.Entry(f, textvariable=self.pin_name, width=24).grid(row=1, column=1, sticky="w", padx=6)
        b = ttk.Button(f, text="Add selected pin to constraints", command=self._add_pin)
        b.grid(row=1, column=2, sticky="w")
        self.buttons.append(b)
        ttk.Label(f, text="Leave the name empty to keep the board's port name.",
                  foreground="#555").grid(row=2, column=0, columnspan=4, sticky="w")

    def _settings_tab(self):
        f = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(f, text="  This computer  ")
        ttk.Label(f, text="Saved in forge.local.toml (not committed). Leave empty to auto-detect.",
                  foreground="#555").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Vivado").grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.viv_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.viv_var, width=70).grid(row=1, column=1, sticky="w", pady=(12, 4))
        ttk.Button(f, text="Browse", command=self._browse_vivado).grid(row=1, column=2, padx=6, pady=(12, 4))
        ttk.Label(f, text="Build folder").grid(row=2, column=0, sticky="w", pady=4)
        self.bdir_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.bdir_var, width=70).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(f, text="Tip: inside OneDrive/Dropbox use a local folder such as C:/fpga_build/{name}",
                  foreground="#555").grid(row=3, column=1, sticky="w")
        row = ttk.Frame(f)
        row.grid(row=4, column=1, sticky="w", pady=12)
        for label, cmd in (("Detect Vivado", self._detect), ("Save", self._save_settings)):
            b = ttk.Button(row, text=label, command=cmd)
            b.pack(side="left", padx=(0, 6))
            self.buttons.append(b)

    # ---- data ---------------------------------------------------------------------------------
    def refresh(self):
        info = forge_json("info")
        if info.get("ok") is False:
            self.summary.config(text="No project yet: create one on the 'New project' tab")
            self.detail.config(text=info.get("error", ""))
        else:
            p, b, t = info["project"], info["board"], info["tools"]
            last = info.get("last_build") or {}
            timing = (last.get("timing") or {}).get("wns")
            self.summary.config(text=f"{p['name']}  (top {p['top']})  on  {b['name']}  [{b['part']}]")
            self.detail.config(text=(
                f"clock {b['clock']['freq_hz'] / 1e6:g} MHz  |  {len(p['sources'])} sources, {len(p['tests'])} tests  |  "
                f"last build: {last.get('status', 'none')}" + (f", WNS {timing} ns" if timing is not None else "") +
                f"  |  Vivado: {(t.get('vivado') or {}).get('version', 'NOT FOUND')}"))
            self.viv_var.set("")
            self.bdir_var.set(p["build_dir"])
            self._load_pins()
        self.boards = forge_json("boards").get("boards", [])
        self.templates = forge_json("templates").get("templates", [])
        self.board_box["values"] = [f"{b['id']}  -  {b['name']}" for b in self.boards]
        if self.boards and not self.board_var.get():
            current = (info.get("board") or {}).get("id")
            ids = [b["id"] for b in self.boards]
            self.board_box.current(ids.index(current) if current in ids else 0)
        self._filter_templates()

    def _selected_board(self) -> str:
        return self.board_var.get().split("  -  ")[0].strip()

    def _filter_templates(self):
        board = self._selected_board()
        names = [t["name"] for t in self.templates if board in t["boards"]]
        self.tpl_box["values"] = names
        if names:
            self.tpl_box.current(0)
        self._describe_template()

    def _describe_template(self):
        t = next((t for t in self.templates if t["name"] == self.tpl_var.get()), None)
        self.tpl_desc.config(text=t["description"] if t else "")
        if t and not self.name_var.get():
            self.name_var.set(t["name"])

    def _load_pins(self):
        data = forge_json("pins")
        self.pins.delete(*self.pins.get_children())
        for r in data.get("pins", []):
            pol = "" if r.get("active_low") is None else ("active-low" if r["active_low"] else "active-high")
            self.pins.insert("", "end", values=(r["port"], r["pin"], r["iostandard"], r["role"], pol, r["used_by"] or ""))

    # ---- actions ------------------------------------------------------------------------------
    def run(self, args: list[str], confirm: str | None = None, then=None):
        if self.proc is not None:
            return
        if confirm == "program" and not messagebox.askyesno(
                "Program FPGA", "Load the last bitstream into the connected board?\n(Volatile: lost at power-off.)"):
            return
        if confirm == "flash" and not messagebox.askyesno(
                "Write flash", "Erase and rewrite the board's configuration flash?\n"
                               "The board will boot this design at every power-up."):
            return
        if confirm == "clean" and not messagebox.askyesno("Clean", "Delete the build folder?"):
            return
        self.tabs.select(0)
        self.out.insert("end", f"\n$ python scripts/forge.py {' '.join(args)}\n", "cmd")
        self.out.see("end")
        for b in self.buttons:
            b.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self._then = then

        def worker():
            try:
                self.proc = subprocess.Popen([sys.executable, "-u", str(FORGE), *args], cwd=REPO, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                                             encoding="utf-8", errors="replace", bufsize=1)
                for line in self.proc.stdout:
                    self.lines.put(line)
                self.proc.wait()
                self.lines.put(f"[exit code {self.proc.returncode}]\n")
            except OSError as exc:
                self.lines.put(f"failed to start: {exc}\n")
            self.lines.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def _drain(self):
        try:
            while True:
                line = self.lines.get_nowait()
                if line is None:
                    self.proc = None
                    for b in self.buttons:
                        b.state(["!disabled"])
                    self.stop_btn.state(["disabled"])
                    self.refresh()
                    if self._then:
                        self._then()
                    continue
                tag = "bad" if any(k in line for k in ("ERROR", "FAIL", "error:")) else \
                      "good" if any(k in line for k in ("PASS", "DONE")) else None
                self.out.insert("end", line, tag)
                self.out.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def stop(self):
        if self.proc is not None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                self.proc.kill()

    def _create(self):
        board, tpl, name = self._selected_board(), self.tpl_var.get(), self.name_var.get().strip()
        if not board or not tpl:
            messagebox.showerror("Missing choice", "Pick a board and a template.")
            return
        if any((REPO / d).is_dir() and any((REPO / d).iterdir()) for d in ("src", "tb", "constraints")):
            if not messagebox.askyesno("Replace project?", "src/, tb/ and constraints/ already contain files.\n"
                                                           "Delete them and create the new project?"):
                return
        args = ["new", "--template", tpl, "--board", board, "--force"]
        if name:
            args += ["--name", name]
        self.run(args, then=lambda: self.run(["check"]))

    def _add_pin(self):
        sel = self.pins.selection()
        if not sel:
            messagebox.showinfo("Pick a pin", "Select a row in the table first.")
            return
        port = self.pins.item(sel[0], "values")[0]
        name = self.pin_name.get().strip()
        self.run(["pins", "add", f"{port}={name}" if name else port])

    def _browse_vivado(self):
        path = filedialog.askopenfilename(title="Find vivado.bat (Windows) or vivado (Linux)",
                                          filetypes=[("Vivado", "vivado*"), ("All files", "*")])
        if path:
            self.viv_var.set(path)

    def _detect(self):
        self.run(["setup", "--detect"])

    def _save_settings(self):
        args = ["setup"]
        if self.viv_var.get().strip():
            args += ["--vivado", self.viv_var.get().strip()]
        if self.bdir_var.get().strip():
            args += ["--build-dir", self.bdir_var.get().strip()]
        self.run(args)


if __name__ == "__main__":
    App().mainloop()
