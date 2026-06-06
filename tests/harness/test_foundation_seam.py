"""AC-10 (boundary) + the FoundationGateway seam contract (harness-architecture §2).

The judgment layer depends ONLY on the seam and never imports quant_strategies. The
seam types/shape match §2 exactly, and FakeFoundationGateway satisfies the protocol.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import numpy as np

import harness
from harness.foundation import (
    FoldEvalResult,
    FoldReturns,
    FoundationGateway,
    QuickRunResult,
)
from harness.testing import FakeFoundationGateway, make_returns

HARNESS_DIR = Path(harness.__file__).parent


def _harness_module_files() -> list[Path]:
    files = []
    for mod in pkgutil.walk_packages([str(HARNESS_DIR)], prefix="harness."):
        spec = importlib.util.find_spec(mod.name)
        if spec and spec.origin and spec.origin.endswith(".py"):
            files.append(Path(spec.origin))
    files.append(HARNESS_DIR / "__init__.py")
    return files


def test_ac10_no_harness_module_imports_quant_strategies():
    """Dependency Inversion: the judgment layer must not import the engine (FR-J1).

    `harness.testing` is a test double and is exempt-by-design — but it does not import
    quant_strategies either, so we assert the whole package is clean.
    """
    offenders = []
    for path in _harness_module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "quant_strategies":
                        offenders.append((path.name, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "quant_strategies":
                    offenders.append((path.name, node.module))
    assert not offenders, f"harness modules import quant_strategies: {offenders}"


def test_fold_returns_shape_matches_contract():
    fr = make_returns([0.01, -0.02, 0.03])
    assert isinstance(fr.timestamps, np.ndarray)
    assert fr.timestamps.dtype == np.dtype("datetime64[ns]")
    assert isinstance(fr.values, np.ndarray)
    assert fr.values.dtype == np.float64
    assert isinstance(fr.periods_per_year, float)
    # by_symbol is optional.
    assert fr.by_symbol is None
    fr2 = make_returns([0.01], by_symbol={"A": make_returns([0.01])})
    assert isinstance(fr2.by_symbol["A"], FoldReturns)


def test_quick_run_result_fields_match_contract():
    fields = set(QuickRunResult.__dataclass_fields__)
    assert fields == {
        "valid",
        "causal_ok",
        "in_sample_metric",
        "trade_count",
        "slices",
        "failure_stage",
    }


def test_fold_eval_result_fields_match_contract():
    fields = set(FoldEvalResult.__dataclass_fields__)
    assert fields == {
        "succeeded",
        "causal_ok",
        "returns",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "trade_count",
        "worst_period_return",
        "provenance",
        "failure_stage",
    }


def test_fake_gateway_satisfies_protocol():
    gw = FakeFoundationGateway(quick_metric_fn=lambda e: 1.0)
    assert isinstance(gw, FoundationGateway)  # runtime-checkable structural conformance


def test_fake_gateway_evaluate_returns_injected_fold_results():
    r1 = FoldEvalResult(
        succeeded=True,
        causal_ok=True,
        returns=make_returns([0.01, 0.02]),
        sharpe=1.2,
        sortino=1.5,
        calmar=0.8,
        max_drawdown=-0.1,
        trade_count=50,
        worst_period_return=-0.02,
        provenance={"snapshot": "s1", "foundation": "v1"},
        failure_stage=None,
    )
    gw = FakeFoundationGateway(eval_results=[r1])
    out = gw.evaluate(object(), object(), ("a", "b"))
    assert out is r1
    assert out.provenance["snapshot"] == "s1"
