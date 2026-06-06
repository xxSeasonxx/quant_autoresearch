"""Stage-1 gate unit tests — concentration + correlation-aware effective-breadth.

The effective-breadth gate is what kills the "ADA-disguised-as-basket" trick (AC-1
partial): co-moving legs collapse to N_eff ≈ 1.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.objective import gates
from harness.testing import make_returns


def _basket(series_by_symbol: dict[str, np.ndarray]) -> dict:
    return {s: make_returns(v) for s, v in series_by_symbol.items()}


def test_evidence_gate_min_trades():
    assert gates.evidence_gate(50, 30).passed
    assert not gates.evidence_gate(10, 30).passed


def test_effective_breadth_one_for_perfectly_comoving_basket():
    """ADA/XRP/AVAX all tracking one underlying ⇒ N_eff ≈ 1."""
    rng = np.random.default_rng(0)
    base = 0.01 * rng.standard_normal(400)
    basket = _basket(
        {
            "ADA": base,
            "XRP": base * 1.01 + 1e-9 * rng.standard_normal(400),
            "AVAX": base * 0.99 + 1e-9 * rng.standard_normal(400),
        }
    )
    n_eff = gates.effective_breadth(basket)
    assert n_eff == pytest.approx(1.0, abs=0.1)


def test_effective_breadth_k_for_independent_basket():
    """Three independent legs ⇒ N_eff ≈ 3."""
    rng = np.random.default_rng(1)
    basket = _basket(
        {
            "A": 0.01 * rng.standard_normal(800),
            "B": 0.01 * rng.standard_normal(800),
            "C": 0.01 * rng.standard_normal(800),
        }
    )
    n_eff = gates.effective_breadth(basket)
    assert n_eff == pytest.approx(3.0, abs=0.4)


def test_effective_breadth_gate_bounces_comoving_basket():
    rng = np.random.default_rng(2)
    base = 0.01 * rng.standard_normal(400)
    basket = _basket({"ADA": base, "XRP": base * 1.02, "AVAX": base * 0.98})
    outcome = gates.effective_breadth_gate(basket, min_breadth=2.0)
    assert not outcome.passed
    assert outcome.value == pytest.approx(1.0, abs=0.1)


def test_effective_breadth_gate_passes_diversified_basket():
    rng = np.random.default_rng(3)
    basket = _basket(
        {
            "A": 0.01 * rng.standard_normal(800),
            "B": 0.01 * rng.standard_normal(800),
            "C": 0.01 * rng.standard_normal(800),
        }
    )
    assert gates.effective_breadth_gate(basket, min_breadth=2.0).passed


def test_concentration_gate_flags_dominant_symbol():
    """ADA carries ~95% of PnL ⇒ concentration gate fails."""
    big = np.full(200, 0.01)  # strong steady PnL
    tiny = np.full(200, 0.0002)
    basket = _basket({"ADA": big, "XRP": tiny, "AVAX": tiny})
    outcome = gates.concentration_gate(basket, max_share=0.5)
    assert not outcome.passed
    assert outcome.value > 0.9


def test_concentration_gate_passes_balanced_basket():
    rng = np.random.default_rng(4)
    basket = _basket(
        {
            "A": 0.005 + 0.01 * rng.standard_normal(400),
            "B": 0.005 + 0.01 * rng.standard_normal(400),
            "C": 0.005 + 0.01 * rng.standard_normal(400),
        }
    )
    assert gates.concentration_gate(basket, max_share=0.6).passed


def test_no_decomposition_treated_as_single_symbol():
    """Omitting the per-symbol decomposition cannot disguise a single-symbol bet."""
    assert not gates.concentration_gate(None, max_share=0.5).passed
    assert not gates.effective_breadth_gate(None, min_breadth=2.0).passed
