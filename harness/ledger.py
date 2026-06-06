"""Trial Ledger — append-only, reproducible, fail-safe (FR-E1, FR-I1, FR-I2, NFR-6).

Every Selection look is a logged bet. The ledger is the campaign's system of record (it
retires ``results.tsv``): an **append-only** JSONL file where each row carries everything the
P4 audit and an AC-7 reproduction need:

- ids: ``trial_id``, the computed ``family_id`` (FR-E4), ``experiment_hash`` (strategy+params),
  ``protocol_hash`` (FR-H2), and the Lockbox ``dataset_id`` it relates to (P2's book);
- the **full per-fold OOS return series of the trial** (``per_fold_returns``) — the audit in P4
  is impossible without the returns of *every* trial (FR-E1, FR-F1);
- the ``ResResult`` (the undeflated row metric);
- the measurement **fingerprint** (``provenance``: snapshot id + foundation/backend versions,
  from ``FoldEvalResult.provenance``) sufficient to reproduce the metric bit-for-bit (FR-I1/AC-7);
- ``thesis`` (effect / observable / falsifier) and ``created_at`` (ISO, **injected** — never read
  from a clock inside this pure module, NFR-1).

**Append-only & atomic (FR-I2/NFR-6).** A Selection touch is RESERVED before it runs and
FINALIZED after. Both are single appended JSONL records (`os.replace` of a rewritten temp file —
the only safe atomic write on top of an append-only file). A crash *after* reserve but *before*
finalize leaves a RESERVED record with no FINALIZED partner: the look still **counts as spent**
(``charged_trial_ids`` includes it), so a crash can never yield a silent un-ledgered look. Rows
are never mutated; a finalize is a new record keyed to the reservation's ``trial_id``.

**Lossless numpy round-trip (AC-7).** ``FoldReturns`` arrays are serialized as base64 of their
**raw little-endian bytes** plus dtype + shape, so a persisted row reconstructs ``values`` and
``timestamps`` bit-for-bit (no float-string precision loss).

Pure of ``quant_strategies``. numpy + json + base64 + hashlib only.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence

import numpy as np

from harness.foundation import FoldReturns
from harness.objective.gates import GateOutcome
from harness.objective.res import ResResult

# JSONL record kinds. A trial is one RESERVED record followed (on success) by one FINALIZED
# record with the same trial_id. RESERVED-without-FINALIZED is a charged-but-crashed look.
_KIND_RESERVED = "reserved"
_KIND_FINALIZED = "finalized"

_LEDGER_VERSION = "ledger-v1"


# --------------------------------------------------------------------------- #
# The row + reservation value objects.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LedgerRow:
    """One finalized Selection look (harness-architecture §3). Append-only; never mutated."""

    trial_id: str
    family_id: str  # computed fingerprint (FR-E4), NOT the free-text thesis
    experiment_hash: str  # strategy ref + params
    protocol_hash: str  # content hash of the Protocol (FR-H2)
    thesis: str  # effect / observable / falsifier
    per_fold_returns: tuple[FoldReturns, ...]  # FULL series of EVERY trial — the audit needs these
    res: ResResult
    provenance: Mapping[str, str]  # snapshot id + versions (reproducible — AC-7)
    created_at: str  # ISO; injected, never read from a clock inside pure code
    dataset_id: str | None = None  # the Lockbox dataset (P2's book) this trial relates to


@dataclass(frozen=True)
class Reservation:
    """A RESERVED-but-not-yet-finalized Selection look (the fail-safe charge unit)."""

    trial_id: str
    family_id: str
    experiment_hash: str
    protocol_hash: str
    thesis: str
    reserved_at: str
    dataset_id: str | None = None


# --------------------------------------------------------------------------- #
# Lossless (de)serialization of numpy return series.
# --------------------------------------------------------------------------- #


def _encode_array(arr: np.ndarray) -> dict[str, object]:
    """Serialize a numpy array as base64 of its raw little-endian bytes + dtype + shape.

    Raw bytes (not a float-string list) guarantee a bit-exact round-trip (AC-7). The dtype is
    normalized to little-endian byte order so a row written on one platform reconstructs
    identically on another.
    """
    a = np.ascontiguousarray(arr)
    # Normalize to little-endian so the on-disk bytes (and the reconstruction) are platform-stable.
    if a.dtype.byteorder == ">":
        a = a.astype(a.dtype.newbyteorder("<"))
    return {
        "dtype": a.dtype.str.replace(">", "<"),
        "shape": list(a.shape),
        "b64": base64.b64encode(a.tobytes()).decode("ascii"),
    }


def _decode_array(payload: Mapping[str, object]) -> np.ndarray:
    raw = base64.b64decode(payload["b64"])  # type: ignore[arg-type]
    arr = np.frombuffer(raw, dtype=np.dtype(payload["dtype"]))  # type: ignore[arg-type]
    return arr.reshape(tuple(payload["shape"])).copy()  # copy: frombuffer is read-only


def _encode_fold(fr: FoldReturns) -> dict[str, object]:
    out: dict[str, object] = {
        "timestamps": _encode_array(np.asarray(fr.timestamps)),
        "values": _encode_array(np.asarray(fr.values, dtype=np.float64)),
        "periods_per_year": float(fr.periods_per_year),
    }
    if fr.by_symbol:
        out["by_symbol"] = {sym: _encode_fold(leg) for sym, leg in fr.by_symbol.items()}
    return out


def _decode_fold(payload: Mapping[str, object]) -> FoldReturns:
    by_symbol = None
    if "by_symbol" in payload:
        by_symbol = {
            sym: _decode_fold(leg) for sym, leg in payload["by_symbol"].items()  # type: ignore[union-attr]
        }
    return FoldReturns(
        timestamps=_decode_array(payload["timestamps"]),  # type: ignore[arg-type]
        values=_decode_array(payload["values"]),  # type: ignore[arg-type]
        periods_per_year=float(payload["periods_per_year"]),  # type: ignore[arg-type]
        by_symbol=by_symbol,
    )


def _encode_gate(g: GateOutcome) -> dict[str, object]:
    return {
        "name": g.name,
        "passed": bool(g.passed),
        "value": None if g.value is None else float(g.value),
        "threshold": None if g.threshold is None else float(g.threshold),
        "detail": g.detail,
    }


def _decode_gate(payload: Mapping[str, object]) -> GateOutcome:
    return GateOutcome(
        name=str(payload["name"]),
        passed=bool(payload["passed"]),
        value=None if payload["value"] is None else float(payload["value"]),  # type: ignore[arg-type]
        threshold=None if payload["threshold"] is None else float(payload["threshold"]),  # type: ignore[arg-type]
        detail=str(payload.get("detail", "")),
    )


def _encode_res(res: ResResult) -> dict[str, object]:
    return {
        "feasible": bool(res.feasible),
        "gate_results": {name: _encode_gate(g) for name, g in res.gate_results.items()},
        "rank_sharpe": None if res.rank_sharpe is None else float(res.rank_sharpe),
        "per_fold_sharpe": [float(s) for s in res.per_fold_sharpe],
        "residual_info_ratio": (
            None if res.residual_info_ratio is None else float(res.residual_info_ratio)
        ),
        "psr": None if res.psr is None else float(res.psr),
    }


def _decode_res(payload: Mapping[str, object]) -> ResResult:
    return ResResult(
        feasible=bool(payload["feasible"]),
        gate_results={
            name: _decode_gate(g) for name, g in payload["gate_results"].items()  # type: ignore[union-attr]
        },
        rank_sharpe=None if payload["rank_sharpe"] is None else float(payload["rank_sharpe"]),  # type: ignore[arg-type]
        per_fold_sharpe=tuple(float(s) for s in payload["per_fold_sharpe"]),  # type: ignore[union-attr]
        residual_info_ratio=(
            None if payload["residual_info_ratio"] is None else float(payload["residual_info_ratio"])  # type: ignore[arg-type]
        ),
        psr=None if payload["psr"] is None else float(payload["psr"]),  # type: ignore[arg-type]
    )


def _encode_row(row: LedgerRow) -> dict[str, object]:
    return {
        "kind": _KIND_FINALIZED,
        "v": _LEDGER_VERSION,
        "trial_id": row.trial_id,
        "family_id": row.family_id,
        "experiment_hash": row.experiment_hash,
        "protocol_hash": row.protocol_hash,
        "thesis": row.thesis,
        "per_fold_returns": [_encode_fold(fr) for fr in row.per_fold_returns],
        "res": _encode_res(row.res),
        "provenance": dict(row.provenance),
        "created_at": row.created_at,
        "dataset_id": row.dataset_id,
    }


def _decode_row(payload: Mapping[str, object]) -> LedgerRow:
    return LedgerRow(
        trial_id=str(payload["trial_id"]),
        family_id=str(payload["family_id"]),
        experiment_hash=str(payload["experiment_hash"]),
        protocol_hash=str(payload["protocol_hash"]),
        thesis=str(payload["thesis"]),
        per_fold_returns=tuple(_decode_fold(f) for f in payload["per_fold_returns"]),  # type: ignore[union-attr]
        res=_decode_res(payload["res"]),  # type: ignore[arg-type]
        provenance=dict(payload["provenance"]),  # type: ignore[arg-type]
        created_at=str(payload["created_at"]),
        dataset_id=None if payload.get("dataset_id") is None else str(payload["dataset_id"]),
    )


# --------------------------------------------------------------------------- #
# The append-only ledger.
# --------------------------------------------------------------------------- #


class LedgerError(RuntimeError):
    """Raised on a ledger consistency violation (e.g. finalizing an unknown reservation)."""


class TrialLedger:
    """An append-only JSONL trial ledger (the campaign system of record).

    In-memory by default; pass ``path`` to persist across processes (the campaign lifecycle).
    The append-only invariant is mechanical: ``reserve`` and ``finalize`` only ever *append* a
    record; nothing rewrites or deletes an existing one.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._records: list[dict[str, object]] = []
        if self._path is not None and self._path.is_file():
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                self._records.append(json.loads(line))

    def _append(self, record: Mapping[str, object]) -> None:
        """Append one JSONL record. Atomic on disk: rewrite a temp file with all records +
        the new one, then ``os.replace`` over the ledger (the safe atomic primitive; a partial
        write never replaces the live file). In-memory then mirrors the persisted state."""
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            existing = self._path.read_text(encoding="utf-8") if self._path.is_file() else ""
            tmp.write_text(existing + line + "\n", encoding="utf-8")
            os.replace(tmp, self._path)  # atomic on POSIX
        self._records.append(json.loads(line))

    # -- reserve / finalize (the fail-safe touch protocol, FR-I2/NFR-6) --

    def reserve(
        self,
        *,
        trial_id: str,
        family_id: str,
        experiment_hash: str,
        protocol_hash: str,
        thesis: str,
        reserved_at: str,
        dataset_id: str | None = None,
    ) -> Reservation:
        """Append a RESERVED record BEFORE the Selection look runs.

        From this moment the look counts as charged (``charged_trial_ids`` includes it), so a
        crash before ``finalize`` cannot yield a silent un-ledgered look (fail-safe toward
        "charged + logged"). ``trial_id`` must be unique.
        """
        if trial_id in self.charged_trial_ids():
            raise LedgerError(f"trial_id {trial_id!r} is already reserved (append-only, no reuse)")
        self._append(
            {
                "kind": _KIND_RESERVED,
                "v": _LEDGER_VERSION,
                "trial_id": trial_id,
                "family_id": family_id,
                "experiment_hash": experiment_hash,
                "protocol_hash": protocol_hash,
                "thesis": thesis,
                "reserved_at": reserved_at,
                "dataset_id": dataset_id,
            }
        )
        return Reservation(
            trial_id=trial_id,
            family_id=family_id,
            experiment_hash=experiment_hash,
            protocol_hash=protocol_hash,
            thesis=thesis,
            reserved_at=reserved_at,
            dataset_id=dataset_id,
        )

    def finalize(
        self,
        reservation: Reservation,
        *,
        per_fold_returns: Sequence[FoldReturns],
        res: ResResult,
        provenance: Mapping[str, str],
        created_at: str,
    ) -> LedgerRow:
        """Append the FINALIZED record for a prior reservation (the full row).

        The finalized row inherits the reservation's ids/thesis/dataset (so the charge and the
        evidence are one trial), adds the per-fold returns + ``ResResult`` + fingerprint, and is
        keyed to the reservation's ``trial_id``. Finalizing an unknown or already-finalized
        reservation raises (append-only: a row is written exactly once).
        """
        if reservation.trial_id not in self._reserved_ids():
            raise LedgerError(
                f"cannot finalize trial_id {reservation.trial_id!r}: no matching reservation"
            )
        if reservation.trial_id in self._finalized_ids():
            raise LedgerError(
                f"trial_id {reservation.trial_id!r} already finalized (rows are never rewritten)"
            )
        row = LedgerRow(
            trial_id=reservation.trial_id,
            family_id=reservation.family_id,
            experiment_hash=reservation.experiment_hash,
            protocol_hash=reservation.protocol_hash,
            thesis=reservation.thesis,
            per_fold_returns=tuple(per_fold_returns),
            res=res,
            provenance=dict(provenance),
            created_at=created_at,
            dataset_id=reservation.dataset_id,
        )
        self._append(_encode_row(row))
        return row

    # -- read API (P4's audit consumes this) --

    def _reserved_ids(self) -> set[str]:
        return {r["trial_id"] for r in self._records if r["kind"] == _KIND_RESERVED}  # type: ignore[misc]

    def _finalized_ids(self) -> set[str]:
        return {r["trial_id"] for r in self._records if r["kind"] == _KIND_FINALIZED}  # type: ignore[misc]

    def charged_trial_ids(self) -> set[str]:
        """Every trial that has spent a look: any RESERVED record (finalized or not).

        This is the budget-charge set (FR-I2/NFR-6): a reserved-but-crashed look is still here,
        so it counts against the budget and is never silently lost.
        """
        return self._reserved_ids()

    def charged_count(self) -> int:
        """How many Selection looks have been charged (the budget consumption)."""
        return len(self.charged_trial_ids())

    def rows(self) -> list[LedgerRow]:
        """All FINALIZED rows in append order — the audit population (FR-F1).

        P4's Romano-Wolf / PBO reads ``row.per_fold_returns`` (the full OOS series of every
        trial) and groups by ``row.family_id`` for the top-K rule.
        """
        return [_decode_row(r) for r in self._records if r["kind"] == _KIND_FINALIZED]

    def rows_by_family(self) -> dict[str, list[LedgerRow]]:
        """Finalized rows grouped by computed ``family_id`` (for P4's top-K-per-family)."""
        grouped: dict[str, list[LedgerRow]] = {}
        for row in self.rows():
            grouped.setdefault(row.family_id, []).append(row)
        return grouped

    def pending_reservations(self) -> list[str]:
        """trial_ids that were reserved but never finalized — charged-but-crashed looks.

        Observability (NFR-5): these consumed budget but produced no row (e.g. a mid-touch
        crash). They are intentionally NOT auto-finalized; they remain visible as spent.
        """
        return sorted(self._reserved_ids() - self._finalized_ids())

    def __iter__(self) -> Iterator[LedgerRow]:
        return iter(self.rows())

    def __len__(self) -> int:
        return len(self._finalized_ids())
