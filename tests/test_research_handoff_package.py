from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from quant_strategies.runner.config import load_config

from tools.research_handoff_package import build_researched_package


def test_builds_three_family_package_and_rewrites_configs(tmp_path: Path):
    campaign = tmp_path / "campaign"
    target_repo = tmp_path / "quant_strategies"
    target_repo.mkdir()
    source_strategy = tmp_path / "strategy.py"
    source_strategy.write_text("# current source\n")

    attempt_1 = write_attempt(campaign, 1, "time_only_exit", strategy_snapshot="# snapshot source\n")
    attempt_2 = write_attempt(campaign, 2, "entry_filter")
    attempt_3 = write_attempt(campaign, 3, "directional_subset")
    promotion_dir = campaign / "promotion_0001_demo"
    promotion_dir.mkdir()
    (promotion_dir / "trade_attribution.json").write_text(json.dumps({"trades": 3}) + "\n")

    ranking_path = write_ranking(
        tmp_path,
        campaign,
        [
            variant("variant-time", "time_only_exit", attempt_1, promotion_dir=promotion_dir),
            variant("variant-entry", "entry_filter", attempt_2),
            variant("variant-directional", "directional_subset", attempt_3),
        ],
    )

    package_dir = build_researched_package(
        campaign_dir=campaign,
        target_repo=target_repo,
        strategy_id="demo_strategy",
        ranking_path=ranking_path,
        source_strategy_path=source_strategy,
    )

    expected_family_dirs = [
        package_dir / "families" / "family_01_primary_time_only_exit",
        package_dir / "families" / "family_02_secondary_entry_filter",
        package_dir / "families" / "family_03_exploratory_directional_subset",
    ]
    for family_dir in expected_family_dirs:
        assert family_dir.is_dir()
        assert (family_dir / "variants" / "rank_01" / "strategy.py").exists()
        assert (family_dir / "variants" / "rank_01" / "config.toml").exists()
        assert (family_dir / "variants" / "rank_01" / "evidence").is_dir()

    config_path = (
        target_repo
        / "researched/demo_strategy/families/family_01_primary_time_only_exit/variants/rank_01/config.toml"
    )
    config = config_path.read_text()
    assert (
        'strategy_path = "researched/demo_strategy/families/'
        'family_01_primary_time_only_exit/variants/rank_01/strategy.py"'
    ) in config
    assert 'results_dir = "results/researched/demo_strategy/family_01_primary_time_only_exit/rank_01"' in config
    assert 'symbols = ["BTC-PERP", "ETH-PERP"]' in config

    assert (
        target_repo
        / "researched/demo_strategy/families/family_01_primary_time_only_exit/variants/rank_01/strategy.py"
    ).read_text() == "# snapshot source\n"
    assert (
        target_repo
        / "researched/demo_strategy/families/family_02_secondary_entry_filter/variants/rank_01/strategy.py"
    ).read_text() == "# current source\n"

    assert (
        target_repo
        / "researched/demo_strategy/families/family_01_primary_time_only_exit/variants/rank_01/evidence/"
        "promotion_summary.json"
    ).exists()
    assert (
        target_repo
        / "researched/demo_strategy/families/family_01_primary_time_only_exit/variants/rank_01/evidence/"
        "trade_attribution.json"
    ).exists()
    assert (
        target_repo
        / "researched/demo_strategy/families/family_02_secondary_entry_filter/variants/rank_01/evidence/"
        "attempt_0002_recent_score.json"
    ).exists()

    manifest = json.loads((package_dir / "manifest.json").read_text())
    assert manifest["ranking_method_version"] == "research_handoff_rank_v1"
    assert manifest["selected_family_ids"] == ["time_only_exit", "entry_filter", "directional_subset"]
    assert manifest["variant_ids"] == ["variant-time", "variant-entry", "variant-directional"]
    for entry in manifest["variants"]:
        variant_dir = package_dir / entry["directory"]
        assert entry["code_sha256"] == sha256(variant_dir / "strategy.py")
        assert entry["config_sha256"] == sha256(variant_dir / "config.toml")
        for evidence_file in entry["evidence_files"]:
            assert (package_dir / evidence_file).exists()

    summary = (package_dir / "notes" / "llm_research_summary.md").read_text()
    assert "initial machine-written scaffold" in summary
    assert "source JSON, config, strategy, and evidence files" in summary

    for entry in manifest["variants"]:
        load_config(package_dir / entry["directory"] / "config.toml", repo_root=target_repo)


def test_destination_collision_requires_replace(tmp_path: Path):
    campaign = tmp_path / "campaign"
    target_repo = tmp_path / "target"
    target_repo.mkdir()
    source_strategy = tmp_path / "strategy.py"
    source_strategy.write_text("# current source\n")
    attempts = [
        write_attempt(campaign, 1, "time_only_exit"),
        write_attempt(campaign, 2, "entry_filter"),
        write_attempt(campaign, 3, "directional_subset"),
    ]
    ranking_path = write_ranking(
        tmp_path,
        campaign,
        [
            variant("variant-time", "time_only_exit", attempts[0]),
            variant("variant-entry", "entry_filter", attempts[1]),
            variant("variant-directional", "directional_subset", attempts[2]),
        ],
    )

    build_researched_package(
        campaign_dir=campaign,
        target_repo=target_repo,
        strategy_id="demo_strategy",
        ranking_path=ranking_path,
        source_strategy_path=source_strategy,
    )
    with pytest.raises(FileExistsError):
        build_researched_package(
            campaign_dir=campaign,
            target_repo=target_repo,
            strategy_id="demo_strategy",
            ranking_path=ranking_path,
            source_strategy_path=source_strategy,
        )

    rebuilt = build_researched_package(
        campaign_dir=campaign,
        target_repo=target_repo,
        strategy_id="demo_strategy",
        ranking_path=ranking_path,
        source_strategy_path=source_strategy,
        replace=True,
    )
    assert (rebuilt / "manifest.json").exists()


def write_attempt(
    campaign: Path,
    attempt_id: int,
    family: str,
    *,
    strategy_snapshot: str | None = None,
) -> Path:
    attempt_dir = campaign / f"attempt_{attempt_id:04d}_{family}"
    attempt_dir.mkdir(parents=True)
    generated_dir = campaign / ".generated"
    generated_dir.mkdir(exist_ok=True)
    config_path = generated_dir / f"attempt_{attempt_id:04d}.toml"
    config_path.write_text(valid_runner_toml())
    if strategy_snapshot is not None:
        (attempt_dir / "strategy_snapshot.py").write_text(strategy_snapshot)
    (attempt_dir / "attempt_metadata.json").write_text(
        json.dumps(
            {
                "attempt": attempt_id,
                "generated_config": str(config_path.relative_to(campaign)),
                "window_id": "recent",
            }
        )
        + "\n"
    )
    (attempt_dir / "score.json").write_text(
        json.dumps({"status": "scored", "score": 0.01 * attempt_id, "trade_count": 250}) + "\n"
    )
    return attempt_dir


def valid_runner_toml() -> str:
    return """
strategy_path = "strategy.py"
strategy_id = "demo"

[data]
kind = "crypto_perp_funding"
symbols = ["BTC-PERP", "ETH-PERP"]
start = "2024-01-01"
end = "2024-04-30"
strict = true

[params]
hold_bars = 24
threshold = 1.5

[fill_model]
price = "close"
entry_lag_bars = 1
exit_lag_bars = 0

[cost_model]
fee_bps_per_side = 1.0
slippage_bps_per_side = 2.0

[output]
results_dir = "results/original"
mode = "validate"
""".lstrip()


def write_ranking(tmp_path: Path, campaign: Path, variants: list[dict[str, object]]) -> Path:
    selected_families = [
        {"family": "time_only_exit", "best_variant_id": "variant-time", "variant_count": 1},
        {"family": "entry_filter", "best_variant_id": "variant-entry", "variant_count": 1},
        {"family": "directional_subset", "best_variant_id": "variant-directional", "variant_count": 1},
    ]
    path = tmp_path / "ranking.json"
    path.write_text(
        json.dumps(
            {
                "method_version": "research_handoff_rank_v1",
                "campaign_dir": str(campaign),
                "selected_families": selected_families,
                "variants": variants,
            }
        )
        + "\n"
    )
    return path


def variant(
    variant_id: str,
    family: str,
    attempt_dir: Path,
    *,
    promotion_dir: Path | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "variant_id": variant_id,
        "family": family,
        "attempt_ids": [int(attempt_dir.name.split("_")[1])],
        "attempt_dirs": [str(attempt_dir)],
        "promotion_score": None,
        "promotion_summary": None,
        "promotion_dir": None,
    }
    if promotion_dir is not None:
        payload["promotion_score"] = 0.025
        payload["promotion_summary"] = {"attempt": 1, "promotion_score": 0.025}
        payload["promotion_dir"] = str(promotion_dir)
    return payload


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
