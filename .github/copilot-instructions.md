# Copilot instructions

Follow `AGENTS.md` at the repository root: it holds this project's rules, commands and
conventions. The most important ones:

- Use `python scripts/forge.py info --json` and `board --json` before changing anything.
- Never type FPGA pin numbers; use `python scripts/forge.py pins add <board port>=<name>`.
- Work in the order `check`, `sim`, `build`, and report what was actually verified.
- Never run `forge.py program` or `forge.py flash` without the user's explicit approval.

Step-by-step procedures are in `.claude/skills/*/SKILL.md`.
