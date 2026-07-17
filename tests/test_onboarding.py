from __future__ import annotations

from pathlib import Path
import json
import re

import pytest

import loop
from onboarding import build_protocol_proposal, protocol_sha256, write_protocol_proposal
from universe_resolver import universe_payload_sha256


def _protocol_text() -> str:
    return """
strategy_path = "strategy.py"
strategy_id = "example"

[data]
kind = "crypto_perp_funding"
symbols = ["BTC-PERP"]
start = "2025-01-01"
end = "2025-02-01"
load_end = "2025-02-08"

[fill_model]
price = "close"
entry_lag_bars = 1

[cost_model]
fee_bps_per_side = 1.0
slippage_bps_per_side = 1.0

[capacity_model]
mode = "adv_impact"
portfolio_notional = 1000000.0
adv_lookback_bars = 1440
adv_min_observations = 60
max_bar_participation = 0.50
max_adv_participation = 0.25
impact_coefficient_bps = 10.0
impact_exponent = 0.5

[leverage_budget]
max_gross_exposure = 1.0
max_net_exposure = 1.0

[risk_budget]
mode = "calibrate_vol"
annualization_periods_per_year = 525600
target_volatility = 0.15

[output]
results_dir = "results"
artifact_profile = "diagnostic"
quick_checks = true
causality_check = "micro"
micro_probe_limit = 40
micro_timeout_seconds = 600.0
diagnostic_sample_trades = 5
foundation_subwindows = 3
foundation_cost_stress_multiplier = 2.0

[loop]
plateau_patience = 5
max_iterations = 10
min_abs_improvement = 0.001
min_rel_improvement = 0.0
baseline_grace_iterations = 3

[objective]
kind = "return_lcb_subwindow"
subwindows = 3
psr_hurdle_sharpe = 0.0

[gates]
min_trades = 10
min_return_sample_count = 100
min_effective_sample_size = 50.0
max_symbol_concentration = 0.75
min_cost_stress_return_retention = 0.5
max_abs_drawdown = 0.2
score_haircut_se = 2.8
max_components = 3
max_params = 10
""".strip() + "\n"


def _brief_text(
    *,
    mechanism: str = "Funding crowding mean reverts after large positive prints.",
    falsifier: str = "No stable return after costs across subwindows.",
    symbols: str | None = '"BTC-PERP", "ETH-PERP", "SOL-PERP"',
    universe_artifact: str = "",
    dataset: str = "crypto_perp_minute",
    exclusions: str = '"illiquid venues"',
    max_iterations: int = 50,
    target_volatility: float = 0.18,
    max_abs_drawdown: float = 0.22,
) -> str:
    universe_lines = ""
    if symbols is not None:
        universe_lines += f"symbols = [{symbols}]\n"
    if universe_artifact:
        universe_lines += f"universe_artifact = {universe_artifact!r}\n"
    return f"""
# Test Brief

```toml protocol-brief
mechanism = {mechanism!r}
observable = "funding prints and mark-price bars available before decision time"
falsifier = {falsifier!r}
horizon = "intraday to multi-day"
decision_cadence = "hourly rebalance, multi-day hold"
data_needs = ["funding events", "minute mark bars", "volume for capacity"]
data_kind = "crypto_perp_funding"
dataset = {dataset!r}
train_start = "2024-07-01"
train_end = "2025-12-31"
load_start = "2024-06-24"
load_end = "2026-01-07"
bar_cadence = "1m"
annualization_periods_per_year = 525600
{universe_lines.rstrip()}
capital_notional = 2500000.0
adv_lookback_bars = 2880
adv_min_observations = 120
max_bar_participation = 0.25
max_adv_participation = 0.15
impact_coefficient_bps = 12.0
impact_exponent = 0.6
max_gross_exposure = 1.5
max_net_exposure = 1.0
risk_budget_mode = "calibrate_vol"
target_volatility = {target_volatility}
max_abs_drawdown = {max_abs_drawdown}
objective_subwindows = 6
min_trades = 180
min_return_sample_count = 200
min_effective_sample_size = 80.0
max_symbol_concentration = 0.60
min_cost_stress_return_retention = 0.55
max_iterations = {max_iterations}
baseline_grace_iterations = 40
plateau_patience = 30
min_abs_improvement = 0.002
min_rel_improvement = 0.01
max_components = 4
max_params = 12
exclusions = [{exclusions}]
editable_params = ["lookback", "threshold"]
baseline_expectations = "Baseline may fail breadth before the universe resolver exists."
```
"""


def _write_universe_artifact(
    path: Path,
    symbols: list[str],
    *,
    exclusions: list[str] | None = None,
) -> str:
    resolved_exclusions = exclusions or []
    payload: dict[str, object] = {
        "schema_version": 1,
        "created_at": "2026-06-16T00:00:00+00:00",
        "rule": {
            "data_kind": "crypto_perp_funding",
            "dataset": "crypto_perp_1min_with_funding",
            "start": "2024-07-01",
            "end": "2025-12-31",
            "exclusions": resolved_exclusions,
            "readiness_options": {
                "max_lag_days": None,
                "require_research_ready": False,
                "allowed_derived_statuses": ["research_ready"],
                "capacity_model": "adv_impact",
            },
        },
        "resolved_symbols": symbols,
        "excluded_symbols": [],
        "data_snapshot": {
            "dataset": "crypto_perp_1min_with_funding",
            "dataset_status": {"status": "usable_with_caveats"},
            "derived_health": {"sha256": "digest", "symbol_count": len(symbols)},
            "snapshot_sha256": "snapshot",
        },
        "resolver_sha256": "",
    }
    payload["resolver_sha256"] = universe_payload_sha256(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return str(payload["resolver_sha256"])


def _write_setup(tmp_path: Path) -> tuple[Path, Path]:
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(_brief_text())
    return protocol_path, brief_path


def test_protocol_proposal_derives_mandate_values(tmp_path: Path):
    protocol_path, brief_path = _write_setup(tmp_path)

    proposal = build_protocol_proposal(brief_path, protocol_path=protocol_path)

    recommended = proposal.recommended_protocol
    assert recommended["data"]["kind"] == "crypto_perp_funding"
    assert recommended["data"]["dataset"] == "crypto_perp_minute"
    assert recommended["data"]["start"] == "2024-07-01"
    assert recommended["data"]["end"] == "2025-12-31"
    assert recommended["data"]["load_start"] == "2024-06-24"
    assert recommended["data"]["load_end"] == "2026-01-07"
    assert recommended["risk_budget"]["annualization_periods_per_year"] == 525600
    assert recommended["loop"]["max_iterations"] == 50
    assert recommended["loop"]["baseline_grace_iterations"] == 40
    assert recommended["loop"]["plateau_patience"] == 30
    assert recommended["loop"]["min_abs_improvement"] == 0.002
    assert recommended["loop"]["min_rel_improvement"] == 0.01
    assert recommended["gates"]["score_haircut_se"] == 2.0
    assert recommended["risk_budget"]["target_volatility"] == 0.18
    assert recommended["leverage_budget"]["max_gross_exposure"] == 1.5
    assert recommended["gates"]["max_abs_drawdown"] == 0.22
    assert recommended["gates"]["min_trades"] == 180
    assert recommended["gates"]["min_return_sample_count"] == 200
    assert recommended["gates"]["min_effective_sample_size"] == 80.0
    assert recommended["gates"]["max_symbol_concentration"] == 0.60
    assert recommended["gates"]["min_cost_stress_return_retention"] == 0.55
    assert recommended["gates"]["max_components"] == 4
    assert recommended["gates"]["max_params"] == 12
    assert recommended["objective"]["subwindows"] == 6
    assert recommended["data"]["symbols"] == ["BTC-PERP", "ETH-PERP", "SOL-PERP"]
    assert recommended["capacity_model"]["portfolio_notional"] == 2500000.0
    assert recommended["capacity_model"]["adv_lookback_bars"] == 2880
    assert recommended["capacity_model"]["adv_min_observations"] == 120
    assert recommended["capacity_model"]["max_bar_participation"] == 0.25
    assert recommended["capacity_model"]["max_adv_participation"] == 0.15
    assert recommended["capacity_model"]["impact_coefficient_bps"] == 12.0
    assert recommended["capacity_model"]["impact_exponent"] == 0.6
    assert recommended["output"]["causality_check"] == "micro"
    assert proposal.thesis["editable_params"] == ["lookback", "threshold"]
    assert proposal.approval["approved"] is False


def test_protocol_proposal_accepts_universe_artifact_without_explicit_symbols(
    tmp_path: Path,
):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())
    artifact_path = tmp_path / ".autoresearch" / "universe" / "latest.json"
    artifact_hash = _write_universe_artifact(
        artifact_path,
        ["BTC-PERP", "ETH-PERP", "SOL-PERP"],
    )
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(
        _brief_text(
            symbols=None,
            universe_artifact=str(artifact_path),
            dataset="crypto_perp_1min_with_funding",
            exclusions="",
        )
    )

    proposal = build_protocol_proposal(brief_path, protocol_path=protocol_path)

    assert proposal.recommended_protocol["data"]["symbols"] == [
        "BTC-PERP",
        "ETH-PERP",
        "SOL-PERP",
    ]
    assert proposal.thesis["universe_artifact"] == str(artifact_path)
    assert proposal.thesis["universe_resolver_sha256"] == artifact_hash
    assert any("eligibility-based" in warning for warning in proposal.warnings)


def test_protocol_proposal_accepts_matching_symbols_and_universe_artifact(
    tmp_path: Path,
):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())
    artifact_path = tmp_path / ".autoresearch" / "universe" / "latest.json"
    _write_universe_artifact(artifact_path, ["BTC-PERP", "ETH-PERP", "SOL-PERP"])
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(
        _brief_text(
            symbols='"BTC-PERP", "ETH-PERP", "SOL-PERP"',
            universe_artifact=str(artifact_path),
            dataset="crypto_perp_1min_with_funding",
            exclusions="",
        )
    )

    proposal = build_protocol_proposal(brief_path, protocol_path=protocol_path)

    assert proposal.recommended_protocol["data"]["symbols"] == [
        "BTC-PERP",
        "ETH-PERP",
        "SOL-PERP",
    ]


def test_protocol_proposal_rejects_mismatching_symbols_and_universe_artifact(
    tmp_path: Path,
):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())
    artifact_path = tmp_path / ".autoresearch" / "universe" / "latest.json"
    _write_universe_artifact(artifact_path, ["BTC-PERP", "ETH-PERP", "SOL-PERP"])
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(
        _brief_text(
            symbols='"BTC-PERP", "ETH-PERP"',
            universe_artifact=str(artifact_path),
            dataset="crypto_perp_1min_with_funding",
            exclusions="",
        )
    )

    with pytest.raises(
        ValueError,
        match="symbols must exactly match universe_artifact resolved_symbols",
    ):
        build_protocol_proposal(brief_path, protocol_path=protocol_path)


def test_protocol_proposal_rejects_stale_universe_artifact_rule(tmp_path: Path):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())
    artifact_path = tmp_path / ".autoresearch" / "universe" / "latest.json"
    _write_universe_artifact(artifact_path, ["BTC-PERP", "ETH-PERP", "SOL-PERP"])
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(
        _brief_text(
            symbols=None,
            universe_artifact=str(artifact_path),
        )
    )

    with pytest.raises(
        ValueError,
        match="universe_artifact rule.dataset must match dataset",
    ):
        build_protocol_proposal(brief_path, protocol_path=protocol_path)


def test_protocol_proposal_rejects_malformed_universe_artifact(tmp_path: Path):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())
    artifact_path = tmp_path / ".autoresearch" / "universe" / "latest.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text('{"schema_version": 1}\n')
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(
        _brief_text(
            symbols=None,
            universe_artifact=str(artifact_path),
            dataset="crypto_perp_1min_with_funding",
            exclusions="",
        )
    )

    with pytest.raises(ValueError, match="universe artifact missing created_at"):
        build_protocol_proposal(brief_path, protocol_path=protocol_path)


@pytest.mark.parametrize(
    ("brief", "message"),
    [
        (_brief_text(mechanism="   "), "mechanism is required"),
        (_brief_text(falsifier=""), "falsifier is required"),
        (_brief_text(symbols=""), "symbols must include at least one symbol"),
        (_brief_text(target_volatility=float("nan")), "target_volatility must be finite"),
        (_brief_text(max_abs_drawdown=1.5), "max_abs_drawdown must be in [0, 1]"),
        (_brief_text(max_iterations=1), "max_iterations must be >= 2"),
        (
            _brief_text().replace("adv_min_observations = 120", "adv_min_observations = 3000"),
            "adv_min_observations must be <= adv_lookback_bars",
        ),
        (
            _brief_text().replace("objective_subwindows = 6", "objective_subwindows = 0"),
            "objective_subwindows must be > 0",
        ),
    ],
)
def test_protocol_proposal_rejects_invalid_briefs(
    tmp_path: Path, brief: str, message: str
):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(brief)

    with pytest.raises(ValueError, match=re.escape(message)):
        build_protocol_proposal(brief_path, protocol_path=protocol_path)


def test_propose_protocol_writes_artifacts_without_mutating_protocol(tmp_path: Path):
    protocol_path, brief_path = _write_setup(tmp_path)
    before = protocol_path.read_text()
    out = tmp_path / ".autoresearch" / "protocol_proposals" / "latest.json"

    proposal = write_protocol_proposal(
        brief_path,
        out,
        protocol_path=protocol_path,
    )

    assert protocol_path.read_text() == before
    assert out.exists()
    assert out.with_suffix(".md").exists()
    payload = json.loads(out.read_text())
    assert payload["proposal_sha256"] == proposal.proposal_sha256
    assert payload["current_protocol"]["risk_budget"]["target_volatility"] == 0.15
    assert payload["recommended_protocol"]["gates"]["score_haircut_se"] == 2.0
    markdown = out.with_suffix(".md").read_text()
    assert "| Protocol field | Current value | Recommended value | Reason |" in markdown
    assert "## Feasibility" in markdown
    assert "Approval Checklist" in markdown


def test_propose_protocol_markdown_includes_universe_artifact_hash(tmp_path: Path):
    protocol_path = tmp_path / "protocol.toml"
    protocol_path.write_text(_protocol_text())
    artifact_path = tmp_path / ".autoresearch" / "universe" / "latest.json"
    artifact_hash = _write_universe_artifact(
        artifact_path,
        ["BTC-PERP", "ETH-PERP", "SOL-PERP"],
    )
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(
        _brief_text(
            symbols=None,
            universe_artifact=str(artifact_path),
            dataset="crypto_perp_1min_with_funding",
            exclusions="",
        )
    )
    out = tmp_path / ".autoresearch" / "protocol_proposals" / "latest.json"

    write_protocol_proposal(brief_path, out, protocol_path=protocol_path)

    payload = json.loads(out.read_text())
    markdown = out.with_suffix(".md").read_text()
    assert payload["thesis"]["universe_resolver_sha256"] == artifact_hash
    assert "## Universe Resolver" in markdown
    assert artifact_hash in markdown
    assert "eligibility-based, not return-ranked" in markdown


def test_baseline_refuses_missing_unapproved_stale_and_active_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    protocol_path, brief_path = _write_setup(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    write_protocol_proposal(brief_path, proposal_path, protocol_path=protocol_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="approved proposal not found"):
        loop.baseline_once(
            mechanism="m",
            falsifier="f",
            approved_proposal=tmp_path / "missing.json",
        )

    with pytest.raises(ValueError, match="proposal is not approved"):
        loop.baseline_once(
            mechanism="m",
            falsifier="f",
            approved_proposal=proposal_path,
        )

    payload = json.loads(proposal_path.read_text())
    payload["approval"]["approved"] = True
    payload["approval"]["protocol_sha256"] = "0" * 64
    proposal_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="protocol.toml no longer matches"):
        loop.baseline_once(
            mechanism="m",
            falsifier="f",
            approved_proposal=proposal_path,
        )

    payload["approval"]["protocol_sha256"] = protocol_sha256(protocol_path)
    proposal_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (tmp_path / ".autoresearch").mkdir()
    (tmp_path / ".autoresearch" / "thesis_lock.json").write_text("{}\n")
    with pytest.raises(ValueError, match="active lifecycle state already exists"):
        loop.baseline_once(
            mechanism="m",
            falsifier="f",
            approved_proposal=proposal_path,
        )


def test_approved_baseline_delegates_to_climb_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    protocol_path, brief_path = _write_setup(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    write_protocol_proposal(brief_path, proposal_path, protocol_path=protocol_path)
    payload = json.loads(proposal_path.read_text())
    payload["approval"]["approved"] = True
    payload["approval"]["protocol_sha256"] = protocol_sha256(protocol_path)
    proposal_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_climb_once(**kwargs):
        calls.append(kwargs)
        return loop.IterationOutcome(
            status="discard",
            score=None,
            gates_passed=False,
            gates=None,
        )

    monkeypatch.setattr(loop, "climb_once", fake_climb_once)

    outcome = loop.baseline_once(
        mechanism="Funding mean reversion",
        falsifier="No post-cost robustness",
        approved_proposal=proposal_path,
    )

    assert outcome.status == "discard"
    assert calls == [
        {
            "mechanism": "Funding mean reversion",
            "falsifier": "No post-cost robustness",
        }
    ]


def test_reset_cli_requires_exact_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results.tsv").write_text("active\n")
    (tmp_path / ".autoresearch" / "quick").mkdir(parents=True)
    (tmp_path / ".autoresearch" / "quick" / "attempt-0001.toml").write_text("quick\n")
    (tmp_path / ".autoresearch" / "thesis_lock.json").write_text("{}\n")

    with pytest.raises(SystemExit):
        loop.main(["reset"])
    assert "--confirm" in capsys.readouterr().err
    assert (tmp_path / "results.tsv").exists()
    assert (tmp_path / ".autoresearch" / "thesis_lock.json").exists()

    with pytest.raises(ValueError, match="RESET-LIFECYCLE"):
        loop.main(["reset", "--confirm", "wrong"])
    assert (tmp_path / "results.tsv").exists()
    assert (tmp_path / ".autoresearch" / "thesis_lock.json").exists()


def test_reset_cli_archives_generated_lifecycle_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results.tsv").write_text("results\n")
    quick_dir = tmp_path / ".autoresearch" / "quick"
    quick_dir.mkdir(parents=True)
    (quick_dir / "attempt-0001.toml").write_text("quick\n")
    (tmp_path / ".autoresearch" / "thesis_lock.json").write_text('{"active": true}\n')
    source_files = {
        "strategy.py": "strategy\n",
        "protocol.toml": "protocol\n",
        "experiment.toml": "experiment\n",
        "rationale.md": "rationale\n",
    }
    for name, content in source_files.items():
        (tmp_path / name).write_text(content)

    assert loop.main(["reset", "--confirm", "RESET-LIFECYCLE"]) == 0

    archives = sorted((tmp_path / ".autoresearch" / "lifecycle_archive").iterdir())
    assert len(archives) == 1
    archive = archives[0]
    assert (archive / "results.tsv").read_text() == "results\n"
    assert (archive / "thesis_lock.json").read_text() == '{"active": true}\n'
    assert (archive / "quick" / "attempt-0001.toml").read_text() == "quick\n"
    assert not (tmp_path / "results.tsv").exists()
    assert not (tmp_path / ".autoresearch" / "thesis_lock.json").exists()
    assert not quick_dir.exists()
    for name, content in source_files.items():
        assert (tmp_path / name).read_text() == content


def test_reset_cli_refuses_when_no_lifecycle_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="no lifecycle state"):
        loop.main(["reset", "--confirm", "RESET-LIFECYCLE"])

    assert not (tmp_path / ".autoresearch" / "lifecycle_archive").exists()
