# AGENTS.md

Canonical agent contract for `quant_autoresearch`.

## Role

Run one active strategy through the fixed quant engine harness.

## Editable Files During A Loop

Agents may edit only:

- `strategy.py`
- `experiment.yml`

Do not edit `runner.py`, `prepare.py`, `README.md`, `AGENTS.md`, or artifact
files unless Season explicitly asks.

## Rules

- No strategy registry.
- No strategy discovery.
- No paper-trading approval.
- No autonomous mutation outside the two editable files.
- Use `conda run -n quant <command>` for Python commands.
