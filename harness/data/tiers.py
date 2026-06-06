"""Tiered Data Service — disjoint Train / Selection / Lockbox partitions (FR-B1).

Derives the three data tiers per asset **from the harness-owned Protocol**, never from
agent-editable config. The partitions are disjoint and forward-ordered
(``Train ≤ Selection < Lockbox`` in time), and the Lockbox is the most-recent forward block
(the one-shot confirmation set the agent can never iterate against).

Pure: operates on the Protocol's ISO-date spans, requires no loaded data. Invalid
configurations (overlapping or mis-ordered tiers, a Lockbox that is not the latest block)
are rejected at derivation time, so an invalid tier layout is unrepresentable downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from harness.protocol import DataTier, DataTiers, Protocol

# Days per calendar year used to convert the purge horizon (in bars) to calendar days,
# matching the orchestrator's bar-duration conversion (``timedelta(days=365.25/ppy)``).
_DAYS_PER_YEAR = 365.25


def _purge_horizon_days(protocol: Protocol) -> int:
    """The purge horizon expressed as whole calendar days (FR-B3).

    The Protocol's purge is ``purge_periods`` bars; one bar spans ``365.25 / periods_per_year``
    days at the configured annualization cadence. The horizon is that product rounded to whole
    calendar days. Because the bar/day ratio is not generally integral (e.g. 8760 hourly bars
    vs 365.25 days ⇒ 23.98 bars/day), comparing whole calendar gaps to a sub-day-precise
    horizon is ambiguous; we therefore enforce a clearly-documented **minimum of 1 calendar
    day** so a configured purge always carves at least one day between adjacent tiers.
    """
    folds = protocol.folds
    ppy = protocol.annualization.periods_per_year
    if folds.purge_periods <= 0 or ppy <= 0:
        return 1
    bar_days = _DAYS_PER_YEAR / ppy
    return max(1, round(folds.purge_periods * bar_days))


class TierError(ValueError):
    """Raised when the Protocol's tier spans are not a valid disjoint forward partition."""


@dataclass(frozen=True)
class Span:
    """A half-open-in-spirit time span ``[start, end]`` (inclusive ISO-date bounds).

    Tiers are expressed in calendar dates (the Protocol surface). The walk-forward operates
    in integer period counts; ``Span`` is the bridge — it carries the calendar bounds the
    foundation's per-fold ``[[windows]]`` config consumes.
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise TierError(f"span end {self.end} precedes start {self.start}")

    def overlaps(self, other: "Span") -> bool:
        """True iff the two spans share any calendar day (inclusive bounds)."""
        return self.start <= other.end and other.start <= self.end

    def isoformat(self) -> tuple[str, str]:
        return self.start.isoformat(), self.end.isoformat()


@dataclass(frozen=True)
class TierSpans:
    """The three disjoint tiers for a campaign (the derived, validated partition)."""

    train: Span
    selection: Span
    lockbox: Span
    symbols: tuple[str, ...]

    @property
    def all_spans(self) -> tuple[Span, Span, Span]:
        return (self.train, self.selection, self.lockbox)


def _parse(d: str) -> date:
    # Accept plain ISO dates; the Protocol surface is dates, not datetimes.
    return datetime.fromisoformat(d).date()


def _span(tier: DataTier) -> Span:
    return Span(start=_parse(tier.start), end=_parse(tier.end))


def derive_tiers(protocol: Protocol) -> TierSpans:
    """Derive the disjoint Train/Selection/Lockbox partition from the Protocol (FR-B1).

    Validates (fails closed) that:
      - each span is well-formed (end ≥ start),
      - the three spans are pairwise non-overlapping,
      - they are forward-ordered Train → Selection → Lockbox,
      - the Lockbox is the most-recent block (its start is after both others end).
    """
    tiers: DataTiers = protocol.data_tiers
    train = _span(tiers.train)
    selection = _span(tiers.selection)
    lockbox = _span(tiers.lockbox)

    # Pairwise disjointness.
    pairs = (("train", train, "selection", selection),
             ("selection", selection, "lockbox", lockbox),
             ("train", train, "lockbox", lockbox))
    for a_name, a, b_name, b in pairs:
        if a.overlaps(b):
            raise TierError(
                f"tiers {a_name} {a.isoformat()} and {b_name} {b.isoformat()} overlap; "
                "Train/Selection/Lockbox must be disjoint (FR-B1)"
            )

    # Forward ordering: each tier strictly after the previous one ends.
    if not (train.end < selection.start):
        raise TierError("Selection must start after Train ends (forward-only, FR-B1/B2)")
    if not (selection.end < lockbox.start):
        raise TierError("Lockbox must start after Selection ends (forward-only, FR-B1/B2)")

    # Adjacent partitions must be separated by at least the purge horizon (FR-B3), not merely
    # be non-adjacent. Enforce mechanically so a too-tight boundary fails closed at derivation.
    horizon = _purge_horizon_days(protocol)
    for a_name, a_end, b_name, b_start in (
        ("Train", train.end, "Selection", selection.start),
        ("Selection", selection.end, "Lockbox", lockbox.start),
    ):
        gap_days = (b_start - a_end).days
        if gap_days < horizon:
            raise TierError(
                f"{a_name}→{b_name} gap is {gap_days}d but the purge horizon requires "
                f"≥{horizon}d separation (FR-B3); widen the boundary or lower purge_periods"
            )

    # Lockbox is the most-recent forward block.
    if not (lockbox.start > train.end and lockbox.start > selection.end):
        raise TierError("Lockbox must be the most-recent forward block (FR-B1)")

    return TierSpans(
        train=train,
        selection=selection,
        lockbox=lockbox,
        symbols=tuple(tiers.symbols),
    )
