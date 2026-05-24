# AGENTS.md

## Project Target

This repo is a fast quant candidate research workbench. It is not the final validation framework.

The goal is to iterate on one scratch strategy with a cheap guard screen, run
deliberate promotion screening only for serious candidates, and send only
promoted candidates to comprehensive validation.

## Research Protocol

- Read `program.md` before running the research loop.
- Use `README.md` for repository file contracts and runner entry points.
- Treat `strategy.py` and `experiment.toml` as the ordinary editable research
  surface.
- Treat `runner.py`, `scoring.py`, `experiment_config.py`, tests, generated
  results, and ledgers as harness or evidence unless the user explicitly asks
  for harness changes.

## Quant Research Posture

- The cheap guard screen and deliberate promotion screening are loop feedback,
  not market evidence.
- Prefer simple robust candidates over complex fragile ones.
- Do not chase one-window wins.
- Do not call a promoted candidate validated; comprehensive validation is a
  separate downstream process.
