"""The data wall (FR-B): tiers, forward-only walk-forward, write-once Lockbox.

Pure span arithmetic over time — the harness owns fold orchestration (architecture §2),
so these modules operate on ``(start, end)`` spans and period counts, never on loaded data.
That keeps the wall deterministically unit-testable with no database and no
``quant_strategies`` call.
"""

from __future__ import annotations
