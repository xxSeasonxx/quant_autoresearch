# ADR-0001: Curated-Few Research Regime

## Status

Accepted

## Context

`quant_autoresearch` is a personal research workbench for one human-seeded thesis at a time. The objective is not to certify deployability from historical data; it is to produce simple, causal Train survivors worth Season's downstream OOS, paper, and small-live review.

The repo deliberately does not operate as an automated-many strategy miner. That distinction controls how much validation machinery is appropriate.

## Decision

Use a curated-few thesis-driven regime:

- Season owns thesis selection and protocol setup.
- The agent explores strategy expression on Train inside the editable surface.
- The backend records bounded Train evidence and stops on protocol rules.
- OOS review is one-look, downstream, and human-owned.
- Paper and small-live review remain the real forward filters before any scaling.

## Consequences

This keeps the project small and lets the agent focus on strategy development instead of operating a research platform. It also means Train survivors are only candidates for downstream review, not proof of profitability.

Heavier automated-many controls become necessary if any of these triggers occur:

- automated generation of many independent candidates;
- repeated OOS looks used to select or tune candidates;
- historical validation being treated as deployment evidence;
- strategy family tracking becomes too large to audit manually;
- Season wants portfolio-wide statistical claims from historical research alone.

If those triggers appear, add a separate change for multiple-testing controls, family tracking, and validation governance rather than expanding the current Train loop quietly.
