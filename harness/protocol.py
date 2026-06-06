"""The Protocol / Experiment split and the mechanical config wall (FR-H).

Two surfaces, split by ownership (harness-architecture §4):

- **Experiment** (agent-editable): ``strategy_path`` + ``params`` (+ optional bounded
  discovery ``symbols``). Nothing about how it is judged.
- **Protocol** (harness-owned, read-only to the agent): data tiers, cost model, fill
  model, fold/walk-forward/embargo config, objective metric + gates + thresholds, factor
  panel spec, budget, perturbation steps, annualization.

The wall is **mechanical, not advisory**:

1. The Protocol is **content-hashed**; ``load_protocol`` **fails closed** on drift
   (``ProtocolDriftError``) — FR-H2, AC-3. The hash is what a ledger row records (P3).
2. ``derive_foundation_config`` lets ``params`` populate **only** strategy params. It is
   **structurally** unable to override cost/fill/tiers (FR-H3): the derived config takes
   cost/fill/tiers from the Protocol and places ``params`` in a *separate* field — there is
   no key, merge, or override path by which ``cost_model = 0/0`` could be resurrected.
   AC-3 asserts this as the *absence of a code path*, not a guarded exception.

Pydantic at the config boundary; all models frozen + ``extra="forbid"`` so an unknown key
(e.g. a sneaked cost override) is rejected at parse time.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProtocolError(Exception):
    """Base class for Protocol loading/validation failures."""


class ProtocolDriftError(ProtocolError):
    """Raised when a loaded Protocol's content hash does not match the expected hash.

    This is the fail-closed signal (FR-H2, AC-3): an agent-process edit to the Protocol
    file after its hash was recorded stops the run rather than silently judging against
    tampered config.
    """


class _Frozen(BaseModel):
    """Frozen, strict base: unknown keys are rejected at parse time."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- #
# Protocol sub-models (harness-owned judgment config).
# --------------------------------------------------------------------------- #


class CostModel(_Frozen):
    """Realistic costs are part of the edge (Principle 4). Never overridable by params."""

    taker_bps: float = Field(ge=0.0)
    maker_bps: float = Field(ge=0.0)
    slippage_bps: float = Field(ge=0.0, default=0.0)
    # The cost-stress scenario multiplies realistic costs by this factor (the cost-stress
    # survival gate checks the edge holds under it). Protocol-owned; >1 means harsher costs.
    stress_multiplier: float = Field(ge=1.0, default=2.0)


class FillModel(_Frozen):
    fill: str  # e.g. "next_bar_open", "close"
    participation_cap: float = Field(gt=0.0, le=1.0, default=1.0)


class DataTier(_Frozen):
    """One partition span (Train / Selection / Lockbox). Consumed in P2."""

    start: str  # ISO date; the harness owns spans, the agent never edits them
    end: str


class DataSource(_Frozen):
    """The foundation data surface for the campaign (harness-owned, FR-H/FR-J3).

    ``kind`` and ``dataset`` are the ``quant_data`` loader selectors the foundation's
    ``[data]`` block needs (e.g. ``kind="crypto_perp_funding"``, or ``kind="bars"`` with
    ``dataset="crypto_perp_1min"``). They define *what data the campaign is judged on* — part
    of the immutable judgment config, never agent-editable. Defaults suit hourly crypto perp.
    """

    kind: str = "crypto_perp_funding"
    dataset: str | None = None  # required by the foundation only for kind="bars"
    # ge=1 to match the foundation's FillModelConfig.entry_lag_bars (Field(ge=1)); a 0 would
    # derive a config the foundation rejects, so fail closed at the harness boundary instead.
    entry_lag_bars: int = Field(ge=1, default=1)
    exit_lag_bars: int = Field(ge=0, default=0)


class DataTiers(_Frozen):
    train: DataTier
    selection: DataTier
    lockbox: DataTier
    symbols: tuple[str, ...] = ()  # the asset universe for the campaign
    source: DataSource = DataSource()


class FoldConfig(_Frozen):
    """Walk-forward / embargo config. Fields exist now; consumed in P2 (FR-B2/B3)."""

    scheme: str = "rolling"  # "rolling" | "anchored"
    n_folds: int = Field(gt=0, default=6)
    train_periods: int = Field(gt=0, default=4320)  # e.g. ~6mo of hourly bars
    test_periods: int = Field(gt=0, default=1440)
    purge_periods: int = Field(ge=0, default=24)
    embargo_periods: int = Field(ge=0, default=24)


class GateThresholdSpec(_Frozen):
    """Stage-1 gate thresholds. P1 consumes the cheap ones; P2 adds the rest."""

    # P1 (cheap) gates:
    min_trades: int = Field(gt=0, default=30)
    max_concentration: float = Field(gt=0.0, le=1.0, default=0.5)
    min_effective_breadth: float = Field(ge=1.0, default=2.0)
    # P2 (deferred) gates — fields present so the Protocol is forward-complete:
    psr_floor: float = Field(ge=0.0, le=1.0, default=0.95)
    max_drawdown_ceiling: float = Field(gt=0.0, default=0.35)
    worst_fold_floor: float = Field(default=0.0)
    dispersion_ceiling: float = Field(gt=0.0, default=3.0)
    cost_stress_ratio: float = Field(ge=0.0, default=0.5)


class FactorPanelSpec(_Frozen):
    """Which factor axes to neutralize (FR-C3). Funding is carry, regressed out.

    ``axes`` is the full canonical panel the harness neutralizes *when a column is present*.
    ``required_factors`` is the stronger FAIL-CLOSED contract (PRD Principle 6, AC-9/G2): the
    columns the objective MUST be able to regress out before it may produce a feasible RES /
    confirmed Lockbox verdict. If the supplied panel does not COVER these (empty/identity panel
    — e.g. an unwired provider), the judgment layer fails closed (RES infeasible / Lockbox
    insufficient_evidence) rather than silently scoring RAW returns as residual alpha. Defaults
    to the two drivers a crypto-perp campaign must neutralize: market (BTC beta) + funding carry.
    """

    axes: tuple[str, ...] = ("market", "momentum", "funding_carry", "size")
    required_factors: tuple[str, ...] = ("market", "funding_carry")


class ObjectiveSpec(_Frozen):
    """The objective metric + gates + thresholds (RES)."""

    rank_metric: str = "sharpe"  # RES ranks on Sharpe (FR-C2) — of the residual
    gates: GateThresholdSpec = GateThresholdSpec()
    factor_panel: FactorPanelSpec = FactorPanelSpec()
    deflate_per_row: bool = False  # FR-C6: the row is NOT deflated


class BudgetSpec(_Frozen):
    """Global Selection-look budget (field only in P1; enforced in P3, FR-E2)."""

    max_selection_looks: int = Field(gt=0, default=8)


class StabilitySpec(_Frozen):
    """Stability-gate config (FR-D2). Steps are Protocol-owned, never agent-set."""

    rho: float = Field(gt=0.0, le=1.0, default=0.6)  # min_N m(θ) ≥ ρ·m(θ*)
    min_positive_fraction: float = Field(ge=0.0, le=1.0, default=0.8)  # ≥80% neighbours positive
    step_multipliers: tuple[int, ...] = (1, 2)  # ±1/±2 natural steps
    # natural step size per tunable param name (e.g. {"lookback": 4, "threshold": 0.1}).
    param_steps: dict[str, float] = Field(default_factory=dict)


class AnnualizationSpec(_Frozen):
    periods_per_year: float = Field(gt=0.0, default=8760.0)  # hourly crypto default


class Protocol(_Frozen):
    """Immutable, content-hashed judgment config. Harness-owned; read-only to the agent."""

    name: str
    cost_model: CostModel
    fill_model: FillModel
    data_tiers: DataTiers
    folds: FoldConfig = FoldConfig()
    objective: ObjectiveSpec = ObjectiveSpec()
    budget: BudgetSpec = BudgetSpec()
    stability: StabilitySpec = StabilitySpec()
    annualization: AnnualizationSpec = AnnualizationSpec()

    @property
    def content_hash(self) -> str:
        """Stable SHA-256 over the canonical content (sorted keys, no whitespace drift).

        Order-independent and float-stable. This is the hash recorded in every ledger
        row (FR-H2) and the value ``load_protocol`` checks against to fail closed.
        """
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Experiment (agent-editable hypothesis surface).
# --------------------------------------------------------------------------- #


class Experiment(_Frozen):
    """The agent's only judgment-relevant surface: strategy + params (+ bounded symbols)."""

    strategy_path: str
    params: dict[str, Any] = Field(default_factory=dict)
    symbols: tuple[str, ...] | None = None  # optional bounded discovery set


# --------------------------------------------------------------------------- #
# The derived foundation call config — the structural wall (FR-H3).
# --------------------------------------------------------------------------- #


class FoundationCallConfig(_Frozen):
    """What the harness hands the foundation for one call.

    cost_model / fill_model / data_tiers come **solely** from the Protocol; the agent's
    ``params`` live ONLY under ``strategy_params``. There is no field, merge, or override
    path by which a param key could change a cost/fill/tier value — invalid states are
    unrepresentable. This is the mechanical wall (FR-H3, AC-3).
    """

    cost_model: CostModel
    fill_model: FillModel
    data_tiers: DataTiers
    strategy_path: str
    strategy_params: dict[str, Any]
    symbols: tuple[str, ...]


def derive_foundation_config(
    protocol: Protocol, experiment: Experiment
) -> FoundationCallConfig:
    """Derive the per-call foundation config from Protocol + Experiment.

    The Protocol owns cost/fill/tiers; the Experiment owns only strategy params. There
    is deliberately no code path that merges ``experiment.params`` into cost/fill/tiers.
    """
    symbols = experiment.symbols if experiment.symbols is not None else protocol.data_tiers.symbols
    return FoundationCallConfig(
        cost_model=protocol.cost_model,
        fill_model=protocol.fill_model,
        data_tiers=protocol.data_tiers,
        strategy_path=experiment.strategy_path,
        strategy_params=dict(experiment.params),
        symbols=tuple(symbols),
    )


# --------------------------------------------------------------------------- #
# Loading + fail-closed drift detection.
# --------------------------------------------------------------------------- #


def load_protocol(path: str | Path, expected_hash: str | None = None) -> Protocol:
    """Load and validate a Protocol from a TOML file outside the agent's writable surface.

    If ``expected_hash`` is provided and does not match the loaded Protocol's
    ``content_hash``, raise ``ProtocolDriftError`` (fail closed, FR-H2 / AC-3). Unknown
    keys (e.g. a sneaked cost override) are rejected by ``extra="forbid"`` at parse time.
    """
    p = Path(path)
    if not p.is_file():
        raise ProtocolError(f"protocol file not found: {p}")
    with p.open("rb") as fh:
        payload = tomllib.load(fh)
    protocol = Protocol.model_validate(payload)
    if expected_hash is not None and protocol.content_hash != expected_hash:
        raise ProtocolDriftError(
            f"protocol content hash drift: expected {expected_hash}, "
            f"got {protocol.content_hash} (run fails closed)"
        )
    return protocol
