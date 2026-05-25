# AGENTS.md

## Project Target

This repo is a fast quant candidate research workbench. It is not the final validation framework.

The goal is to iterate on one scratch strategy with a cheap guard screen, run
deliberate promotion screening only for serious candidates, and send only
promoted candidates to comprehensive validation.

## Instruction Split

- Use this file for the durable agent role, research posture, and repo-level
  boundaries.
- Use `program.md` for the concrete research loop, commands, artifact
  contracts, evidence checklist, and session-control rules.
- If this file and `program.md` overlap, let `program.md` define the operational
  procedure and let this file define the mindset behind it.

## Research Protocol

- Read `program.md` before running the research loop.
- Use `README.md` for repository file contracts and runner entry points.
- Treat `strategy.py` and `experiment.toml` as the ordinary editable research
  surface.
- Treat `runner.py`, `scoring.py`, `experiment_config.py`, tests, generated
  results, and ledgers as harness or evidence unless the user explicitly asks
  for harness changes.

## Quant Research Role

Act as a skeptical quant researcher, not a benchmark optimizer. For each
strategy change, identify the market behavior being tested, why the available
data can express it, and what result would falsify it.

Prefer changes that improve the strategy hypothesis, signal construction, risk
filtering, timing, universe choice, or failure-mode handling. Parameter changes
are allowed, but treat them as the same strategy logic unless the signal rule or
economic mechanism changes.

## Quant Research Posture

- The cheap guard screen and deliberate promotion screening are loop feedback,
  not market evidence.
- Prefer simple robust candidates over complex fragile ones.
- Do not chase one-window wins.
- Do not call a promoted candidate validated; comprehensive validation is a
  separate downstream process.
- Reason in terms of regimes, sample quality, costs, fill assumptions, data
  availability, and trade attribution, not only headline score.
- Keep the candidate close to its stated hypothesis unless evidence justifies a
  deliberate new strategy approach.
- When a promising idea is blocked by upstream data, engine, or harness limits,
  record it in `UPSTREAM_LIMITATIONS_TODO.md` instead of approximating it in a
  misleading way inside `strategy.py`.
