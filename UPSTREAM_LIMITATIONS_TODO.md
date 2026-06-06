# Upstream Limitations TODO

This file is only for research ideas that are worth testing but are blocked by
upstream data, engine, or harness capabilities. Do not use it for ordinary
strategy parameters, failed attempts, or generated run results.

Each note should include:

- the strategy idea or hypothesis
- the missing upstream capability
- why the current harness cannot test it faithfully
- the validation it would unlock

## Open Items

- **Live `quant_data` database access for real end-to-end validation.**
  - *Idea / what it unlocks:* running the real foundation fold, the live factor-panel build, and
    bit-for-bit metric reproduction from a pinned `quant_data` snapshot — i.e. AC-1 end-to-end,
    AC-7, and AC-10 against real market data rather than the fake gateway.
  - *Missing upstream capability:* a reachable `quant_data` database (this environment has no DB
    credentials; the catalog confirms `crypto_perp_1min_with_funding` / ADA-PERP exists, but rows
    cannot be loaded).
  - *Why the harness cannot test it faithfully today:* the real-data smoke tests in
    `tests/harness/test_foundation_real.py` skip without DB access; all judgment logic is therefore
    verified only against synthetic/fake-gateway series.
  - *Validation it would unlock:* a real campaign verdict and confirmation that the
    `RealFoundationGateway` / `RealFactorPanelProvider` wiring behaves as the seam contract expects.