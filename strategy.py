"""Strategy: awaiting_next_candidate

This workbench has been reset after the prior researched strategy was handed
off to `quant_strategies/researched/`.

The next research cycle should replace this module with one scratch strategy
candidate and update `experiment.toml` accordingly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


__all__ = ["generate_signals"]


def generate_signals(bars: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> list[dict[str, object]]:
    return []
