"""AC-4 — Knife-edge bounced; a flat-and-positive plateau passes (FR-D2).

The stability gate is computed (not LLM-judged) and runs entirely through the
FakeFoundationGateway (no live data). It rewards flatness, not height.
"""

from __future__ import annotations

from harness.protocol import Experiment, Protocol
from harness.stability import evaluate_stability, train_plausibility
from harness.testing import FakeFoundationGateway

WINDOW = ("2024-01-01", "2024-09-30")


def _protocol(rho=0.6, min_pos=0.8, steps=(1, 2), param_steps=None) -> Protocol:
    return Protocol.model_validate(
        {
            "name": "stab-test",
            "cost_model": {"taker_bps": 5, "maker_bps": 1},
            "fill_model": {"fill": "close"},
            "data_tiers": {
                "train": {"start": "2024-01-01", "end": "2024-09-30"},
                "selection": {"start": "2024-10-01", "end": "2025-04-30"},
                "lockbox": {"start": "2025-05-01", "end": "2025-07-31"},
            },
            "stability": {
                "rho": rho,
                "min_positive_fraction": min_pos,
                "step_multipliers": list(steps),
                "param_steps": param_steps or {"lookback": 4, "threshold": 0.1},
            },
        }
    )


def _experiment(lookback=20, threshold=0.5) -> Experiment:
    return Experiment(strategy_path="strategy.py", params={"lookback": lookback, "threshold": threshold})


# --------------------------------------------------------------------------- #
# AC-4: a flat-and-positive plateau passes.
# --------------------------------------------------------------------------- #


def test_ac4_flat_positive_plateau_passes():
    """All neighbours stay near the center value ⇒ stability gate passes with S ≥ rho."""
    proto = _protocol()
    exp = _experiment()

    # A plateau: every param setting yields ~the same positive metric.
    def metric(experiment):
        return 1.0  # perfectly flat and positive

    gateway = FakeFoundationGateway(quick_metric_fn=metric)
    result = evaluate_stability(exp, proto, WINDOW, gateway)
    assert result.passed
    assert result.score is not None and result.score >= proto.stability.rho
    assert not result.routed_back_to_train
    # 2 params * 2 multipliers * 2 signs = 8 neighbours probed.
    assert len(result.neighbours) == 8


def test_ac4_mild_slope_within_rho_passes():
    """A gently sloped plateau (worst neighbour ≥ rho*center) still passes."""
    proto = _protocol(rho=0.6)
    exp = _experiment()

    def metric(experiment):
        # center=1.0; neighbours drop at most to 0.7 (> rho*center=0.6) and stay positive.
        d = abs(experiment.params["lookback"] - 20) / 4 + abs(experiment.params["threshold"] - 0.5) / 0.1
        return max(1.0 - 0.15 * d, 0.7)

    gateway = FakeFoundationGateway(quick_metric_fn=metric)
    result = evaluate_stability(exp, proto, WINDOW, gateway)
    assert result.passed


# --------------------------------------------------------------------------- #
# AC-4: a knife-edge collapses under perturbation and cannot be evaluated.
# --------------------------------------------------------------------------- #


def test_ac4_knife_edge_collapse_routed_back_to_train():
    """The metric spikes only at θ* and collapses under any ±step ⇒ cannot evaluate."""
    proto = _protocol(rho=0.6)
    exp = _experiment()

    def metric(experiment):
        at_center = experiment.params["lookback"] == 20 and experiment.params["threshold"] == 0.5
        return 2.0 if at_center else 0.1  # 0.1 < rho*2.0 = 1.2 ⇒ fails flatness

    gateway = FakeFoundationGateway(quick_metric_fn=metric)
    result = evaluate_stability(exp, proto, WINDOW, gateway)
    assert not result.passed
    assert result.routed_back_to_train
    assert result.score is not None and result.score < proto.stability.rho


def test_ac4_neighbours_turn_negative_fails_positive_fraction():
    """Neighbours flipping negative under perturbation ⇒ the gate fails and flags it.

    The ≥80%-positive arm (FR-D2) is the explicit "broadly positive after costs" check;
    when half the neighbours go negative it is violated (and is reported as the binding
    signal). A negative neighbour is also below ρ·center, so both arms agree the plateau
    is broken — exactly the intent.
    """
    proto = _protocol(rho=0.6, min_pos=0.8)
    exp = _experiment()

    def metric(experiment):
        # Center positive; the lookback neighbours go negative ⇒ 4/8 negative ⇒ 0.5 < 0.8.
        if experiment.params["lookback"] != 20:
            return -0.5
        return 1.0

    gateway = FakeFoundationGateway(quick_metric_fn=metric)
    result = evaluate_stability(exp, proto, WINDOW, gateway)
    assert not result.passed
    assert result.positive_fraction is not None and result.positive_fraction < 0.8


def test_ac4_infeasible_neighbour_is_a_hole_and_fails():
    """An infeasible (None) neighbour is the worst possible outcome — cannot evaluate."""
    proto = _protocol()
    exp = _experiment()

    def metric(experiment):
        if experiment.params["lookback"] == 16:  # one perturbation is infeasible
            return None
        return 1.0

    gateway = FakeFoundationGateway(quick_metric_fn=metric)
    result = evaluate_stability(exp, proto, WINDOW, gateway)
    assert not result.passed
    assert result.routed_back_to_train


def test_ac4_nonpositive_center_cannot_evaluate():
    """A negative/flat center is itself disqualifying — Train is biased high."""
    proto = _protocol()
    exp = _experiment()
    gateway = FakeFoundationGateway(quick_metric_fn=lambda e: -0.2)
    result = evaluate_stability(exp, proto, WINDOW, gateway)
    assert not result.passed
    assert result.routed_back_to_train
    assert result.center_metric == -0.2


def test_stability_rewards_flatness_not_height():
    """A lower-but-flat candidate passes where a higher-but-peaky one fails."""
    proto = _protocol(rho=0.6)
    exp = _experiment()

    flat_low = FakeFoundationGateway(quick_metric_fn=lambda e: 0.3)  # flat at 0.3
    peaky_high = FakeFoundationGateway(
        quick_metric_fn=lambda e: 5.0
        if (e.params["lookback"] == 20 and e.params["threshold"] == 0.5)
        else 0.5  # 0.5 < rho*5.0 = 3.0
    )
    assert evaluate_stability(exp, proto, WINDOW, flat_low).passed
    assert not evaluate_stability(exp, proto, WINDOW, peaky_high).passed


def test_no_tunable_params_cannot_establish_plateau():
    proto = _protocol(param_steps={"unused_param": 1.0})
    exp = _experiment()  # experiment has no "unused_param"
    gateway = FakeFoundationGateway(quick_metric_fn=lambda e: 1.0)
    result = evaluate_stability(exp, proto, WINDOW, gateway)
    assert not result.passed
    assert result.routed_back_to_train


def test_train_plausibility_is_coarse_band():
    proto = _protocol()
    exp = _experiment()
    gateway = FakeFoundationGateway(quick_metric_fn=lambda e: 0.4)
    band = train_plausibility(exp, proto, WINDOW, gateway)
    assert band["plausibility_band"] == "positive"
    assert band["valid"] is True
    assert "slices" in band
    # Deliberately coarse: no rankable magnitude is surfaced.
    assert "in_sample_metric" not in band
