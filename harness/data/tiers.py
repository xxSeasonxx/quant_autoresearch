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

    # Lockbox is the most-recent forward block.
    if not (lockbox.start > train.end and lockbox.start > selection.end):
        raise TierError("Lockbox must be the most-recent forward block (FR-B1)")

    return TierSpans(
        train=train,
        selection=selection,
        lockbox=lockbox,
        symbols=tuple(tiers.symbols),
    )
