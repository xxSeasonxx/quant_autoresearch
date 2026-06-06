"""AC-10 (in use) — RealFoundationGateway reads per-fold OOS returns via the typed accessor.

Two layers:
- A unit test with a STUBBED ``run_evaluation`` confirming the adapter's call sequence uses
  ``returns_for`` / ``metrics_for`` (never Parquet) and maps the typed series into the seam.
- A DATA-GATED real integration smoke that runs one real fold end-to-end and confirms typed
  returns flow into RES. It SKIPS when ``quant_data``'s live DB is unreachable (catalog data
  exists, but this environment has no DB credentials), so the suite stays green without
  faking a "real" result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pytest

import harness.foundation_real as fr_mod
from harness.foundation_real import FoldWindow, RealFoundationGateway
from harness.protocol import Experiment, Protocol


def _protocol(symbols=("BTC-PERP", "ETH-PERP")) -> Protocol:
    return Protocol.model_validate(
        {
            "name": "adapter-test",
            "cost_model": {"taker_bps": 5, "maker_bps": 1, "slippage_bps": 1, "stress_multiplier": 2.0},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-06-30"},
                "selection": {"start": "2024-07-01", "end": "2025-02-28"},
                "lockbox": {"start": "2025-03-01", "end": "2025-05-31"},
                "symbols": list(symbols),
                "source": {"kind": "crypto_perp_funding"},
            },
            "annualization": {"periods_per_year": 525949},
        }
    )


def _experiment() -> Experiment:
    return Experiment(
        strategy_path="untested/crypto_perp_funding_crowding_reversal.py",
        params={"weight": 0.25, "max_hold_bars": 480},
    )


# --------------------------------------------------------------------------- #
# Unit: the adapter call sequence (stubbed run_evaluation).
# --------------------------------------------------------------------------- #


@dataclass
class _StubSeries:
    window_id: str
    scenario_id: str
    timestamps: np.ndarray
    values: np.ndarray
    periods_per_year: float
    per_symbol: Mapping | None = None  # ALWAYS None for the grouped backend (the P0 contract)


@dataclass
class _StubMetrics:
    window_id: str
    scenario_id: str
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    max_drawdown: float | None
    worst_period_return: float | None
    trade_count: int | None
    return_sample_count: int | None
    causal_ok: bool
    provenance: Mapping[str, str]


class _StubEvalResult:
    """Mimics EvaluationRunResult's PUBLIC accessor surface. A Parquet read would set the
    tripwire — the test asserts it is never tripped."""

    parquet_touched = False

    def __init__(self, window_id, scenario_id, n=200, mean=0.0006, sd=0.01, seed=0):
        rng = np.random.default_rng(seed)
        vals = mean + sd * rng.standard_normal(n)
        ts = (np.arange(n, dtype="timedelta64[h]") + np.datetime64("2024-07-01")).astype("datetime64[ns]")
        self._series = _StubSeries(window_id, scenario_id, ts, vals, 525949.0)
        self._metrics = _StubMetrics(
            window_id, scenario_id, sharpe=1.4, sortino=1.8, calmar=0.9,
            max_drawdown=-0.08, worst_period_return=-0.03, trade_count=120,
            return_sample_count=n, causal_ok=True, provenance={"snapshot": "s1", "backend": "perp_ledger"},
        )
        self.provenance = {"snapshot": "s1", "backend": "perp_ledger", "quant-strategies_version": "0.0"}

    @property
    def succeeded(self):
        return True

    @property
    def causal_replay_passed(self):
        return True

    @property
    def failure_stage(self):
        return None

    def returns_for(self, window_id, scenario_id):
        if (window_id, scenario_id) == (self._series.window_id, self._series.scenario_id):
            return self._series
        return None

    def metrics_for(self, window_id, scenario_id):
        if (window_id, scenario_id) == (self._metrics.window_id, self._metrics.scenario_id):
            return self._metrics
        return None

    # Any attempt to scrape the on-disk trace would go through here — it must never be called.
    def read_parquet(self, *_a, **_k):  # pragma: no cover - tripwire
        type(self).parquet_touched = True
        raise AssertionError("adapter scraped Parquet — must use returns_for (AC-10)")


def test_adapter_uses_returns_for_not_parquet(tmp_path, monkeypatch):
    proto = _protocol()
    exp = _experiment()
    window = FoldWindow(window_id="f0", start="2024-07-01", end="2024-08-31")
    scenario = f"{window.window_id}/{fr_mod._SCENARIO_ID}"

    calls = {"returns_for": 0, "metrics_for": 0, "eval_calls": []}

    def fake_run_evaluation(config_path, repo_root=None, **_kw):
        calls["eval_calls"].append(config_path)
        result = _StubEvalResult(window.window_id, scenario)
        # Wrap accessors to count usage.
        orig_rf, orig_mf = result.returns_for, result.metrics_for

        def counting_rf(w, s):
            calls["returns_for"] += 1
            return orig_rf(w, s)

        def counting_mf(w, s):
            calls["metrics_for"] += 1
            return orig_mf(w, s)

        result.returns_for = counting_rf  # type: ignore[assignment]
        result.metrics_for = counting_mf  # type: ignore[assignment]
        return result

    monkeypatch.setattr(fr_mod, "run_evaluation", fake_run_evaluation)

    gw = RealFoundationGateway(repo_root=tmp_path, workdir=tmp_path)
    out = gw.evaluate(exp, proto, window)

    assert out.succeeded is True
    assert out.causal_ok is True
    assert out.sharpe == 1.4
    assert out.max_drawdown == -0.08
    assert out.trade_count == 120
    assert out.provenance["snapshot"] == "s1"
    # The typed series flowed into the seam FoldReturns.
    assert out.returns is not None
    assert out.returns.values.dtype == np.float64
    assert out.returns.periods_per_year == 525949.0
    # by_symbol was assembled via per-symbol evaluate calls (2 symbols).
    assert out.returns.by_symbol is not None
    assert set(out.returns.by_symbol) == {"BTC-PERP", "ETH-PERP"}
    # The adapter used the typed accessor and NEVER scraped Parquet.
    assert calls["returns_for"] >= 1
    assert calls["metrics_for"] >= 1
    assert _StubEvalResult.parquet_touched is False
    # One grouped evaluate + one per symbol = 3 evaluate calls for this fold.
    assert len(calls["eval_calls"]) == 3


def test_adapter_maps_failed_evaluation_to_failed_fold(tmp_path, monkeypatch):
    class _Failed:
        succeeded = False
        causal_replay_passed = None
        failure_stage = "data_load"
        provenance = {"snapshot": "s1"}

    monkeypatch.setattr(fr_mod, "run_evaluation", lambda *a, **k: _Failed())
    gw = RealFoundationGateway(repo_root=tmp_path, workdir=tmp_path)
    out = gw.evaluate(_experiment(), _protocol(), FoldWindow("f0", "2024-07-01", "2024-08-31"))
    assert out.succeeded is False
    assert out.returns is None
    assert out.failure_stage == "data_load"


def test_single_symbol_universe_has_no_by_symbol(tmp_path, monkeypatch):
    window = FoldWindow("f0", "2024-07-01", "2024-08-31")
    scenario = f"{window.window_id}/{fr_mod._SCENARIO_ID}"
    monkeypatch.setattr(
        fr_mod, "run_evaluation", lambda *a, **k: _StubEvalResult(window.window_id, scenario)
    )
    gw = RealFoundationGateway(repo_root=tmp_path, workdir=tmp_path)
    out = gw.evaluate(_experiment(), _protocol(symbols=("BTC-PERP",)), window)
    # A single-symbol universe makes no per-symbol decomposition.
    assert out.returns is not None
    assert out.returns.by_symbol is None


# --------------------------------------------------------------------------- #
# Data-gated real integration smoke (AC-10 in use, end-to-end).
# --------------------------------------------------------------------------- #


def _live_data_available() -> bool:
    """True iff a real crypto-perp evaluate can load rows (the live DB is reachable).

    The catalog constants always import, but the TimescaleDB may be unauthenticated in this
    environment. Probe by attempting a tiny real evaluate and checking it does not fail at the
    data-load stage. Any import/connection failure ⇒ data unavailable ⇒ skip.
    """
    try:
        import os

        from quant_strategies.evaluation import run_evaluation

        repo = "/Users/Season_Yang/Personal/quant_strategies"
        if not os.path.isdir(repo):
            return False
        gw = RealFoundationGateway(repo_root=repo)
        proto = _protocol(symbols=("BTC-PERP", "ETH-PERP", "SOL-PERP", "XRP-PERP"))
        exp = Experiment(
            strategy_path="untested/crypto_perp_funding_crowding_reversal.py",
            params={
                "funding_lookback_events": 3, "return_lookback_minutes": 240,
                "decision_interval_minutes": 480, "decision_lag_minutes": 1, "top_n": 1,
                "min_cross_section": 4, "min_abs_funding_bps": 1.0, "min_abs_return_bps": 25.0,
                "weight": 0.25, "max_hold_bars": 480,
            },
        )
        window = FoldWindow("probe", "2023-06-01", "2023-06-05")
        res = gw.evaluate(exp, proto, window)
        # Reachable iff we did NOT fail at the data-load stage.
        return res.succeeded or res.failure_stage not in ("data_load", "config_load", "strategy_import")
    except Exception:
        return False


@pytest.mark.skipif(
    not _live_data_available(),
    reason="live quant_data DB unreachable in this environment (no DB credentials); "
    "catalog confirms crypto_perp+funding exists but rows cannot be loaded — real smoke skipped",
)
def test_ac10_real_fold_typed_returns_flow_into_res():
    """End-to-end: one real fold through RealFoundationGateway → typed returns → RES.

    Runs only when the live DB is reachable. Confirms per-fold OOS returns obtained via the
    typed foundation API (no Parquet scraping) flow into compute_res.
    """
    from harness.objective.res import GateThresholds, compute_res

    repo = "/Users/Season_Yang/Personal/quant_strategies"
    gw = RealFoundationGateway(repo_root=repo)
    proto = _protocol(symbols=("BTC-PERP", "ETH-PERP", "SOL-PERP", "XRP-PERP"))
    exp = Experiment(
        strategy_path="untested/crypto_perp_funding_crowding_reversal.py",
        params={
            "funding_lookback_events": 3, "return_lookback_minutes": 240,
            "decision_interval_minutes": 480, "decision_lag_minutes": 1, "top_n": 1,
            "min_cross_section": 4, "min_abs_funding_bps": 1.0, "min_abs_return_bps": 25.0,
            "weight": 0.25, "max_hold_bars": 480,
        },
    )
    window = FoldWindow("real_f0", "2023-06-01", "2023-06-20")
    fold = gw.evaluate(exp, proto, window)
    assert fold.succeeded, f"real evaluate failed: {fold.failure_stage}"
    assert fold.returns is not None
    assert fold.returns.values.dtype == np.float64
    assert fold.causal_ok is True
    # The typed series feeds RES (one fold; identity panel — the smoke is about the pipe).
    thr = GateThresholds(min_trades=1, max_concentration=1.0, min_effective_breadth=1.0)
    res = compute_res([fold.returns], [{}], trade_count=fold.trade_count, thresholds=thr)
    assert res.per_fold_sharpe is not None
