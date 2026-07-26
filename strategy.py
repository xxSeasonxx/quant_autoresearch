"""Strategy: crypto_perp_tsmom_majors

Family A — per-symbol time-series momentum (trend following) applied independently to a
small a-priori set of the deepest crypto-perp majors (BTC/ETH/SOL), sized by the engine's
volatility target. The alpha lives in each name's own directional trend signal; the book
combines the per-name signals into one standing portfolio and book-level volatility
targeting is the operator's free service, not part of the edge, so the strategy emits a
clean signed shape per name and lets the frozen risk budget size the whole book. How NAV
is split across the active names is a strategy-owned allocation-shape lever, not a
separate alpha: `weighting` chooses equal (each name at most 1/N of NAV, so a fully-long
N-name book grosses to <= 1.0), inverse-volatility (risk parity across names), or
conviction (vol-adjusted trend strength); `top_n` optionally caps the active book to the
strongest-trending names. Every weighting redistributes within the same active-set gross,
so it reshapes the book without changing magnitude, which the vol target washes out anyway.
`gross_mode` is the one allocation lever that does change magnitude, and only its
breadth-conditional profile — how hard the book leans on the fraction of the universe voting:
`universe` is linear (an idle sleeve stays in cash), `active` is flat (full budget at any
breadth), `tilted` is quadratic (risk leans into cross-name agreement). A single global book
scale cannot wash that out, because it reallocates risk across time rather than resizing the
whole book.

Source / provenance:
Time-series momentum construction: Moskowitz, Ooi & Pedersen, "Time Series
Momentum", Journal of Financial Economics 104(2) 2012,
doi:10.1016/j.jfineco.2011.11.003
(https://www.sciencedirect.com/science/article/abs/pii/S0304405X11002613).
Crypto replication: Liu & Tsyvinski, "Risks and Returns of Cryptocurrency", Review
of Financial Studies 34(6) 2021, doi:10.1093/rfs/hhaa113 (daily/weekly time-series
momentum in BTC/ETH). "A Decade of Evidence of Trend Following in Cryptocurrencies"
(2020), arXiv:2009.12155 (multi-timescale sign blend). Grayscale Research, "The
Trend is Your Friend" (2023). Shortlist and Family-A specification:
internal_note docs/research/crypto_majors_btc_eth_sol_perp_strategies.md (Family A,
verified 2026-07-23) citing the sources above.

Market rationale:
Crypto perpetuals are retail-heavy, sentiment-driven, and weakly arbitraged, so an
instrument under-reacts to information and then over-reacts, producing positively
autocorrelated returns at weekly-to-quarterly horizons. Each symbol's own trailing
return therefore predicts the sign of its next-horizon return. The signal is
computed from a single name's own history, so it depends on no cross-section and
dodges the survivorship bias that inflates cross-sectional crypto claims.

Required observables:
Symbol, timezone-aware bar timestamp, available_at, and close for crypto-perp bars.
Funding is not read for the signal; the book runs under the financed data kind only
so a multi-day hold pays or collects realized funding honestly. With vol_scale on, the
decision also reads the symbol's own trailing daily closes to estimate recent realized
volatility. A row is used only when its available_at is at or before the emitted
decision_time.

Decision rule:
On a fixed UTC rebalance clock, for each symbol form the trailing return
r = close(formation_end) / close(formation_end - lookback_days) - 1, where
formation_end is skip_days before the rebalance (skip_days=0 uses the rebalance bar;
a positive skip excludes the reversal-prone most-recent move, a gap-momentum
formation). With trend_method="ma_cross" the reference denominator is instead the mean
daily close over the lookback window (a moving-average crossover) — a whole-path trend
robust to the two-endpoint noise of a point-to-point return. signal="sign" targets
+1 / -1 on the sign of r; signal="long_flat"
targets +1 / 0 (no shorts). With signal_band > 0 the sign decision carries a no-trade band
(hysteresis): a name takes the trend direction only when its formation return clears
+/-signal_band and holds its prior standing vote inside the band, so whipsaw round-trips
through zero collapse into holds — cutting turnover (and its capacity participation) without
slowing the formation horizon. With blend=true the per-horizon vote is averaged over a
fixed multi-timescale lookback set, giving a graded target in [-1, 1] from how many
horizons agree. When confirm_lookback_days > 0 the target is gated by a slow regime
trend measured over that horizon (same formation_end): a long survives only in a slow
uptrend and a short only in a slow downtrend, so the book stands flat when the fast
signal and the slow regime disagree — trading with the major trend and sitting out
whipsaw regimes rather than fighting them. When vol_scale is on **and weighting is equal**,
each entry's weight is scaled by min(1, ref_vol / recent_vol) using the symbol's own trailing
daily-return volatility over vol_lookback_days against a fixed a-priori reference, de-risking
entries made in high-volatility regimes; the size is set at entry and held until the trend vote
changes, so a drifting vol estimate does not churn the standing book. The lever is inert under
inverse_vol and conviction weighting, which already size from the same volatility estimate and
would otherwise apply it twice. Across names, the
active book is those with a non-zero vote, optionally capped by top_n to the
strongest-trending names (ranked by vol-adjusted trend magnitude), and NAV is split across
them by the weighting mode within the gross that gross_mode sets from breadth (linear, so
idle sleeves sit in cash; flat, so gross holds at the full budget at any breadth; or
quadratic, leaning into cross-name agreement); the selection and cross-name weights are
recomputed only when
some name's trend vote changes and held otherwise, so drifting vol or trend strength does
not churn the standing book. Emit one signed
weight-of-NAV target per
symbol whenever it changes from the last emitted value (including a zero target to
flatten), so the standing book rebalances by netting. When position_smoothing > 1, the
emitted book steps only 1/position_smoothing of the way toward each newly desired target per
rebalance, spreading one position change across that many rebalance days so its turnover lands
in that many separate daily capacity windows (the cross-name weights are still fixed at the
vote change). When execution_bars > 1, each emitted step is additionally ramped across that
many consecutive one-minute bars (TWAP) so no single decision minute pins participation; every
step uses the same signal known at the rebalance, so it stays causal. The only exit is the
formation vote turning, emitted as an explicit zero target: the book carries no faster-horizon
exit and no declared price-path barrier, because every such device was falsified on clean Train
evidence — a shorter-horizon exit and a trailing barrier both sell into the short-horizon
reversals this edge is paid for holding through, a take-profit truncates the minority of large
continuing trends that carry the return, and a fixed stop leaves portfolio drawdown untouched
because that drawdown is a correlated cross-sectional move rather than an accumulation of
per-name losses from entry. Book volatility targeting and the leverage ceiling are the engine's
operator-frozen risk budget, not strategy knobs.

Assumptions:
Input bars are timezone-aware and ordered by causal availability through
available_at. The rebalance clock fires at UTC midnight every rebalance_days days;
each decision fires at the first real bar at or after the signal bar's available_at
plus decision_lag_minutes, so it is never look-ahead. Warmup happens inside the
decision window: a rebalance without enough lookback history simply emits no target.

Falsifier:
If net return after realistic costs and ADV/impact capacity is not positive across
the bounded lookbacks, or is not materially above a volatility-matched buy-and-hold
of the same symbol, or all return is concentrated in a single mega-trend window (for
example the 2020-21 bull) rather than pervasive across subwindows, reject the thesis
rather than adding filters or per-window exceptions.
"""

import math
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from quant_strategies.decisions import (
    InstrumentRef,
    ObservationRef,
    TargetDecision,
)

__all__ = ["generate_decisions", "validate_params"]

_STRATEGY_ID = "crypto_perp_tsmom_majors"
_SOURCE = "crypto_perp_1min_with_funding"
_REQUIRED_FIELDS = {"symbol", "timestamp", "available_at", "close"}
# Coarse, documented multi-timescale grid for the optional sign blend. Fixed by the
# research spec (a decade-of-trend-following ensemble), not a tuning surface.
_BLEND_LOOKBACKS: tuple[int, ...] = (20, 50, 100, 200)
# Reference annualized volatility for ex-ante vol scaling. A fixed a-priori anchor for a
# crypto major's long-run realized volatility (BTC ≈ 0.65 annualized), not a tuning
# surface. The engine renormalizes book scale globally, so this constant only sets where
# the gross cap binds — it de-risks periods whose recent vol runs above a major's norm.
_VOL_SCALE_REF_ANNUAL = 0.65
_VOL_MIN_RETURNS = 10
_PERIODS_PER_YEAR_DAILY = 365.0
_DEFAULT_PARAMS: dict[str, object] = {
    "lookback_days": 30,
    "signal": "sign",
    "blend": False,
    "skip_days": 0,
    "rebalance_days": 1,
    "decision_lag_minutes": 1,
    "confirm_lookback_days": 0,
    "vol_scale": False,
    "vol_lookback_days": 30,
    "trend_method": "return",
    "weighting": "equal",
    "gross_mode": "universe",
    "top_n": 0,
    "execution_bars": 1,
    "signal_band": 0.0,
    "position_smoothing": 1,
}
_MA_MIN_DAILY = 5


@dataclass(frozen=True)
class _BarRow:
    symbol: str
    timestamp: datetime
    available_at: datetime
    close: float


@dataclass(frozen=True)
class _SymbolRows:
    bars: tuple[_BarRow, ...]
    timestamps: tuple[datetime, ...]
    daily_bars: tuple[_BarRow, ...]
    daily_times: tuple[datetime, ...]


@dataclass(frozen=True)
class _Eval:
    """One symbol's evaluation at a rebalance: its trend vote, the timing/anchor bar,
    the bars its decision reads, the primary-horizon formation return (bps) for the
    trade tape, the ex-ante vol scale (1.0 unless vol_scale), and recent annualized
    volatility (``None`` during warmup) used by cross-name weighting and selection."""

    raw_target: float
    scale: float
    signal_row: _BarRow
    observation_bars: tuple[_BarRow, ...]
    formation_bps: float
    recent_vol: float | None


def validate_params(params: Mapping[str, object]) -> dict[str, object]:
    """Validate the bounded time-series-momentum parameters."""

    unknown = set(params) - set(_DEFAULT_PARAMS)
    if unknown:
        raise ValueError(f"unknown params: {sorted(unknown)}")

    merged = {**_DEFAULT_PARAMS, **dict(params)}
    return {
        "lookback_days": _positive_int(merged["lookback_days"], "lookback_days"),
        "signal": _signal(merged["signal"]),
        "blend": _bool_param(merged["blend"], "blend"),
        "skip_days": _non_negative_int(merged["skip_days"], "skip_days"),
        "rebalance_days": _positive_int(merged["rebalance_days"], "rebalance_days"),
        "decision_lag_minutes": _non_negative_int(
            merged["decision_lag_minutes"], "decision_lag_minutes"
        ),
        "confirm_lookback_days": _non_negative_int(
            merged["confirm_lookback_days"], "confirm_lookback_days"
        ),
        "vol_scale": _bool_param(merged["vol_scale"], "vol_scale"),
        "vol_lookback_days": _positive_int(
            merged["vol_lookback_days"], "vol_lookback_days"
        ),
        "trend_method": _trend_method(merged["trend_method"]),
        "weighting": _weighting(merged["weighting"]),
        "gross_mode": _gross_mode(merged["gross_mode"]),
        "top_n": _non_negative_int(merged["top_n"], "top_n"),
        "execution_bars": _positive_int(merged["execution_bars"], "execution_bars"),
        "signal_band": _non_negative_fraction(merged["signal_band"], "signal_band"),
        "position_smoothing": _positive_int(
            merged["position_smoothing"], "position_smoothing"
        ),
    }


def generate_decisions(
    bars: Sequence[Mapping[str, object]], params: Mapping[str, object]
) -> list[TargetDecision]:
    """Emit standing per-symbol time-series-momentum target decisions."""

    if not bars:
        return []
    validated = validate_params(params)
    rows_by_symbol = _rows_by_symbol(bars)
    if not rows_by_symbol:
        return []
    # Equal-weight the book across the whole eligible universe: each name carries at most
    # 1/N of NAV, so a fully-long N-name book grosses to <= 1.0 within the frozen budget.
    # Relative per-name weights are equal; the engine's vol target sets overall scale.
    n_universe = len(rows_by_symbol)

    blend = _param_bool(validated, "blend")
    lookback_days = _param_int(validated, "lookback_days")
    lookbacks = _BLEND_LOOKBACKS if blend else (lookback_days,)
    skip_days = _param_int(validated, "skip_days")
    rebalance_days = _param_int(validated, "rebalance_days")
    signal = _param_str(validated, "signal")
    lag = _param_int(validated, "decision_lag_minutes")
    confirm_lookback_days = _param_int(validated, "confirm_lookback_days")
    vol_scale = _param_bool(validated, "vol_scale")
    vol_lookback_days = _param_int(validated, "vol_lookback_days")
    trend_method = _param_str(validated, "trend_method")
    weighting = _param_str(validated, "weighting")
    gross_mode = _param_str(validated, "gross_mode")
    top_n = _param_int(validated, "top_n")
    execution_bars = _param_int(validated, "execution_bars")
    signal_band = _param_float(validated, "signal_band")
    position_smoothing = _param_int(validated, "position_smoothing")
    # Cross-name weighting and top_n selection both need each name's recent volatility;
    # compute it whenever a lever consumes it (and, as before, when vol_scale is on).
    need_vol = vol_scale or top_n > 0 or weighting in ("inverse_vol", "conviction")

    rebalance_times = _rebalance_times(rows_by_symbol, rebalance_days)
    last_vote: dict[str, float] = {}
    last_target: dict[str, float] = {}
    # Desired book per symbol, set (weights held) at each trend-vote change; the emitted
    # book ramps toward it over position_smoothing rebalances so a flip's turnover is
    # spread across that many daily capacity windows.
    desired_target: dict[str, float] = {}
    # Standing trend vote per symbol, updated every rebalance; only consumed by the
    # hysteresis band (signal_band > 0) to hold the prior vote inside the no-trade zone.
    standing_vote: dict[str, float] = {}
    decisions: list[TargetDecision] = []
    seen_keys: set[tuple[str, datetime]] = set()

    for signal_time in rebalance_times:
        evaluated: dict[str, _Eval] = {}
        for symbol in sorted(rows_by_symbol):
            result = _symbol_target(
                rows=rows_by_symbol[symbol],
                signal_time=signal_time,
                lookbacks=lookbacks,
                skip_days=skip_days,
                signal=signal,
                confirm_lookback_days=confirm_lookback_days,
                vol_scale=vol_scale,
                need_vol=need_vol,
                vol_lookback_days=vol_lookback_days,
                trend_method=trend_method,
                signal_band=signal_band,
                prev_vote=standing_vote.get(symbol, 0.0),
            )
            if result is not None:
                evaluated[symbol] = result
        if not evaluated:
            continue

        # Recompute the active book only when the raw trend-vote vector changes; between
        # changes the standing selection and cross-name weights hold, so drifting vol or
        # trend strength does not churn the book. Under equal weighting with vol_scale
        # off this reproduces the per-name "emit on own vote change" behavior exactly.
        votes = {symbol: ev.raw_target for symbol, ev in evaluated.items()}
        # Carry the standing vote forward every rebalance so the hysteresis hold has the
        # prior vote available even on rebalances that emit nothing.
        standing_vote.update(votes)
        # Recompute the desired book (with held cross-name weights) only on a vote change.
        if votes != last_vote:
            desired_target.update(
                _assign_targets(evaluated, weighting, gross_mode, top_n, n_universe)
            )
            last_vote = votes

        # Every rebalance, step the emitted book toward the desired book. With
        # position_smoothing=1 the step jumps straight to desired (so the book only moves
        # on a vote change — unchanged behavior); with >1 it covers 1/N of the remaining
        # gap per rebalance, spreading each flip's turnover across N daily windows.
        for symbol in sorted(evaluated):
            ev = evaluated[symbol]
            desired = desired_target.get(symbol, 0.0)
            previous = last_target.get(symbol, 0.0)
            if position_smoothing > 1:
                target = previous + (desired - previous) / position_smoothing
                if abs(desired - target) < 1e-4:
                    target = desired
            else:
                target = desired
            if _close(target, previous):
                continue
            # decision_time is a computed clock time — the signal bar's availability
            # plus the causal lag — not a bar looked up in ``rows``. Causal replay
            # truncates visible rows to ``available_at <= decision_time``, which drops
            # the decision bar itself (published one minute later), so a bar lookup
            # could not be reconstructed on the truncated prefix. Recomputing the clock
            # value from the (visible) signal bar reproduces identically. Every observed
            # close is available by decision_time; as_of_time is the signal bar's time.
            base_time = ev.signal_row.available_at + timedelta(minutes=lag)
            # Spread the target change linearly across ``execution_bars`` consecutive
            # one-minute bars (TWAP), so no single decision minute pins participation.
            # Each ramp step reads the same signal known at the rebalance, so every step
            # is causal; execution_bars=1 emits a single decision at base_time (unchanged).
            for step in range(1, execution_bars + 1):
                if step == execution_bars:
                    step_target = target
                else:
                    step_target = previous + (target - previous) * (step / execution_bars)
                decision_time = base_time + timedelta(minutes=step - 1)
                key = (symbol, decision_time)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                decisions.append(
                    TargetDecision(
                        strategy_id=_STRATEGY_ID,
                        instrument=InstrumentRef(kind="crypto_perp", symbol=symbol),
                        decision_time=decision_time,
                        as_of_time=ev.signal_row.timestamp,
                        target=step_target,
                        observations=_observations(symbol, ev.observation_bars),
                        metadata={
                            "signal_family": _STRATEGY_ID,
                            "signal": signal,
                            "blend": blend,
                            "weighting": weighting,
                            "formation_return_bps": ev.formation_bps,
                        },
                    )
                )
            last_target[symbol] = target

    return sorted(
        decisions,
        key=lambda decision: (decision.decision_time, decision.instrument.symbol),
    )


def _assign_targets(
    evaluated: Mapping[str, _Eval],
    weighting: str,
    gross_mode: str,
    top_n: int,
    n_universe: int,
) -> dict[str, float]:
    """Signed weight-of-NAV target per symbol for one rebalance.

    The active book is the non-zero votes, optionally capped by ``top_n`` to the
    strongest (vol-adjusted trend magnitude) names. ``equal`` weighting gives each
    active name an equal share, ``inverse_vol`` (risk parity) and ``conviction``
    (vol-adjusted trend strength) redistribute NAV within the same active-set gross,
    so weighting reshapes the book without changing its magnitude. A degenerate metric
    total (warmup with no volatility yet) falls back to equal shares.

    ``gross_mode`` sets how the book's gross responds to breadth — the fraction of the
    universe voting — which is the only thing here that varies risk across time rather
    than across names. ``universe`` is linear in breadth: an idle sleeve stays in cash, so
    one name voting deploys a third of the budget. ``active`` is flat: gross holds at the
    full budget at any breadth. ``tilted`` is quadratic, treating breadth as conviction in
    a common trend, so risk leans into cross-name agreement and backs further out of
    single-name signals.
    """

    targets = {symbol: 0.0 for symbol in evaluated}
    active = {symbol: ev for symbol, ev in evaluated.items() if ev.raw_target != 0.0}
    if not active:
        return targets
    if 0 < top_n < len(active):
        ranked = sorted(active, key=lambda s: _rank_strength(active[s]), reverse=True)
        active = {symbol: active[symbol] for symbol in ranked[:top_n]}

    active_count = len(active)
    breadth_share = active_count / n_universe
    if gross_mode == "active":
        gross = 1.0
    elif gross_mode == "tilted":
        gross = breadth_share**2
    else:
        gross = breadth_share

    if weighting == "equal":
        for symbol, ev in active.items():
            targets[symbol] = ev.raw_target * ev.scale * gross / active_count
        return targets
    metrics = {symbol: _weight_metric(active[symbol], weighting) for symbol in active}
    total = sum(metrics.values())
    if total <= 0.0:
        share = 1.0 / len(active)
        for symbol, ev in active.items():
            targets[symbol] = _sign(ev.raw_target) * share * gross
        return targets
    for symbol, ev in active.items():
        targets[symbol] = _sign(ev.raw_target) * (metrics[symbol] / total) * gross
    return targets


def _weight_metric(ev: _Eval, weighting: str) -> float:
    """Non-negative cross-name weight metric for a shaped weighting mode.

    ``inverse_vol`` weights by ``1 / recent_vol`` (risk parity across names).
    ``conviction`` weights by vol-adjusted trend *strength* — the magnitude of the
    formation return per unit volatility, matching the metric ``top_n`` ranks on, so a
    strong downtrend counts as strongly as a strong uptrend and a two-sided book keeps
    its shorts. The sign is applied by the caller. Both return ``0`` when volatility is
    unavailable (warmup), which the caller resolves as an equal-share fallback.
    """

    if ev.recent_vol is None or ev.recent_vol <= 0.0:
        return 0.0
    if weighting == "inverse_vol":
        return 1.0 / ev.recent_vol
    return abs(ev.formation_bps / 10_000.0) / ev.recent_vol


def _rank_strength(ev: _Eval) -> float:
    """Vol-adjusted trend magnitude for top_n selection; raw magnitude if vol is unknown."""

    if ev.recent_vol is not None and ev.recent_vol > 0.0:
        return abs(ev.formation_bps) / ev.recent_vol
    return abs(ev.formation_bps)


def _sign(value: float) -> float:
    return 1.0 if value > 0.0 else -1.0


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9


def _symbol_target(
    *,
    rows: _SymbolRows,
    signal_time: datetime,
    lookbacks: tuple[int, ...],
    skip_days: int,
    signal: str,
    confirm_lookback_days: int,
    vol_scale: bool,
    need_vol: bool,
    vol_lookback_days: int,
    trend_method: str,
    signal_band: float,
    prev_vote: float,
) -> _Eval | None:
    """Signed trend evaluation for one symbol at a rebalance time, or ``None``.

    ``None`` means the symbol lacks enough formation history at this rebalance for
    the requested lookback(s), so no decision is emitted (warmup). Otherwise returns
    an ``_Eval`` with the signed vote, the timing/anchor bar, the bars whose closes
    the decision reads, the primary-horizon formation return in bps for the trade
    tape, the ex-ante vol scale, and recent annualized volatility. The vote averages
    one ``sign`` (or ``long_flat``) vote per lookback, so a single lookback yields
    +/-1 (or +1/0) and a blend yields a graded value in [-1, 1].
    """

    signal_index = bisect_right(rows.timestamps, signal_time) - 1
    if signal_index < 0:
        return None
    signal_row = rows.bars[signal_index]

    formation_end_time = signal_time - timedelta(days=skip_days)
    formation_end_index = bisect_right(rows.timestamps, formation_end_time) - 1
    if formation_end_index < 0:
        return None
    formation_end_row = rows.bars[formation_end_index]

    votes: list[float] = []
    observation_bars: list[_BarRow] = [formation_end_row]
    primary_formation_return = 0.0
    for position, lookback_days in enumerate(lookbacks):
        lookback_time = formation_end_time - timedelta(days=lookback_days)
        if trend_method == "ma_cross":
            # Whole-path trend: current close vs the mean daily close over the window,
            # robust to the two-endpoint noise of a point-to-point return.
            sma = _daily_sma(rows, lookback_time, formation_end_time)
            if sma is None:
                return None
            reference, sma_bars = sma
            observation_bars.extend(sma_bars)
        else:
            lookback_index = bisect_right(rows.timestamps, lookback_time) - 1
            if lookback_index < 0 or lookback_index == formation_end_index:
                return None
            lookback_row = rows.bars[lookback_index]
            reference = lookback_row.close
            observation_bars.append(lookback_row)
        formation_return = formation_end_row.close / reference - 1.0
        if position == 0:
            primary_formation_return = formation_return
        votes.append(_vote(formation_return, signal))

    target = sum(votes) / len(votes)

    # Hysteresis: replace the raw vote with a banded vote that holds the prior standing
    # vote inside the no-trade zone, so whipsaw round-trips through zero become holds.
    # Applied to the primary-horizon formation return (band is a single-horizon device).
    if signal_band > 0.0:
        target = _hysteresis_vote(primary_formation_return, signal, signal_band, prev_vote)

    if confirm_lookback_days > 0:
        confirm_time = formation_end_time - timedelta(days=confirm_lookback_days)
        confirm_index = bisect_right(rows.timestamps, confirm_time) - 1
        if confirm_index < 0 or confirm_index == formation_end_index:
            return None
        confirm_row = rows.bars[confirm_index]
        confirm_return = formation_end_row.close / confirm_row.close - 1.0
        observation_bars.append(confirm_row)
        target = _confirm_gate(target, confirm_return)

    scale = 1.0
    recent_vol: float | None = None
    if need_vol:
        estimate = _recent_annualized_vol(rows, formation_end_time, vol_lookback_days)
        if estimate is not None:
            annualized_vol, vol_bars = estimate
            observation_bars.extend(vol_bars)
            recent_vol = annualized_vol
            if vol_scale and annualized_vol > 0.0:
                scale = min(1.0, _VOL_SCALE_REF_ANNUAL / annualized_vol)

    return _Eval(
        raw_target=target,
        scale=scale,
        signal_row=signal_row,
        observation_bars=tuple(observation_bars),
        formation_bps=primary_formation_return * 10_000.0,
        recent_vol=recent_vol,
    )


def _daily_sma(
    rows: _SymbolRows, start_time: datetime, end_time: datetime
) -> tuple[float, tuple[_BarRow, ...]] | None:
    """Mean of UTC-midnight daily closes over ``(start_time, end_time]``.

    Returns ``None`` when fewer than ``_MA_MIN_DAILY`` daily closes are available
    (warmup), and otherwise the mean and the daily bars it reads for observations. All
    bars are at or before ``end_time`` (the decision's formation end), hence causal.
    """

    lo = bisect_right(rows.daily_times, start_time)
    hi = bisect_right(rows.daily_times, end_time)
    window = rows.daily_bars[lo:hi]
    if len(window) < _MA_MIN_DAILY:
        return None
    mean = sum(bar.close for bar in window) / len(window)
    return mean, window


def _recent_annualized_vol(
    rows: _SymbolRows, cutoff_time: datetime, lookback_days: int
) -> tuple[float, tuple[_BarRow, ...]] | None:
    """Annualized std of daily log returns over the window ending at ``cutoff_time``.

    Reads UTC-midnight daily closes known at ``cutoff_time`` (all at or before the
    decision's formation end, hence causal). Returns ``None`` during warmup, when fewer
    than ``_VOL_MIN_RETURNS`` daily returns are available. Also returns the daily bars
    whose closes the estimate reads, so the decision can declare them as observations.
    """

    end = bisect_right(rows.daily_times, cutoff_time)
    start = max(0, end - (lookback_days + 1))
    window = rows.daily_bars[start:end]
    if len(window) < _VOL_MIN_RETURNS + 1:
        return None
    log_returns = [
        math.log(window[i].close / window[i - 1].close) for i in range(1, len(window))
    ]
    count = len(log_returns)
    mean = sum(log_returns) / count
    variance = sum((value - mean) ** 2 for value in log_returns) / (count - 1)
    annualized = math.sqrt(variance) * math.sqrt(_PERIODS_PER_YEAR_DAILY)
    return annualized, window


def _confirm_gate(target: float, confirm_return: float) -> float:
    """Zero the target unless its sign agrees with the slow regime trend.

    A long survives only in a slow uptrend, a short only in a slow downtrend; when
    the fast signal and the slow regime disagree (chop or transition) the book stands
    flat. This trades with the major trend and exits whipsaw regimes rather than
    fighting them.
    """

    if target > 0.0 and confirm_return <= 0.0:
        return 0.0
    if target < 0.0 and confirm_return >= 0.0:
        return 0.0
    return target


def _vote(formation_return: float, signal: str) -> float:
    """One trend vote: +1 up, -1 down for ``sign``; +1 up, 0 otherwise for ``long_flat``."""

    if formation_return > 0.0:
        return 1.0
    if signal == "long_flat":
        return 0.0
    if formation_return < 0.0:
        return -1.0
    return 0.0


def _hysteresis_vote(
    formation_return: float, signal: str, band: float, prev_vote: float
) -> float:
    """Trend vote with a no-trade band around zero (hysteresis).

    Enter/hold the trend direction only when the formation return clears ``+band``
    (or drops below ``-band``); inside the band, hold the prior standing vote. This
    collapses whipsaw round-trips through the zero-crossing zone into holds, cutting
    turnover (and its capacity participation) without slowing the formation horizon.
    """

    if formation_return > band:
        return 1.0
    if formation_return < -band:
        return 0.0 if signal == "long_flat" else -1.0
    return prev_vote


def _rebalance_times(
    rows_by_symbol: Mapping[str, _SymbolRows], rebalance_days: int
) -> tuple[datetime, ...]:
    """UTC-midnight rebalance clock firing every ``rebalance_days`` days.

    Uses the union of bar timestamps so the clock only fires where data exists; the
    day-ordinal modulo fixes a consistent phase across the window.
    """

    times = {
        timestamp
        for rows in rows_by_symbol.values()
        for timestamp in rows.timestamps
        if timestamp.hour == 0
        and timestamp.minute == 0
        and timestamp.date().toordinal() % rebalance_days == 0
    }
    return tuple(sorted(times))


def _rows_by_symbol(bars: Sequence[Mapping[str, object]]) -> dict[str, _SymbolRows]:
    grouped: dict[str, list[_BarRow]] = {}
    for index, bar in enumerate(bars):
        missing = _REQUIRED_FIELDS - set(bar)
        if missing:
            raise ValueError(f"bar {index} missing fields: {sorted(missing)}")
        symbol = str(bar["symbol"])
        grouped.setdefault(symbol, []).append(
            _BarRow(
                symbol=symbol,
                timestamp=_datetime_value(bar["timestamp"], "timestamp"),
                available_at=_datetime_value(bar["available_at"], "available_at"),
                close=_positive_float(bar["close"], "close"),
            )
        )

    result: dict[str, _SymbolRows] = {}
    for symbol, symbol_bars in grouped.items():
        ordered = tuple(sorted(symbol_bars, key=lambda row: row.timestamp))
        daily = tuple(
            row for row in ordered if row.timestamp.hour == 0 and row.timestamp.minute == 0
        )
        result[symbol] = _SymbolRows(
            bars=ordered,
            timestamps=tuple(row.timestamp for row in ordered),
            daily_bars=daily,
            daily_times=tuple(row.timestamp for row in daily),
        )
    return result


def _observations(symbol: str, bars: tuple[_BarRow, ...]) -> tuple[ObservationRef, ...]:
    """Declare the close observations the decision reads, deduped by bar time."""

    seen: set[datetime] = set()
    refs: list[ObservationRef] = []
    for row in sorted(bars, key=lambda bar: bar.timestamp):
        if row.timestamp in seen:
            continue
        seen.add(row.timestamp)
        refs.append(
            ObservationRef(
                symbol=symbol,
                timestamp=row.timestamp,
                field="close",
                source=_SOURCE,
            )
        )
    return tuple(refs)


def _param_int(params: Mapping[str, object], key: str) -> int:
    return cast(int, params[key])


def _param_float(params: Mapping[str, object], key: str) -> float:
    return cast(float, params[key])


def _param_bool(params: Mapping[str, object], key: str) -> bool:
    return cast(bool, params[key])


def _param_str(params: Mapping[str, object], key: str) -> str:
    return cast(str, params[key])


def _datetime_value(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"{field_name} must be a datetime or ISO string")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _finite_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    parsed = float(value)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    return parsed


def _positive_float(value: object, name: str) -> float:
    parsed = _finite_float(value, name)
    if parsed <= 0.0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _non_negative_fraction(value: object, name: str) -> float:
    """Non-negative fraction in [0, 1); ``0`` disables the associated band."""

    parsed = _finite_float(value, name)
    if parsed < 0.0 or parsed >= 1.0:
        raise ValueError(f"{name} must be in [0, 1)")
    return parsed


def _int_value(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _positive_int(value: object, name: str) -> int:
    parsed = _int_value(value, name)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _non_negative_int(value: object, name: str) -> int:
    parsed = _int_value(value, name)
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _bool_param(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _signal(value: object) -> str:
    parsed = str(value)
    if parsed not in {"sign", "long_flat"}:
        raise ValueError("signal must be one of: sign, long_flat")
    return parsed


def _trend_method(value: object) -> str:
    parsed = str(value)
    if parsed not in {"return", "ma_cross"}:
        raise ValueError("trend_method must be one of: return, ma_cross")
    return parsed


def _weighting(value: object) -> str:
    parsed = str(value)
    if parsed not in {"equal", "inverse_vol", "conviction"}:
        raise ValueError("weighting must be one of: equal, inverse_vol, conviction")
    return parsed


def _gross_mode(value: object) -> str:
    parsed = str(value)
    if parsed not in {"universe", "active", "tilted"}:
        raise ValueError("gross_mode must be one of: universe, active, tilted")
    return parsed
