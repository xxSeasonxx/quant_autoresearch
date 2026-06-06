"""RealFoundationGateway — the SINGLE sanctioned ``quant_strategies`` boundary crosser.

Every other module under ``harness/`` is pure of ``quant_strategies`` (Dependency Inversion,
FR-J1, AC-10); this module is the one explicit adapter that imports the engine and adapts its
public surfaces to the ``FoundationGateway`` seam types. The boundary test
(``tests/harness/test_foundation_seam.py``) asserts exactly that: judgment modules clean,
this module the only importer.

Call sequence (per the P0 consumer contract,
``quant_strategies/docs/consumer/usage-guide.md`` "Per-fold OOS returns in-process"):

  evaluate(experiment, protocol, window):
    1. derive_foundation_config(protocol, experiment)  — the mechanical wall (FR-H3) supplies
       cost/fill/tiers; params populate only strategy params.
    2. write a SINGLE-window evaluation.toml (one [[windows]] = the fold span) with ONE custom
       costs-on [[scenarios]] (id = scenario_id) + a stressed scenario, into the strategy's
       directory with a sibling relative strategy_path (the foundation requires strategy_path
       to resolve inside the config dir).
    3. result = run_evaluation(config_path, repo_root=...) -> EvaluationRunResult.
    4. result.succeeded -> FoldEvalResult.succeeded; result.causal_replay_passed -> causal_ok.
    5. series = result.returns_for(window_id, scenario_id) -> FoldReturns(...).
    6. m = result.metrics_for(window_id, scenario_id) -> sharpe/sortino/calmar/max_drawdown/
       trade_count/worst_period_return; provenance = dict(result.provenance).

Per-symbol returns: the foundation runs a single grouped cash-shared portfolio, so
``FoldReturnSeries.per_symbol`` is ALWAYS None. To populate ``FoldReturns.by_symbol`` for the
concentration / effective-breadth gates + cross-asset holdout, the adapter issues SEPARATE
single-symbol evaluate calls (one per symbol in the universe) and assembles the legs. The
harness owns this orchestration; the foundation is never asked to compute per-symbol paths.

pandas, if any, lives ONLY here. (numpy arrays come straight off the typed accessor.)
"""

from __future__ import annotations

import datetime as _dt
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import tomlkit

from harness.foundation import (
    FoldEvalResult,
    FoldReturns,
    QuickRunResult,
)
from harness.protocol import (
    Experiment,
    Protocol,
    derive_foundation_config,
)

# The ONE permitted engine import in the entire harness package (Dependency Inversion seam).
from quant_strategies.evaluation import run_evaluation
from quant_strategies.runner import run_config

# The custom costs-on scenario id; the foundation resolves the full id to
# f"{window_id}/{_SCENARIO_ID}" (ONE unambiguous scenario per fold). The cost-stress
# *evidence* is sourced by the orchestrator via a second evaluate under a stressed-cost
# Protocol (keeping the FoundationGateway seam single-series and unchanged), so the adapter
# config carries exactly one scenario — whatever cost the passed Protocol specifies.
_SCENARIO_ID = "harness_costs_on"


@dataclass(frozen=True)
class FoldWindow:
    """A fold's calendar span + the id the foundation tags its series with.

    ``window_id`` is the foundation ``[[windows]].id``; the harness derives it from the
    walk-forward fold index + the fold's calendar bounds.
    """

    window_id: str
    start: str  # ISO date
    end: str  # ISO date


class RealFoundationGateway:
    """A real ``FoundationGateway`` over ``quant_strategies`` (the only engine importer).

    Parameters
    ----------
    repo_root:
        The directory the foundation resolves config paths against and where the temp
        per-fold config is written. MUST be an ancestor of the strategy file (the foundation
        requires ``strategy_path`` to resolve inside the config directory).
    workdir:
        Optional directory for the generated per-fold configs (defaults to a temp dir under
        ``repo_root`` so the sibling relative ``strategy_path`` resolves).
    """

    def __init__(self, repo_root: str | Path, *, workdir: str | Path | None = None) -> None:
        self._repo_root = Path(repo_root).resolve()
        self._workdir = Path(workdir).resolve() if workdir is not None else self._repo_root

    # ------------------------------------------------------------------ #
    # quick_run (Train) — Tier-0 causal diagnostic + coarse band.
    # ------------------------------------------------------------------ #

    def quick_run(self, experiment: Experiment, protocol: Protocol, window: FoldWindow) -> QuickRunResult:
        cfg = derive_foundation_config(protocol, experiment)
        config_path = self._write_quick_config(cfg, protocol, window)
        result = run_config(str(config_path), repo_root=self._repo_root)
        causal_ok = bool(getattr(result.evidence.causality, "verified", False))
        metric = self._coarse_metric(result)
        return QuickRunResult(
            valid=bool(result.succeeded),
            causal_ok=causal_ok,
            in_sample_metric=metric,
            trade_count=self._trade_count(result),
            slices=self._slices(result),
            failure_stage=None if result.succeeded else getattr(result.outcome, "failure_stage", "unknown"),
        )

    # ------------------------------------------------------------------ #
    # evaluate (one Selection fold or the Lockbox) — one evaluate per fold (FR-J2).
    # ------------------------------------------------------------------ #

    def evaluate(self, experiment: Experiment, protocol: Protocol, window: FoldWindow) -> FoldEvalResult:
        cfg = derive_foundation_config(protocol, experiment)
        scenario_id = f"{window.window_id}/{_SCENARIO_ID}"

        # Grouped portfolio evaluate (the ranking series + scalars).
        config_path = self._write_eval_config(cfg, protocol, window, symbols=cfg.symbols)
        result = run_evaluation(str(config_path), repo_root=self._repo_root)

        if not result.succeeded:
            return FoldEvalResult(
                succeeded=False,
                causal_ok=bool(result.causal_replay_passed) if result.causal_replay_passed is not None else False,
                returns=None,
                sharpe=None,
                sortino=None,
                calmar=None,
                max_drawdown=None,
                trade_count=0,
                worst_period_return=None,
                provenance=dict(result.provenance),
                failure_stage=result.failure_stage,
            )

        series = result.returns_for(window.window_id, scenario_id)
        metrics = result.metrics_for(window.window_id, scenario_id)
        if series is None or metrics is None:
            # Completed run but the requested scenario series is missing — treat as failure
            # rather than fabricate a series.
            return FoldEvalResult(
                succeeded=False,
                causal_ok=bool(result.causal_replay_passed),
                returns=None, sharpe=None, sortino=None, calmar=None, max_drawdown=None,
                trade_count=0, worst_period_return=None,
                provenance=dict(result.provenance),
                failure_stage="missing_scenario_series",
            )

        by_symbol = self._assemble_by_symbol(experiment, protocol, window, cfg.symbols)
        returns = FoldReturns(
            timestamps=np.asarray(series.timestamps),
            values=np.asarray(series.values, dtype=np.float64),
            periods_per_year=float(series.periods_per_year),
            by_symbol=by_symbol,
        )
        return FoldEvalResult(
            succeeded=True,
            causal_ok=bool(result.causal_replay_passed),
            returns=returns,
            sharpe=metrics.sharpe,
            sortino=metrics.sortino,
            calmar=metrics.calmar,
            max_drawdown=metrics.max_drawdown,
            trade_count=int(metrics.trade_count) if metrics.trade_count is not None else 0,
            worst_period_return=metrics.worst_period_return,
            provenance=dict(result.provenance),
            failure_stage=None,
        )

    # ------------------------------------------------------------------ #
    # Per-symbol assembly (separate single-symbol evaluate calls).
    # ------------------------------------------------------------------ #

    def _assemble_by_symbol(
        self,
        experiment: Experiment,
        protocol: Protocol,
        window: FoldWindow,
        symbols: tuple[str, ...],
    ) -> Mapping[str, FoldReturns] | None:
        """Build per-symbol legs from SEPARATE single-symbol evaluate calls (the foundation
        exposes no per-symbol path on its grouped series). Returns None for a single-symbol
        universe (no decomposition to make) — the concentration gate already treats a missing
        decomposition as fully concentrated.
        """
        if len(symbols) < 2:
            return None
        cfg = derive_foundation_config(protocol, experiment)
        scenario_id = f"{window.window_id}/{_SCENARIO_ID}"
        legs: dict[str, FoldReturns] = {}
        for sym in symbols:
            config_path = self._write_eval_config(cfg, protocol, window, symbols=(sym,), tag=sym)
            r = run_evaluation(str(config_path), repo_root=self._repo_root)
            if not r.succeeded:
                continue
            s = r.returns_for(window.window_id, scenario_id)
            if s is None:
                continue
            legs[sym] = FoldReturns(
                timestamps=np.asarray(s.timestamps),
                values=np.asarray(s.values, dtype=np.float64),
                periods_per_year=float(s.periods_per_year),
            )
        return legs or None

    # ------------------------------------------------------------------ #
    # Config writers (the mechanical wall already applied via cfg).
    # ------------------------------------------------------------------ #

    def _strategy_rel(self, cfg) -> str:
        """Strategy path relative to the workdir (sibling resolution requirement)."""
        strat = (self._repo_root / cfg.strategy_path).resolve()
        try:
            return strat.relative_to(self._workdir.resolve()).as_posix()
        except ValueError:
            # Fall back to the absolute path inside the repo root; the foundation accepts a
            # path that resolves inside the config directory (the repo root).
            return str(strat)

    def _data_block(self, cfg, symbols: tuple[str, ...]) -> dict[str, Any]:
        source = cfg.data_tiers.source
        block: dict[str, Any] = {"kind": source.kind, "symbols": list(symbols)}
        if source.dataset is not None:
            block["dataset"] = source.dataset
        return block

    def _cost_block(self, cost) -> dict[str, float]:
        # Map the harness CostModel to the foundation's per-side keys (taker as the per-side
        # fee; slippage as per-side slippage). maker/taker split collapses to taker for the
        # single grouped path; the wall guarantees these come from the Protocol, not params.
        return {"fee_bps_per_side": float(cost.taker_bps), "slippage_bps_per_side": float(cost.slippage_bps)}

    # Foundation FillModelConfig.price is Literal["open", "close", "quote"]; the next-bar
    # timing is carried by entry_lag_bars, not the price label. The harness fill vocabulary
    # adds the "next_bar_open" alias (FillModel docstring) for the same open reference.
    _FILL_PRICES = ("open", "close", "quote")

    def _fill_price(self, fill: str) -> str:
        """Map a harness fill label to a valid foundation price (open|close|quote).

        Passes the three foundation prices through unchanged (so a valid ``open`` is no longer
        silently downgraded to ``close``); resolves the ``next_bar_open`` harness alias to the
        ``open`` reference; raises on a genuinely unsupported value rather than masking it.
        """
        if fill in self._FILL_PRICES:
            return fill
        if fill == "next_bar_open":
            return "open"
        raise ValueError(
            f"unsupported fill {fill!r}: foundation accepts {self._FILL_PRICES} "
            "(harness alias 'next_bar_open' maps to 'open')"
        )

    def _fill_block(self, cfg) -> dict[str, Any]:
        source = cfg.data_tiers.source
        return {
            "price": self._fill_price(cfg.fill_model.fill),
            "entry_lag_bars": int(source.entry_lag_bars),
            "exit_lag_bars": int(source.exit_lag_bars),
        }

    def _write_eval_config(
        self, cfg, protocol: Protocol, window: FoldWindow, *, symbols: tuple[str, ...], tag: str = ""
    ) -> Path:
        # Costs come SOLELY from the (possibly stressed) Protocol via cfg — the mechanical
        # wall (FR-H3): params never touch cost/fill/tiers.
        cost = self._cost_block(protocol.cost_model)
        fill = self._fill_block(cfg)
        payload: dict[str, Any] = {
            "strategy_path": self._strategy_rel(cfg),
            "strategy_id": Path(cfg.strategy_path).stem,
            "windows": [{"id": window.window_id, "start": window.start, "end": window.end}],
            "data": self._data_block(cfg, symbols),
            "params": dict(cfg.strategy_params),
            "fill_model": fill,
            "cost_model": cost,
            "metrics": {
                "annualization_periods_per_year": int(protocol.annualization.periods_per_year),
                "min_annualized_samples": 20,
            },
            "scenarios": [
                {"id": _SCENARIO_ID, "required": True, "cost_model": cost, "fill_model": fill},
            ],
            "output": {"results_dir": f"evaluation_results/harness_{window.window_id}{('_' + tag) if tag else ''}"},
        }
        return self._dump(payload, prefix=f"harness_eval_{window.window_id}{('_' + tag) if tag else ''}_")

    def _write_quick_config(self, cfg, protocol: Protocol, window: FoldWindow) -> Path:
        data = self._data_block(cfg, cfg.symbols)
        data["start"] = window.start
        data["end"] = window.end
        payload: dict[str, Any] = {
            "strategy_path": self._strategy_rel(cfg),
            "strategy_id": Path(cfg.strategy_path).stem,
            "data": data,
            "params": dict(cfg.strategy_params),
            "fill_model": self._fill_block(cfg),
            "cost_model": self._cost_block(protocol.cost_model),
            "output": {"results_dir": f"results/harness_quick_{window.window_id}", "artifact_profile": "diagnostic"},
        }
        return self._dump(payload, prefix=f"harness_quick_{window.window_id}_")

    def _dump(self, payload: dict[str, Any], *, prefix: str) -> Path:
        self._workdir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=prefix, suffix=".toml", dir=str(self._workdir))
        path = Path(name)
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(tomlkit.dumps(payload))
        return path

    # ------------------------------------------------------------------ #
    # Quick-run summary extraction (coarse band; deliberately tolerant).
    #
    # The typed RunResult does not surface economic_metrics directly; they live in the
    # documented `summary.json` artifact (and `diagnostics.json` for slices). Reading a JSON
    # SCALAR from the result_dir is the sanctioned path — distinct from the AC-10 prohibition,
    # which is scraping the per-fold OOS *return series* out of `tables/portfolio_path.parquet`
    # (those flow through `returns_for` on `evaluate`). Tolerant by design: a coarse Train band
    # is deliberately imprecise (open decision #3), so an absent/renamed key degrades to None
    # rather than failing the run.
    # ------------------------------------------------------------------ #

    def _summary(self, result) -> Mapping[str, Any]:
        d = getattr(result, "result_dir", None)
        if d is None:
            return {}
        path = Path(d) / "summary.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _coarse_metric(self, result) -> float | None:
        # ``average_trade_net`` is the foundation's after-costs, sign-meaningful per-trade
        # economic figure (``quant_strategies.runner.economic_metrics.summary_metrics``):
        # positive ⇒ an in-sample edge survives costs. That is exactly the COARSE plausibility
        # band the Train signal needs (open decision #3, "lean coarse") — not a composite.
        # Returns None only when the run genuinely produced no average (no trades / key absent).
        econ = self._summary(result).get("economic_metrics") or {}
        if isinstance(econ, Mapping):
            v = econ.get("average_trade_net")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
        return None

    def _trade_count(self, result) -> int:
        econ = self._summary(result).get("economic_metrics") or {}
        v = econ.get("trade_count") if isinstance(econ, Mapping) else None
        return int(v) if isinstance(v, (int, float)) else 0

    def _slices(self, result) -> Mapping[str, Mapping[str, float]]:
        # Cheap-robust slices come from the foundation's diagnostics.json, whose REAL slice
        # axes are the top-level group maps ``by_symbol`` / ``by_direction`` / ``by_exit_reason``
        # (``quant_strategies.runner.diagnostics.diagnostic_payload``) plus the per-group
        # economic summaries under nested ``economic_slices`` (which carry ``average_trade_net``
        # etc. per group, from ``economic_metrics.diagnostic_slices``). There is no ``slices``
        # wrapper and no ``by_month`` / ``by_hour`` axis in the foundation — those were invented.
        # ``by_symbol`` (the breadth / concentration leg cares about it) is sourced from the
        # economic_slices view when present so its values are sign-meaningful per-symbol scalars,
        # falling back to the top-level group map otherwise.
        empty: dict[str, dict[str, float]] = {"by_symbol": {}}
        d = getattr(result, "result_dir", None)
        if d is None:
            return empty
        path = Path(d) / "diagnostics.json"
        if not path.is_file():
            return empty
        try:
            diag = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return empty
        if not isinstance(diag, Mapping):
            return empty
        econ_slices = diag.get("economic_slices")
        econ_slices = econ_slices if isinstance(econ_slices, Mapping) else {}
        out: dict[str, Mapping[str, float]] = {}
        for axis in ("by_symbol", "by_direction", "by_exit_reason"):
            # Prefer the economic_slices view (sign-meaningful per-group scalars); fall back to
            # the top-level group map (count/gross/funding/cost/net) so the axis still populates.
            group = econ_slices.get(axis)
            if not isinstance(group, Mapping):
                group = diag.get(axis)
            if isinstance(group, Mapping):
                out[axis] = group
        out.setdefault("by_symbol", {})
        return out


# --------------------------------------------------------------------------- #
# RealFactorPanelProvider — the data-backed factor panel (FR-C3, the seam wiring).
#
# Builds the factor-return columns RES neutralizes against, for one fold window, from the
# foundation data (``quant_data``). This is the ONLY place the panel touches live data; the
# judgment layer consumes it as plain numpy columns through the ``FactorPanelProvider`` seam
# (orchestrator/lockbox), so it stays pure and testable with a fake.
#
# At minimum it supplies the two columns a crypto-perp campaign MUST neutralize (the Protocol's
# ``required_factors`` default): ``market`` (the benchmark/BTC-PERP close-to-close return — the
# BTC beta every alt co-moves with) and ``funding_carry`` (the perp funding rate — carry,
# regressed out, never additive alpha). Columns are aligned (as-of) to the strategy's per-bar
# return timestamps so the OLS in ``factors.residualize`` is well-posed.
#
# DB-GATED: the DB is unreachable in CI/this environment, so live correctness is exercised only
# by a skip-if-no-DB smoke (``tests/harness/test_foundation_real.py``). Safety does NOT depend on
# this running: when no panel covers the required factors the JUDGMENT layer fails closed
# (RES infeasible / Lockbox insufficient_evidence). This provider supplies the honest panel so a
# REAL campaign neutralizes beta; the fail-closed guard is the wall when it (or any provider)
# cannot.
# --------------------------------------------------------------------------- #


class RealFactorPanelProvider:
    """A ``FactorPanelProvider`` (callable seam) backed by ``quant_data``.

    Constructs ``{"market", "funding_carry"}`` factor-return columns for a fold window, aligned to
    the strategy's return-series timestamps. ``benchmark_symbol`` is the market-beta proxy (the
    canonical crypto market driver). The SQLAlchemy engine is created lazily so importing this
    module (or constructing the provider) never opens a DB connection.
    """

    def __init__(self, protocol: Protocol, *, benchmark_symbol: str = "BTC-PERP", engine: Any = None) -> None:
        self._protocol = protocol
        self._benchmark = benchmark_symbol
        self._engine = engine  # injected in tests; built lazily from quant_data otherwise

    def __call__(self, window, returns: FoldReturns) -> Mapping[str, np.ndarray]:
        """Build the factor panel for ``window`` aligned to ``returns`` (the seam call)."""
        return self.panel_for(window, returns)

    def _get_engine(self) -> Any:
        if self._engine is None:
            from quant_data.db import get_engine

            self._engine = get_engine()
        return self._engine

    def panel_for(self, window, returns: FoldReturns) -> Mapping[str, np.ndarray]:
        """Load the benchmark bars+funding over ``window`` and align market + funding_carry to the
        strategy's return timestamps. Returns numpy columns of the same length as ``returns``.

        Alignment is as-of (the last benchmark observation at or before each strategy bar): the
        benchmark return is the close-to-close return; the funding rate is forward-filled between
        funding events. polars (a ``quant_data`` dependency) lives only here, never in the core.
        """
        import polars as pl

        from quant_data.loader import load_crypto_perp_bars_with_funding

        n = int(np.asarray(returns.timestamps).shape[0])
        start = _dt.date.fromisoformat(window.start)
        end = _dt.date.fromisoformat(window.end)

        bars = load_crypto_perp_bars_with_funding(self._get_engine(), self._benchmark, start, end)
        if bars.is_empty():
            # No benchmark data for the window ⇒ no covering panel ⇒ the judgment layer fails
            # closed (we return an empty panel rather than fabricate a synthetic factor).
            return {}

        # Benchmark close-to-close return (the market beta proxy) + the funding-carry column.
        bench = (
            bars.select(["timestamp", "close", "funding_rate"])
            .sort("timestamp")
            .with_columns(
                pl.col("close").pct_change().alias("market"),
                pl.col("funding_rate").fill_null(strategy="forward").fill_null(0.0).alias("funding_carry"),
            )
            .with_columns(pl.col("market").fill_null(0.0))
            .select(["timestamp", "market", "funding_carry"])
        )

        # As-of align to the strategy's per-bar timestamps (datetime64[ns] → UTC microseconds).
        ts = pl.Series(
            "timestamp", np.asarray(returns.timestamps).astype("datetime64[us]")
        ).cast(pl.Datetime("us", "UTC"))
        strat = pl.DataFrame({"timestamp": ts}).sort("timestamp")
        aligned = strat.join_asof(bench, on="timestamp", strategy="backward").with_columns(
            pl.col("market").fill_null(0.0), pl.col("funding_carry").fill_null(0.0)
        )

        market = aligned.get_column("market").to_numpy().astype(np.float64)
        funding = aligned.get_column("funding_carry").to_numpy().astype(np.float64)
        if market.shape[0] != n or funding.shape[0] != n:
            # Alignment did not produce a 1:1 column ⇒ fail closed (no fabricated panel).
            return {}

        # Defense-in-depth (AC-9/G2): NEVER emit a degenerate column. A flat-or-single-bar benchmark
        # window makes ``market`` (pct_change) all-zero — a present-but-degenerate column would pass a
        # presence-only gate yet neutralize nothing, laundering raw beta as residual alpha. OMIT any
        # column that is not usable (all-zero / constant / non-finite) so the panel honestly does NOT
        # cover that factor and the judgment-layer gate fails closed at the source. The judgment gate
        # is the real guarantee; this just keeps the provider from emitting a fake-covering column.
        from harness.objective.factors import column_is_usable

        panel: dict[str, np.ndarray] = {}
        if column_is_usable(market):
            panel["market"] = market
        if column_is_usable(funding):
            panel["funding_carry"] = funding
        return panel
