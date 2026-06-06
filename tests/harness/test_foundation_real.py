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

import json
from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pytest

import harness.foundation_real as fr_mod
from harness.foundation_real import FoldWindow, RealFactorPanelProvider, RealFoundationGateway
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
# quick_run coarse band + slices — read against the foundation's REAL artifact
# schema (summary.json economic_metrics + diagnostics.json), not invented keys.
#
# The fixtures below mirror the foundation's actual output:
#   summary.json   -> economic_metrics from quant_strategies.runner.economic_metrics
#                     .summary_metrics (top-level key "economic_metrics"; the coarse
#                     after-costs number is "average_trade_net").
#   diagnostics.json -> quant_strategies.runner.diagnostics.diagnostic_payload
#                       (top-level "by_symbol"/"by_direction"/"by_exit_reason" + nested
#                       "economic_slices"; NO "slices"/"by_month"/"by_hour" wrapper).
# --------------------------------------------------------------------------- #


# Real summary.json shape: economic_metrics is a TOP-LEVEL key; the sign-meaningful
# after-costs coarse number is average_trade_net (positive ⇒ in-sample edge after costs).
_REAL_SUMMARY = {
    "strategy_id": "crypto_perp_funding_crowding_reversal",
    "status": "completed",
    "economic_metrics": {
        "schema_version": "quant_strategies.runner.economic_metrics/v1",
        "basis": "engine_trade_ledger",
        "trade_count": 142,
        "winning_trade_count": 81,
        "losing_trade_count": 60,
        "flat_trade_count": 1,
        "hit_rate": 0.5704,
        "average_trade_net": 0.00037,
        "average_win_net": 0.0042,
        "average_loss_net": -0.0049,
        "profit_factor": 1.16,
        "cost_share_of_abs_gross": 0.21,
        "funding_share_of_abs_gross": 0.34,
    },
}

# Real diagnostics.json shape: by_symbol/by_direction/by_exit_reason are TOP-LEVEL
# group maps; economic_slices is nested. No "slices"/"by_month"/"by_hour".
_REAL_DIAGNOSTICS = {
    "strategy_id": "crypto_perp_funding_crowding_reversal",
    "artifact_profile": "diagnostic",
    "trade_count": 142,
    "by_symbol": {
        "BTC-PERP": {"count": 70, "gross": 0.9, "funding": 0.1, "cost": -0.2, "net": 0.8},
        "ETH-PERP": {"count": 72, "gross": 0.6, "funding": 0.05, "cost": -0.18, "net": 0.47},
    },
    "by_direction": {
        "long": {"count": 80, "gross": 0.8, "funding": 0.09, "cost": -0.2, "net": 0.69},
        "short": {"count": 62, "gross": 0.7, "funding": 0.06, "cost": -0.18, "net": 0.58},
    },
    "by_exit_reason": {
        "max_hold": {"count": 100, "gross": 1.0, "funding": 0.12, "cost": -0.3, "net": 0.82},
        "signal_flip": {"count": 42, "gross": 0.5, "funding": 0.03, "cost": -0.08, "net": 0.45},
    },
    "economic_slices": {
        "schema_version": "quant_strategies.runner.economic_slices/v1",
        "basis": "engine_trade_ledger",
        "by_symbol": {
            "BTC-PERP": {"count": 70, "average_trade_net": 0.011, "hit_rate": 0.6, "net_sum": 0.8},
            "ETH-PERP": {"count": 72, "average_trade_net": 0.0065, "hit_rate": 0.55, "net_sum": 0.47},
        },
        "by_direction": {
            "long": {"count": 80, "average_trade_net": 0.0086},
            "short": {"count": 62, "average_trade_net": 0.0094},
        },
        "by_exit_reason": {
            "max_hold": {"count": 100, "average_trade_net": 0.0082},
            "signal_flip": {"count": 42, "average_trade_net": 0.0107},
        },
    },
}


def _write_real_artifacts(result_dir):
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "summary.json").write_text(json.dumps(_REAL_SUMMARY), encoding="utf-8")
    (result_dir / "diagnostics.json").write_text(json.dumps(_REAL_DIAGNOSTICS), encoding="utf-8")


def test_quick_run_reads_real_summary_and_diagnostics_schema(tmp_path, monkeypatch):
    """quick_run surfaces a NON-None coarse metric + populated by_symbol slices from the
    foundation's REAL artifact keys (average_trade_net; top-level by_symbol).

    Pre-fix this FAILS: _coarse_metric probed economic_metrics for net_return/total_return/
    mean_return/return_per_period (none exist ⇒ None) and _slices read diag["slices"] (no
    such key ⇒ empty by_symbol). Both must resolve against the schema the foundation emits.
    """
    result_dir = tmp_path / "results" / "harness_quick_f0"
    _write_real_artifacts(result_dir)

    # A minimal real-shaped run result: verified causality + result_dir pointing at the
    # artifacts above. (quick_run uses run_config, not run_evaluation.)
    class _Causality:
        verified = True

    class _Evidence:
        causality = _Causality()

    class _Outcome:
        failure_stage = None

    artifacts_dir = str(result_dir)

    class _Result:
        evidence = _Evidence()
        outcome = _Outcome()
        result_dir = artifacts_dir

        @property
        def succeeded(self):
            return True

    monkeypatch.setattr(fr_mod, "run_config", lambda *a, **k: _Result())

    gw = RealFoundationGateway(repo_root=tmp_path, workdir=tmp_path)
    out = gw.quick_run(_experiment(), _protocol(), FoldWindow("f0", "2024-01-01", "2024-06-30"))

    # Coarse after-costs plausibility number is the real average_trade_net (sign-meaningful).
    assert out.in_sample_metric is not None
    assert out.in_sample_metric == pytest.approx(0.00037)
    # trade_count comes off the same real economic_metrics block.
    assert out.trade_count == 142
    assert out.valid is True
    assert out.causal_ok is True
    # by_symbol slices are populated from the real diagnostics (the breadth/robustness leg).
    assert "by_symbol" in out.slices
    assert set(out.slices["by_symbol"]) == {"BTC-PERP", "ETH-PERP"}
    assert out.slices["by_symbol"]["BTC-PERP"]  # non-empty per-symbol scalars
    # The invented by_month/by_hour keys are gone; only real slice axes are present.
    assert "by_month" not in out.slices
    assert "by_hour" not in out.slices


# --------------------------------------------------------------------------- #
# Fix 5 — fill-price mapping is not lossy: a valid foundation fill ("open") must
# reach the written config, not be silently downgraded to "close".
# (Foundation FillModelConfig.price accepts open|close|quote.)
# --------------------------------------------------------------------------- #


def test_fill_block_preserves_open(tmp_path):
    proto = _protocol().model_copy(update={"fill_model": _protocol().fill_model.model_copy(update={"fill": "open"})})
    gw = RealFoundationGateway(repo_root=tmp_path, workdir=tmp_path)
    cfg = fr_mod.derive_foundation_config(proto, _experiment())
    block = gw._fill_block(cfg)
    # Pre-fix this is "close" (open collapsed); post-fix the valid "open" survives.
    assert block["price"] == "open"


def test_fill_block_passthrough_close_and_quote(tmp_path):
    gw = RealFoundationGateway(repo_root=tmp_path, workdir=tmp_path)
    for fill in ("close", "quote"):
        proto = _protocol().model_copy(
            update={"fill_model": _protocol().fill_model.model_copy(update={"fill": fill})}
        )
        cfg = fr_mod.derive_foundation_config(proto, _experiment())
        assert gw._fill_block(cfg)["price"] == fill


def test_fill_block_maps_harness_next_bar_open_alias(tmp_path):
    # The harness vocabulary includes "next_bar_open" (FillModel docstring); the foundation
    # expresses the next-bar timing via entry_lag_bars and only accepts open|close|quote, so
    # the alias maps to the "open" price reference rather than the foundation rejecting it.
    proto = _protocol().model_copy(
        update={"fill_model": _protocol().fill_model.model_copy(update={"fill": "next_bar_open"})}
    )
    gw = RealFoundationGateway(repo_root=tmp_path, workdir=tmp_path)
    cfg = fr_mod.derive_foundation_config(proto, _experiment())
    assert gw._fill_block(cfg)["price"] == "open"


def test_fill_block_rejects_genuinely_unsupported_fill(tmp_path):
    proto = _protocol().model_copy(
        update={"fill_model": _protocol().fill_model.model_copy(update={"fill": "perfect"})}
    )
    gw = RealFoundationGateway(repo_root=tmp_path, workdir=tmp_path)
    cfg = fr_mod.derive_foundation_config(proto, _experiment())
    with pytest.raises(ValueError, match="fill"):
        gw._fill_block(cfg)


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


# --------------------------------------------------------------------------- #
# RealFactorPanelProvider — the data-backed factor panel (FR-C3 wiring).
#
# Unit: the empty-frame path fails closed (returns {}), so the judgment-layer guard bounces an
# unwired/empty panel rather than scoring raw returns. Data-gated: a real build over the live DB
# yields a covering {market, funding_carry} panel aligned to the return timestamps.
# --------------------------------------------------------------------------- #


def _fold_returns(n: int = 48, start: str = "2024-07-01"):
    from harness.foundation import FoldReturns

    ts = (np.arange(n, dtype="timedelta64[h]") + np.datetime64(start)).astype("datetime64[ns]")
    return FoldReturns(
        timestamps=ts, values=np.zeros(n, dtype=np.float64), periods_per_year=8760.0
    )


def test_real_factor_panel_provider_empty_frame_fails_closed(monkeypatch):
    """No benchmark rows for the window ⇒ the provider returns an EMPTY panel (it never fabricates
    a synthetic factor). The judgment layer then fails closed — this is the seam half of AC-9/G2.

    An injected engine + a stubbed loader returning an empty frame exercise the path with no DB."""
    import quant_data.loader as ql

    monkeypatch.setattr(ql, "load_crypto_perp_bars_with_funding", lambda *a, **k: __import__("polars").DataFrame(
        {"timestamp": [], "close": [], "funding_rate": []}
    ))
    provider = RealFactorPanelProvider(_protocol(), engine=object())  # injected engine, never queried
    panel = provider(FoldWindow("f0", "2024-07-01", "2024-08-31"), _fold_returns())
    assert panel == {}  # empty ⇒ no coverage ⇒ judgment layer fails closed


def test_real_factor_panel_provider_builds_covering_panel(monkeypatch):
    """With benchmark bars+funding, the provider returns a COVERING {market, funding_carry} panel,
    each column aligned 1:1 to the strategy's return timestamps. Stubbed loader (no DB)."""
    import polars as pl

    import quant_data.loader as ql

    n = 48
    base = np.datetime64("2024-07-01")
    bench_ts = [(base + np.timedelta64(i, "h")).astype("datetime64[us]").item() for i in range(n)]
    closes = list(100.0 + np.arange(n, dtype=np.float64))  # monotone ⇒ small positive market returns
    # A genuinely-varying funding rate (a real funding column is never identically constant); the
    # provider only emits a column that is USABLE (non-degenerate) for neutralization (AC-9/G2).
    fundings = list(0.0001 + 1e-5 * np.sin(np.arange(n, dtype=np.float64)))

    def fake_loader(engine, symbol, start, end, **kw):  # noqa: ARG001
        return pl.DataFrame({"timestamp": bench_ts, "close": closes, "funding_rate": fundings}).with_columns(
            pl.col("timestamp").cast(pl.Datetime("us", "UTC"))
        )

    monkeypatch.setattr(ql, "load_crypto_perp_bars_with_funding", fake_loader)
    provider = RealFactorPanelProvider(_protocol(), engine=object())
    returns = _fold_returns(n=n)
    panel = provider.panel_for(FoldWindow("f0", "2024-07-01", "2024-08-31"), returns)

    assert set(panel) == {"market", "funding_carry"}
    assert panel["market"].shape[0] == n and panel["funding_carry"].shape[0] == n
    assert panel["market"].dtype == np.float64
    # The funding_carry column carries the (forward-filled, genuinely-varying) funding rate.
    assert np.allclose(panel["funding_carry"], fundings)
    # Both columns are non-degenerate (the close-to-close market return and the varying funding).
    assert np.any(panel["market"] != 0.0)
    from harness.objective import factors

    assert factors.column_is_usable(panel["market"]) and factors.column_is_usable(panel["funding_carry"])


def test_real_factor_panel_provider_flat_close_omits_degenerate_market(monkeypatch):
    """A FLAT-close benchmark window yields an all-zero ``market`` column (pct_change of a constant
    is 0). The provider must NOT emit that fake-covering degenerate column — it OMITS ``market`` so
    the panel does NOT cover the requirement and the judgment layer fails closed at the source.

    Pre-fix the provider returned ``{market: all-zeros, funding_carry: ...}`` (a present-but-
    degenerate column that passed the presence-only gate and neutralized nothing). Stubbed loader,
    no DB."""
    import polars as pl

    import quant_data.loader as ql

    n = 48
    base = np.datetime64("2024-07-01")
    bench_ts = [(base + np.timedelta64(i, "h")).astype("datetime64[us]").item() for i in range(n)]
    flat_closes = list(100.0 * np.ones(n, dtype=np.float64))  # FLAT ⇒ market return ≡ 0
    fundings = list(0.0001 * np.ones(n, dtype=np.float64))

    def fake_loader(engine, symbol, start, end, **kw):  # noqa: ARG001
        return pl.DataFrame({"timestamp": bench_ts, "close": flat_closes, "funding_rate": fundings}).with_columns(
            pl.col("timestamp").cast(pl.Datetime("us", "UTC"))
        )

    monkeypatch.setattr(ql, "load_crypto_perp_bars_with_funding", fake_loader)
    provider = RealFactorPanelProvider(_protocol(), engine=object())
    panel = provider.panel_for(FoldWindow("f0", "2024-07-01", "2024-08-31"), _fold_returns(n=n))

    # The degenerate market column is OMITTED ⇒ the panel does not cover {market, funding_carry}.
    assert "market" not in panel, (
        "provider emitted a degenerate (all-zero) market column from a flat-close window — "
        "it must omit it so the judgment-layer gate fails closed"
    )
    # funding_carry is still a genuine column here, but coverage of the REQUIRED set is broken,
    # which is what the judgment gate keys on (panel_covers → False).
    from harness.objective import factors

    assert not factors.panel_covers(panel, ("market", "funding_carry"))


def test_real_factor_panel_provider_single_bar_omits_degenerate_market(monkeypatch):
    """A SINGLE-BAR benchmark frame cannot produce a non-degenerate close-to-close return series
    (one bar ⇒ the only market value is the fill-null 0). The provider must OMIT ``market`` rather
    than emit a fake-covering all-zero column. Stubbed loader, no DB."""
    import polars as pl

    import quant_data.loader as ql

    n = 48
    base = np.datetime64("2024-07-01")
    one_ts = [(base).astype("datetime64[us]").item()]

    def fake_loader(engine, symbol, start, end, **kw):  # noqa: ARG001
        return pl.DataFrame({"timestamp": one_ts, "close": [100.0], "funding_rate": [0.0]}).with_columns(
            pl.col("timestamp").cast(pl.Datetime("us", "UTC"))
        )

    monkeypatch.setattr(ql, "load_crypto_perp_bars_with_funding", fake_loader)
    provider = RealFactorPanelProvider(_protocol(), engine=object())
    panel = provider.panel_for(FoldWindow("f0", "2024-07-01", "2024-08-31"), _fold_returns(n=n))

    assert "market" not in panel, (
        "provider emitted a degenerate market column from a single-bar benchmark frame"
    )
    from harness.objective import factors

    assert not factors.panel_covers(panel, ("market", "funding_carry"))


def _factor_panel_db_available() -> bool:
    """True iff the live DB can serve benchmark bars+funding (else skip the real smoke)."""
    try:
        import datetime as dt

        from quant_data.loader import load_crypto_perp_bars_with_funding

        provider = RealFactorPanelProvider(_protocol())
        df = load_crypto_perp_bars_with_funding(
            provider._get_engine(), "BTC-PERP", dt.date(2023, 6, 1), dt.date(2023, 6, 3)
        )
        return not df.is_empty()
    except Exception:
        return False


@pytest.mark.skipif(
    not _factor_panel_db_available(),
    reason="live quant_data DB unreachable (no DB credentials) — real factor-panel smoke skipped",
)
def test_real_factor_panel_provider_real_build_is_covering():
    """End-to-end (data-gated): a real panel build over the live DB covers {market, funding_carry}
    aligned to a synthetic return series. Correctness of the live build is exercised only here."""
    provider = RealFactorPanelProvider(_protocol())
    returns = _fold_returns(n=72, start="2023-06-01")
    panel = provider.panel_for(FoldWindow("real", "2023-06-01", "2023-06-04"), returns)
    assert {"market", "funding_carry"} <= set(panel)
    assert panel["market"].shape[0] == returns.timestamps.shape[0]
