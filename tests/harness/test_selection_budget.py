"""P3 acceptance criteria through the Selection-look path (AC-2, AC-7, AC-8 + FR-I2/NFR-6).

These run the real ``SelectionController`` (family + budget + ledger + walk-forward RES) against
a DETERMINISTIC fake gateway keyed by ``(protocol_hash, experiment_hash, snapshot)`` → identical
synthetic ``FoldReturns`` → identical ``ResResult`` on regeneration. The strategy source is
injected (no disk dependency) so we can mutate it to test relabeling / param-tweaks / structural
changes precisely.

- **AC-2** — renaming the thesis ⇒ SAME family ⇒ no extra looks; splitting one signal by
  relabeling or param-tweaks ⇒ still the same family ⇒ the total looks a campaign can run is the
  global cap, UNCHANGED. The cap cannot be raised by any relabeling/splitting.
- **AC-7** — a logged row regenerates its metric bit-for-bit from its fingerprint (same gateway
  key ⇒ identical returns ⇒ identical RES), and the persisted row round-trips with arrays intact.
- **AC-8** — re-evaluating tweaks of one idea on the same Selection data each spends from the
  GLOBAL budget; once spent, no more looks ⇒ no probe/free-look path.
- **FR-I2/NFR-6** — a crash between reserve and finalize keeps the look charged + the ledger
  append-only-consistent.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from harness.budget import BudgetManager
from harness.family import compute_family_id
from harness.foundation import FoldEvalResult, FoldReturns
from harness.ledger import TrialLedger
from harness.objective.res import GateThresholds
from harness.protocol import Experiment, Protocol
from harness.selection import NoLookAvailable, SelectionController, experiment_hash

PPY = 8760.0
THRESHOLDS = GateThresholds(min_trades=30, max_concentration=0.6, min_effective_breadth=2.0)

# A genuinely diversified idiosyncratic-alpha signal (feasible through the gates). The literal
# threshold and the docstring are what we mutate to test relabeling / param-tweaks.
_STRATEGY_SRC = '''
def _momentum(series, lookback):
    return series[-1] / series[-lookback] - 1.0


def generate_decisions(bars, params):
    """A momentum thesis the agent can rename freely."""
    lookback = params["lookback"]
    threshold = 0.012
    out = []
    for series in bars:
        if _momentum(series, lookback) > threshold:
            out.append("long")
    return out
'''


def _protocol(symbols, name="p3") -> Protocol:
    return Protocol.model_validate(
        {
            "name": name,
            "cost_model": {"taker_bps": 5, "maker_bps": 1, "slippage_bps": 1, "stress_multiplier": 2.0},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-03-31"},
                "selection": {"start": "2024-04-01", "end": "2024-10-31"},
                "lockbox": {"start": "2024-11-01", "end": "2024-12-31"},
                "symbols": list(symbols),
                "source": {"kind": "crypto_perp_funding"},
            },
            "folds": {
                "scheme": "rolling", "n_folds": 3, "train_periods": 720,
                "test_periods": 240, "purge_periods": 24, "embargo_periods": 24,
            },
            "annualization": {"periods_per_year": PPY},
        }
    )


class _DeterministicGateway:
    """A FoundationGateway whose fold is a pure function of (protocol_hash, experiment_hash, fold,
    cost-scenario, snapshot). Same inputs ⇒ identical synthetic FoldReturns ⇒ identical RES — this
    is what makes AC-7 a bit-for-bit reproduction rather than a re-roll. It also stashes the TRUE
    factor panel per fold so residual alpha is measured against the real driver (as production does).
    """

    SNAPSHOT = "snap-deterministic"

    def __init__(self, symbols):
        self._symbols = tuple(symbols)
        self._panels: dict[int, dict] = {}
        self.evaluate_calls: list = []

    def quick_run(self, experiment, protocol, window):  # pragma: no cover - unused
        raise NotImplementedError

    def _seed(self, protocol, experiment, window, stressed: bool) -> int:
        exp_h = experiment_hash(experiment, strategy_source=_STRATEGY_SRC)
        key = f"{protocol.content_hash}|{exp_h}|{window.window_id}|{stressed}|{self.SNAPSHOT}"
        return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)

    def _is_stressed(self, protocol) -> bool:
        # The orchestrator's stressed protocol multiplies costs; detect it by the taker bps.
        return protocol.cost_model.taker_bps > 5.0

    def evaluate(self, experiment, protocol, window):
        self.evaluate_calls.append(window)
        seed = self._seed(protocol, experiment, window, self._is_stressed(protocol))
        rng = np.random.default_rng(seed)
        n = 240
        market = 0.012 * rng.standard_normal(n) + 0.004
        by_symbol, port = {}, np.zeros(n)
        for i, sym in enumerate(self._symbols):
            legrng = np.random.default_rng(seed * 10 + i)
            leg = 0.0012 + 0.9 * market + 0.003 * legrng.standard_normal(n)
            ts = (np.arange(n, dtype="timedelta64[h]") + np.datetime64("2024-04-01")).astype("datetime64[ns]")
            by_symbol[sym] = FoldReturns(timestamps=ts, values=leg, periods_per_year=PPY)
            port += leg / len(self._symbols)
        ts = (np.arange(n, dtype="timedelta64[h]") + np.datetime64("2024-04-01")).astype("datetime64[ns]")
        fold = FoldReturns(timestamps=ts, values=port, periods_per_year=PPY, by_symbol=by_symbol)
        self._panels[id(fold)] = {"market": market}
        return FoldEvalResult(
            succeeded=True, causal_ok=True, returns=fold, sharpe=1.5, sortino=1.5,
            calmar=1.0, max_drawdown=-0.1, trade_count=300, worst_period_return=-0.04,
            provenance={"snapshot": self.SNAPSHOT, "foundation_version": "1.0", "backend_version": "2.0"},
            failure_stage=None,
        )

    def panel_for(self, window, returns):
        return self._panels.get(id(returns), {})


def _controller(tmp_path, symbols, cap=3):
    ledger = TrialLedger(tmp_path / "ledger.jsonl")
    budget = BudgetManager(cap=cap, ledger=ledger)
    gw = _DeterministicGateway(symbols)
    ctrl = SelectionController(
        ledger=ledger, budget=budget, gateway=gw, factor_panel_provider=gw.panel_for,
        strategy_source_loader=lambda _path: _STRATEGY_SRC,
    )
    return ctrl, ledger, budget, gw


# --------------------------------------------------------------------------- #
# AC-2 — budget unforgeable by relabeling / splitting.
# --------------------------------------------------------------------------- #


def test_ac2_renaming_thesis_is_the_same_family_and_spends_no_extra_budget(tmp_path):
    symbols = ("AAA", "BBB", "CCC")
    ctrl, ledger, budget, _ = _controller(tmp_path, symbols, cap=5)
    proto = _protocol(symbols)
    exp = Experiment(strategy_path="strategy.py", params={"lookback": 12}, symbols=symbols)

    r1 = ctrl.take_look(exp, proto, thesis="momentum persists", trial_id="t1",
                        created_at="2026-06-05T00:00:00Z", thresholds=THRESHOLDS)
    # Same code, a COMPLETELY different free-text thesis — must be the same family.
    r2 = ctrl.take_look(exp, proto, thesis="a totally different story about regimes",
                        trial_id="t2", created_at="2026-06-05T00:01:00Z", thresholds=THRESHOLDS)

    assert isinstance(r1, type(r2))
    assert r1.family_id == r2.family_id  # thesis is not the family key (FR-E4)
    # Both looks were charged from the SAME global budget — renaming bought nothing.
    assert budget.status().charged == 2
    assert {row.family_id for row in ledger.rows()} == {r1.family_id}


def test_ac2_splitting_by_param_tweaks_does_not_increase_total_looks(tmp_path):
    """The agent tries to 'split' one signal into many candidates by tweaking params (and the
    hardcoded literal). All map to ONE family; the campaign still runs exactly ``cap`` looks total —
    the global cap is UNCHANGED by the splitting (AC-2)."""
    symbols = ("AAA", "BBB", "CCC")
    cap = 3
    ctrl, ledger, budget, _ = _controller(tmp_path, symbols, cap=cap)
    proto = _protocol(symbols)

    looks, refused = [], 0
    for i in range(cap + 4):  # try to take far more looks than the cap by 'splitting'
        exp = Experiment(strategy_path="strategy.py", params={"lookback": 8 + i}, symbols=symbols)
        out = ctrl.take_look(exp, proto, thesis=f"variant {i} of the same idea", trial_id=f"t{i}",
                             created_at=f"2026-06-05T00:{i:02d}:00Z", thresholds=THRESHOLDS)
        if isinstance(out, NoLookAvailable):
            refused += 1
        else:
            looks.append(out)

    # Exactly ``cap`` looks were taken; every further attempt got the quota state, not a fresh look.
    assert len(looks) == cap
    assert refused == 4
    assert budget.status().charged == cap and budget.status().spent
    # Every tweak collapsed to the same family — the splitting minted no new family/budget.
    assert len({l.family_id for l in looks}) == 1


def test_ac2_cap_cannot_be_raised_by_any_relabeling(tmp_path):
    """The hard assertion: no relabeling/splitting changes the cap. Run a campaign that relabels
    thesis AND tweaks params on every look; the total looks ever taken == the global cap, full stop."""
    symbols = ("AAA", "BBB", "CCC")
    cap = 4
    ctrl, _, budget, _ = _controller(tmp_path, symbols, cap=cap)
    proto = _protocol(symbols)
    taken = 0
    for i in range(50):
        exp = Experiment(strategy_path="strategy.py", params={"lookback": 5 + i}, symbols=symbols)
        out = ctrl.take_look(exp, proto, thesis=f"relabel #{i}", trial_id=f"r{i}",
                             created_at=f"2026-06-05T01:{i:02d}:00Z", thresholds=THRESHOLDS)
        if not isinstance(out, NoLookAvailable):
            taken += 1
    assert taken == cap  # the cap is the cap, regardless of 50 relabelings


def test_ac2_a_structurally_different_signal_is_a_new_family_but_shares_the_global_budget(tmp_path):
    """A genuinely NEW signal structure is a new family (the fingerprint distinguishes it) — but
    it still draws from the SAME global budget, not a fresh per-family one (FR-E2)."""
    symbols = ("AAA", "BBB", "CCC")
    fam_a = compute_family_id(_STRATEGY_SRC)
    fam_b = compute_family_id(_STRATEGY_SRC.replace("> threshold", "< threshold"))
    assert fam_a != fam_b  # different structure ⇒ different family

    # Budget is global: two families share one cap. With cap=1, the first look spends it and the
    # second family gets NO fresh budget.
    ledger = TrialLedger(tmp_path / "l.jsonl")
    budget = BudgetManager(cap=1, ledger=ledger)
    src = {"A": _STRATEGY_SRC, "B": _STRATEGY_SRC.replace("> threshold", "< threshold")}
    gw = _DeterministicGateway(symbols)
    seen = {"v": "A"}
    ctrl = SelectionController(
        ledger=ledger, budget=budget, gateway=gw, factor_panel_provider=gw.panel_for,
        strategy_source_loader=lambda _p: src[seen["v"]],
    )
    proto = _protocol(symbols)
    exp = Experiment(strategy_path="strategy.py", params={"lookback": 12}, symbols=symbols)
    seen["v"] = "A"
    first = ctrl.take_look(exp, proto, thesis="family A", trial_id="a1",
                           created_at="2026-06-05T00:00:00Z", thresholds=THRESHOLDS)
    seen["v"] = "B"
    second = ctrl.take_look(exp, proto, thesis="family B", trial_id="b1",
                            created_at="2026-06-05T00:01:00Z", thresholds=THRESHOLDS)
    assert not isinstance(first, NoLookAvailable)
    assert isinstance(second, NoLookAvailable)  # global budget already spent by family A
    assert second.family_id == fam_b


# --------------------------------------------------------------------------- #
# AC-7 — a logged row regenerates its metric bit-for-bit from its fingerprint.
# --------------------------------------------------------------------------- #


def test_ac7_row_metric_regenerates_bit_for_bit_from_its_fingerprint(tmp_path):
    symbols = ("AAA", "BBB", "CCC")
    ctrl, ledger, _, _ = _controller(tmp_path, symbols, cap=3)
    proto = _protocol(symbols)
    exp = Experiment(strategy_path="strategy.py", params={"lookback": 12}, symbols=symbols)

    look = ctrl.take_look(exp, proto, thesis="momentum", trial_id="t1",
                          created_at="2026-06-05T00:00:00Z", thresholds=THRESHOLDS)
    logged_rank = look.row.res.rank_sharpe
    assert logged_rank is not None and look.row.res.feasible

    # Regenerate: a FRESH controller + ledger + gateway, same (protocol_hash, experiment_hash,
    # snapshot) ⇒ the deterministic gateway yields identical FoldReturns ⇒ identical RES.
    ctrl2, _, _, _ = _controller(tmp_path / "regen", symbols, cap=3)
    regen = ctrl2.take_look(exp, proto, thesis="momentum", trial_id="t1",
                            created_at="2026-06-05T00:00:00Z", thresholds=THRESHOLDS)
    assert regen.row.res.rank_sharpe == logged_rank  # bit-for-bit (same float object value)
    assert regen.row.res.per_fold_sharpe == look.row.res.per_fold_sharpe
    assert regen.row.experiment_hash == look.row.experiment_hash
    assert regen.row.protocol_hash == look.row.protocol_hash

    # And the PERSISTED row round-trips with arrays intact (the reproduction reads the same series).
    reread = TrialLedger(tmp_path / "ledger.jsonl").rows()[0]
    assert reread.res.rank_sharpe == logged_rank
    for got, orig in zip(reread.per_fold_returns, look.row.per_fold_returns):
        assert np.array_equal(got.values, orig.values)
    # The fingerprint carries the snapshot + versions sufficient to reproduce (FR-I1).
    assert reread.provenance["snapshot"] == _DeterministicGateway.SNAPSHOT
    assert "foundation_version" in reread.provenance


def test_ac7_full_per_fold_returns_of_the_trial_are_logged(tmp_path):
    """The audit (P4) is impossible without the returns of EVERY trial — the row carries them."""
    symbols = ("AAA", "BBB", "CCC")
    ctrl, _, _, _ = _controller(tmp_path, symbols, cap=3)
    proto = _protocol(symbols)
    exp = Experiment(strategy_path="strategy.py", params={"lookback": 12}, symbols=symbols)
    look = ctrl.take_look(exp, proto, thesis="momentum", trial_id="t1",
                          created_at="2026-06-05T00:00:00Z", thresholds=THRESHOLDS)
    # One per successful fold, each with its per-symbol legs (the audit + breadth need them).
    assert len(look.row.per_fold_returns) == look.walk_forward.n_folds_evaluated >= 2
    assert all(fr.by_symbol and set(fr.by_symbol) == set(symbols) for fr in look.row.per_fold_returns)


# --------------------------------------------------------------------------- #
# AC-8 — no hill-climb leak: every tweak spends from the global budget; no free probe.
# --------------------------------------------------------------------------- #


def test_ac8_re_evaluating_tweaks_each_spends_until_the_budget_is_spent(tmp_path):
    symbols = ("AAA", "BBB", "CCC")
    cap = 3
    ctrl, ledger, budget, _ = _controller(tmp_path, symbols, cap=cap)
    proto = _protocol(symbols)

    charged_after = []
    for i in range(cap):
        exp = Experiment(strategy_path="strategy.py", params={"lookback": 10 + i}, symbols=symbols)
        ctrl.take_look(exp, proto, thesis=f"tweak {i}", trial_id=f"t{i}",
                       created_at=f"2026-06-05T00:{i:02d}:00Z", thresholds=THRESHOLDS)
        charged_after.append(budget.status().charged)
    # Each tweak charged exactly one look — monotonic, no free probe slipped through.
    assert charged_after == [1, 2, 3]
    assert budget.status().spent

    # One more tweak on the SAME Selection data: refused. The agent cannot grind to raise odds.
    exp = Experiment(strategy_path="strategy.py", params={"lookback": 99}, symbols=symbols)
    out = ctrl.take_look(exp, proto, thesis="just one more", trial_id="extra",
                         created_at="2026-06-05T00:09:00Z", thresholds=THRESHOLDS)
    assert isinstance(out, NoLookAvailable)
    # Nothing was logged for the refused look — no row, no charge beyond the cap.
    assert budget.status().charged == cap
    assert "extra" not in {r.trial_id for r in ledger.rows()}
    assert "extra" not in ledger.charged_trial_ids()


def test_ac8_there_is_no_free_look_path_every_finalized_row_was_charged(tmp_path):
    """Structural: every logged row corresponds to a charged reservation (no probe loophole)."""
    symbols = ("AAA", "BBB", "CCC")
    ctrl, ledger, _, _ = _controller(tmp_path, symbols, cap=4)
    proto = _protocol(symbols)
    for i in range(3):
        exp = Experiment(strategy_path="strategy.py", params={"lookback": 10 + i}, symbols=symbols)
        ctrl.take_look(exp, proto, thesis=f"t{i}", trial_id=f"t{i}",
                       created_at=f"2026-06-05T00:{i:02d}:00Z", thresholds=THRESHOLDS)
    charged = ledger.charged_trial_ids()
    logged = {r.trial_id for r in ledger.rows()}
    assert logged <= charged  # every finalized row was charged first (reserve-before-run)
    assert len(charged) == 3


# --------------------------------------------------------------------------- #
# FR-I2 / NFR-6 — crash between reserve and finalize keeps the look charged.
# --------------------------------------------------------------------------- #


def test_fri2_crash_between_reserve_and_finalize_keeps_the_look_charged(tmp_path):
    """If the walk-forward run raises after the reservation, the look stays charged (never lost),
    the ledger remains append-only-consistent, and the budget reflects the spend on recovery."""
    symbols = ("AAA", "BBB", "CCC")
    ledger = TrialLedger(tmp_path / "crash.jsonl")
    budget = BudgetManager(cap=3, ledger=ledger)

    class _CrashingGateway(_DeterministicGateway):
        def evaluate(self, experiment, protocol, window):
            raise RuntimeError("foundation blew up mid-fold")

    gw = _CrashingGateway(symbols)
    ctrl = SelectionController(
        ledger=ledger, budget=budget, gateway=gw, factor_panel_provider=gw.panel_for,
        strategy_source_loader=lambda _p: _STRATEGY_SRC,
    )
    proto = _protocol(symbols)
    exp = Experiment(strategy_path="strategy.py", params={"lookback": 12}, symbols=symbols)

    with pytest.raises(RuntimeError):
        ctrl.take_look(exp, proto, thesis="will crash", trial_id="boom",
                       created_at="2026-06-05T00:00:00Z", thresholds=THRESHOLDS)

    # Recover from disk (as a restarted process would): the look is charged, no row, consistent.
    recovered = TrialLedger(tmp_path / "crash.jsonl")
    assert recovered.charged_count() == 1  # FR-I2: charged, never silently lost
    assert recovered.pending_reservations() == ["boom"]
    assert recovered.rows() == []  # no finalized row (the run failed)
    # The budget, read against the recovered ledger, reflects the spend.
    assert BudgetManager(cap=3, ledger=recovered).remaining() == 2
