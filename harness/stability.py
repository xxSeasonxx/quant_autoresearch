"""The stability gate — computed, not LLM-judged (FR-D2, enforcement #10).

Before a candidate may take a Selection look, the harness perturbs each tunable param
±1/±2 natural steps on Train (one-at-a-time; steps owned by the Protocol, not the agent)
via ``FoundationGateway.quick_run``, and requires the in-sample metric to stay
**flat-and-positive**:

    min_N m(θ) ≥ ρ · m(θ*)        (ρ ≈ 0.6, from the Protocol)
    AND ≥ 80% of neighbours have m(θ) > 0 after costs
    AND m(θ*) > 0

Stability score  ``S = min_N m(θ) / m(θ*)``.

A knife-edge fit (low/negative S, or a non-positive center) is **routed back to Train**
(cannot evaluate). The gate rewards *flatness, not height*, so it cannot be gamed by
climbing the score — the agent only proposes θ* and which params matter; the harness
measures.

This is an in-sample pre-filter only; Selection/Lockbox still confirm. It runs entirely
through the gateway (the ``FakeFoundationGateway`` in tests — no live data).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.foundation import FoundationGateway, QuickRunResult
from harness.protocol import Experiment, Protocol

_EPS = 1e-12


@dataclass(frozen=True)
class Neighbour:
    """One perturbed evaluation."""

    param: str
    delta_steps: int  # signed multiple of the natural step (e.g. -2, -1, +1, +2)
    value: float | None  # in-sample metric after costs (None if infeasible)


@dataclass(frozen=True)
class StabilityResult:
    """Verdict of the stability gate."""

    passed: bool
    score: float | None  # S = min_N m(θ) / m(θ*); None if center non-positive/infeasible
    center_metric: float | None
    worst_neighbour: float | None
    positive_fraction: float | None  # fraction of neighbours with m(θ) > 0
    neighbours: tuple[Neighbour, ...]
    routed_back_to_train: bool  # True ⇒ knife-edge, cannot evaluate
    detail: str = ""


def _perturbed_experiment(
    experiment: Experiment, param: str, new_value: float
) -> Experiment:
    """Return a copy of the experiment with one param changed (others fixed)."""
    new_params = dict(experiment.params)
    new_params[param] = new_value
    return experiment.model_copy(update={"params": new_params})


def _coerce_step(base: Any, step: float, multiplier: int) -> float | int:
    """Apply ``base + multiplier*step``, preserving int-ness of integer params."""
    value = float(base) + float(step) * float(multiplier)
    if isinstance(base, int) and float(step).is_integer():
        return int(round(value))
    return value


def evaluate_stability(
    experiment: Experiment,
    protocol: Protocol,
    window: Any,
    gateway: FoundationGateway,
) -> StabilityResult:
    """Run the stability gate for ``experiment`` on Train via ``gateway.quick_run``.

    Perturbs each param named in ``protocol.stability.param_steps`` by ±each multiplier
    in ``protocol.stability.step_multipliers``, one-at-a-time. The center metric is the
    unperturbed quick run. Returns a verdict; ``passed=False`` and
    ``routed_back_to_train=True`` on a knife-edge.
    """
    spec = protocol.stability
    rho = spec.rho

    center_run: QuickRunResult = gateway.quick_run(experiment, protocol, window)
    center = center_run.in_sample_metric

    # A non-positive or infeasible center is itself a knife-edge / non-edge: route back.
    if center is None or center <= 0.0:
        return StabilityResult(
            passed=False,
            score=None,
            center_metric=center,
            worst_neighbour=None,
            positive_fraction=None,
            neighbours=(),
            routed_back_to_train=True,
            detail="center metric non-positive or infeasible; cannot evaluate",
        )

    neighbours: list[Neighbour] = []
    for param, step in spec.param_steps.items():
        if param not in experiment.params:
            # The agent named a param the experiment does not set — skip it (the harness
            # only perturbs params that actually exist on the candidate).
            continue
        base = experiment.params[param]
        for mult in spec.step_multipliers:
            for signed in (-mult, mult):
                new_value = _coerce_step(base, step, signed)
                pert = _perturbed_experiment(experiment, param, new_value)
                run = gateway.quick_run(pert, protocol, window)
                neighbours.append(
                    Neighbour(param=param, delta_steps=signed, value=run.in_sample_metric)
                )

    if not neighbours:
        # No tunable params to perturb ⇒ no plateau can be established ⇒ cannot evaluate.
        return StabilityResult(
            passed=False,
            score=None,
            center_metric=center,
            worst_neighbour=None,
            positive_fraction=None,
            neighbours=(),
            routed_back_to_train=True,
            detail="no tunable params with Protocol-defined steps; cannot establish a plateau",
        )

    finite = [n.value for n in neighbours if n.value is not None]
    # An infeasible neighbour counts as the worst possible outcome (a hole next door).
    worst = min(finite) if len(finite) == len(neighbours) else float("-inf")
    positive_fraction = sum(1 for n in neighbours if n.value is not None and n.value > 0.0) / len(
        neighbours
    )

    score = worst / center if center > _EPS else float("-inf")
    flat_enough = worst >= rho * center
    broadly_positive = positive_fraction >= spec.min_positive_fraction
    passed = bool(flat_enough and broadly_positive)

    return StabilityResult(
        passed=passed,
        score=score if score != float("-inf") else None,
        center_metric=center,
        worst_neighbour=worst if worst != float("-inf") else None,
        positive_fraction=positive_fraction,
        neighbours=tuple(neighbours),
        routed_back_to_train=not passed,
        detail=(
            f"min_N/center={score:.3f} vs rho={rho}; "
            f"{positive_fraction:.0%} neighbours positive (need {spec.min_positive_fraction:.0%})"
            if score != float("-inf")
            else f"an infeasible neighbour exists; {positive_fraction:.0%} positive"
        ),
    )


def train_plausibility(
    experiment: Experiment,
    protocol: Protocol,
    window: Any,
    gateway: FoundationGateway,
) -> dict[str, Any]:
    """Coarse Train plausibility band surfaced from ``quick_run`` (deliberately coarse).

    Per open decision #3 ("lean coarse"): the free Train signal is a *band*, not a
    precise number — valid/causal + a positive/negative/flat plausibility label + the
    cheap-robust slices. Magnitude above the floor is mostly overfit, so we do not report
    it as a rankable score.
    """
    run = gateway.quick_run(experiment, protocol, window)
    m = run.in_sample_metric
    if m is None:
        band = "infeasible"
    elif m > 0.0:
        band = "positive"
    elif m < 0.0:
        band = "negative"
    else:
        band = "flat"
    return {
        "valid": run.valid,
        "causal_ok": run.causal_ok,
        "plausibility_band": band,
        "trade_count": run.trade_count,
        "slices": run.slices,
        "failure_stage": run.failure_stage,
    }
