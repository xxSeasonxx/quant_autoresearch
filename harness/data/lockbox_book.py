"""Write-once-per-*dataset* Lockbox bookkeeping (FR-B4).

The Lockbox is consumed **per dataset, not per candidate**: once *any* candidate is scored
on a Lockbox block, that block is spent for the whole campaign, and a new Lockbox requires
fresh forward time. This closes the cross-batch reuse leak where a reused forward block
silently becomes a second Selection set across graduation batches.

This module owns only the atomic per-dataset spent-flag (the full append-only ledger is P3,
``harness/ledger.py``; P3's ledger integrates this state). The "dataset" is identified by a
content key over the Lockbox span + symbols + Protocol hash, so the same block under the
same judgment config is one dataset; a freshly cut forward block (new span) is a new dataset.

State is persisted atomically (temp-file write + ``os.replace``) so a crash during a Lockbox
touch resolves toward "spent" (fail-safe, NFR-6) rather than silently leaving a reusable
block.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class LockboxSpentError(RuntimeError):
    """Raised when a Lockbox dataset that is already spent is scored again (FR-B4)."""


def lockbox_dataset_id(
    *,
    protocol_hash: str,
    lockbox_start: str,
    lockbox_end: str,
    symbols: Iterable[str],
) -> str:
    """Deterministic dataset key for one Lockbox block under one judgment config.

    Keyed to the *dataset* (span + universe + Protocol hash), never to a candidate — so two
    different candidates scored on the same block resolve to the same key (and the second is
    refused), while a freshly cut forward block (different span) is a different key.
    """
    canonical = json.dumps(
        {
            "protocol_hash": protocol_hash,
            "lockbox_start": lockbox_start,
            "lockbox_end": lockbox_end,
            "symbols": sorted(symbols),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LockboxSpend:
    """A record of one Lockbox dataset being spent (the unit P3's ledger integrates)."""

    dataset_id: str
    trial_id: str  # the candidate that first spent the block (for provenance)
    spent_at: str  # ISO timestamp, injected (never read from a clock here)


class LockboxBook:
    """Atomic, write-once-per-dataset Lockbox registry.

    In-memory by default; pass ``path`` to persist across processes (the campaign lifecycle).
    ``reserve(dataset_id, ...)`` is the single mutation: it succeeds exactly once per dataset
    and raises ``LockboxSpentError`` on any subsequent attempt for the same dataset.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._spent: dict[str, LockboxSpend] = {}
        if self._path is not None and self._path.is_file():
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        for did, rec in payload.items():
            self._spent[did] = LockboxSpend(
                dataset_id=did, trial_id=rec["trial_id"], spent_at=rec["spent_at"]
            )

    def _persist(self) -> None:
        if self._path is None:
            return
        payload = {
            did: {"trial_id": s.trial_id, "spent_at": s.spent_at}
            for did, s in self._spent.items()
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)  # atomic on POSIX

    def is_spent(self, dataset_id: str) -> bool:
        return dataset_id in self._spent

    def reserve(self, dataset_id: str, *, trial_id: str, spent_at: str) -> LockboxSpend:
        """Spend a Lockbox dataset for the campaign. Idempotent only to *failure*: the first
        call succeeds and records the spend; every later call for the same dataset raises.

        The reservation is persisted before returning, so a crash after this call still sees
        the block as spent (fail-safe toward "spent + logged", NFR-6 / FR-B4).
        """
        if dataset_id in self._spent:
            prior = self._spent[dataset_id]
            raise LockboxSpentError(
                f"Lockbox dataset {dataset_id[:12]}… already spent by trial "
                f"{prior.trial_id!r} at {prior.spent_at}; a new Lockbox needs fresh forward "
                "time (FR-B4)"
            )
        spend = LockboxSpend(dataset_id=dataset_id, trial_id=trial_id, spent_at=spent_at)
        self._spent[dataset_id] = spend
        self._persist()
        return spend
