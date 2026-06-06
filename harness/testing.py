"""Test doubles and synthetic-series builders for the judgment layer.

``FakeFoundationGateway`` is the P1 implementation of the ``FoundationGateway`` seam: it
returns *injected* synthetic results so the entire judgment layer (objective, gates,
stability) is tested with no live data and no ``quant_strategies`` call. This is what makes
AC-1 / AC-4 / AC-9 deterministic.

Lives in ``harness/`` (not ``tests/``) so it can be imported as ``harness.testing`` by any
test module without path games; it is a testing utility, never used by the real evaluator.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np

from harness.foundation import (
    FoldEvalResult,
    FoldReturns,
    QuickRunResult,
)


class FakeFoundationGateway:
    """A ``FoundationGateway`` that returns injected synthetic results.

    Two ways to drive ``quick_run`` (used by the stability gate):

    - ``quick_metric_fn``: ``Callable[[Experiment], float | None]`` — the in-sample metric
      as a function of the (perturbed) experiment params. Lets a test sculpt a plateau or
      a knife-edge around θ*.
    - ``quick_result``: a fixed ``QuickRunResult`` returned for every call (when params do
      not matter to the test).

    ``evaluate`` returns ``eval_results`` in order (one per fold), or a single fixed
    ``eval_result`` repeated.
    """

    def __init__(
        self,
        *,
        quick_metric_fn: Callable[[Any], float | None] | None = None,
        quick_result: QuickRunResult | None = None,
        eval_results: list[FoldEvalResult] | None = None,
        eval_result: FoldEvalResult | None = None,
        valid: bool = True,
        causal_ok: bool = True,
        trade_count: int = 100,
        slices: Mapping[str, Mapping[str, float]] | None = None,
    ) -> None:
        self._quick_metric_fn = quick_metric_fn
        self._quick_result = quick_result
        self._eval_results = list(eval_results) if eval_results else None
        self._eval_result = eval_result
        self._valid = valid
        self._causal_ok = causal_ok
        self._trade_count = trade_count
        # Reconciled with the REAL adapter's diagnostic axes (P5): the foundation emits
        # ``by_symbol`` / ``by_direction`` / ``by_exit_reason`` — there is NO ``by_month`` /
        # ``by_hour`` calendar axis (those were invented). ``by_symbol`` is the load-bearing
        # leg the escalation gate's cheap-robust check reads, so the Fake's default mirrors
        # what escalation will see in production.
        self._slices = slices or {"by_symbol": {}}
        self.quick_run_calls: list[Any] = []
        self.evaluate_calls: list[Any] = []
        self._eval_idx = 0

    def quick_run(self, experiment, protocol, window) -> QuickRunResult:  # noqa: ARG002
        self.quick_run_calls.append(experiment)
        if self._quick_result is not None and self._quick_metric_fn is None:
            return self._quick_result
        metric = self._quick_metric_fn(experiment) if self._quick_metric_fn else 1.0
        return QuickRunResult(
            valid=self._valid,
            causal_ok=self._causal_ok,
            in_sample_metric=metric,
            trade_count=self._trade_count,
            slices=self._slices,
            failure_stage=None if self._valid else "contract",
        )

    def evaluate(self, experiment, protocol, window) -> FoldEvalResult:  # noqa: ARG002
        self.evaluate_calls.append(experiment)
        if self._eval_results is not None:
            result = self._eval_results[self._eval_idx % len(self._eval_results)]
            self._eval_idx += 1
            return result
        if self._eval_result is not None:
            return self._eval_result
        raise RuntimeError("FakeFoundationGateway.evaluate called with no injected result")


# --------------------------------------------------------------------------- #
# Synthetic-series builders (deterministic; seeded RNG only here, never in core).
# --------------------------------------------------------------------------- #


def make_returns(
    values: np.ndarray | list[float],
    periods_per_year: float = 8760.0,
    start: str = "2025-01-01",
    by_symbol: Mapping[str, "FoldReturns"] | None = None,
) -> FoldReturns:
    """Build a ``FoldReturns`` from a value array with synthetic increasing timestamps."""
    vals = np.asarray(values, dtype=np.float64)
    ts = np.arange(vals.size, dtype="timedelta64[h]") + np.datetime64(start)
    return FoldReturns(
        timestamps=ts.astype("datetime64[ns]"),
        values=vals,
        periods_per_year=periods_per_year,
        by_symbol=by_symbol,
    )


def noisy_alpha_series(
    n: int = 400,
    mean: float = 0.0005,
    sd: float = 0.01,
    seed: int = 0,
) -> np.ndarray:
    """A return series with a genuine positive drift (real residual edge)."""
    rng = np.random.default_rng(seed)
    return mean + sd * rng.standard_normal(n)


def factor_series(n: int = 400, sd: float = 0.02, seed: int = 1) -> np.ndarray:
    """A zero-alpha factor return series (e.g. the market/benchmark)."""
    rng = np.random.default_rng(seed)
    return sd * rng.standard_normal(n)


def beta_exposed_series(
    factor: np.ndarray, beta: float = 1.3, idio_sd: float = 1e-9, seed: int = 2
) -> np.ndarray:
    """A return series that is PURE factor beta: ``beta * factor`` (+ negligible idio).

    Residualizing this against the factor leaves ≈0 alpha (AC-9).
    """
    rng = np.random.default_rng(seed)
    return beta * factor + idio_sd * rng.standard_normal(factor.size)


def funding_carry_series(
    funding: np.ndarray, loading: float = 1.0, idio_sd: float = 1e-9, seed: int = 3
) -> np.ndarray:
    """A return series that is PURE funding-carry collection: ``loading * funding``.

    Funding is carry — regressed out as a panel column — so this residualizes to ≈0 (AC-9).
    """
    rng = np.random.default_rng(seed)
    return loading * funding + idio_sd * rng.standard_normal(funding.size)
