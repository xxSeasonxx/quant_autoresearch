from __future__ import annotations

import hashlib
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
from quant_strategies.runner.config import load_config

import tools.research_handoff_package as handoff_package
from tools.research_handoff_package import (
    build_researched_package,
    build_researched_package_from_selected_results,
    build_selected_results_package,
    cleanup_results_root_after_selected_package,
    verify_researched_package,
    verify_selected_results_package,
)


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
    promotion_source_dir = promotion_dir / "windows" / "validation" / "run"
    promotion_source_dir.mkdir(parents=True)
    (promotion_source_dir / "score.json").write_text(
        json.dumps({"status": "scored", "score": 0.026, "trade_count": 300, "window_id": "validation"}) + "\n"
    )
    promotion_score = {
        "promotion_score": 0.025,
        "components": {"sharpe": 1.2, "drawdown": -0.08},
        "extra_authoritative_field": "preserved",
    }
    (promotion_dir / "promotion_score.json").write_text(json.dumps(promotion_score, indent=2) + "\n")
    (promotion_dir / "trade_attribution.json").write_text(json.dumps({"trades": 3}) + "\n")

    ranking_path = write_ranking(
        tmp_path,
        campaign,
        [
            variant(
                "variant-time",
                "time_only_exit",
                attempt_1,
                promotion_dir=promotion_dir,
                evidence_result_dirs=[promotion_source_dir],
            ),
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
    copied_promotion_score = json.loads(
        (
            target_repo
            / "researched/demo_strategy/families/family_01_primary_time_only_exit/variants/rank_01/evidence/"
            "promotion_score.json"
        ).read_text()
    )
    assert copied_promotion_score == promotion_score
    assert (
        target_repo
        / "researched/demo_strategy/families/family_01_primary_time_only_exit/variants/rank_01/evidence/"
        "trade_attribution.json"
    ).exists()
    assert (
        target_repo
        / "researched/demo_strategy/families/family_01_primary_time_only_exit/variants/rank_01/evidence/"
        "promotion_source_01_validation_run_score.json"
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


def test_cli_runs_from_script_path(tmp_path: Path):
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

    result = subprocess.run(
        [
            sys.executable,
            "tools/research_handoff_package.py",
            "--campaign",
            str(campaign),
            "--target-repo",
            str(target_repo),
            "--strategy-id",
            "demo_strategy",
            "--ranking",
            str(ranking_path),
            "--source-strategy",
            str(source_strategy),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    package_dir = target_repo / "researched" / "demo_strategy"
    assert result.stdout.strip() == str(package_dir)
    assert (package_dir / "manifest.json").exists()


def test_builds_selected_15_package_rebuilds_ledger_and_cleans_results(tmp_path: Path):
    results_root = tmp_path / "results"
    campaign = results_root / "campaign"
    source_strategy = tmp_path / "strategy.py"
    source_strategy.write_text("def generate_decisions(rows, params):\n    return []\n")
    old_result = results_root / "old_campaign"
    old_result.mkdir(parents=True)

    variants: list[dict[str, object]] = []
    attempt_id = 1
    for family_index, family in enumerate(("time_only_exit", "entry_filter", "selection_or_breadth")):
        for rank in range(1, 6):
            attempt = write_attempt(campaign, attempt_id, family)
            variants.append(
                variant(
                    f"{family}-{rank}",
                    family,
                    attempt,
                    blended_score=0.10 - family_index * 0.01 - rank * 0.001,
                    trade_count=300 + attempt_id,
                )
            )
            attempt_id += 1
    ranking_path = write_selected_ranking(tmp_path, campaign, variants)

    selected_dir = build_selected_results_package(
        results_root=results_root,
        strategy_id="demo",
        ranking_path=ranking_path,
        strategy_template_path=source_strategy,
        replace=True,
    )

    manifest = json.loads((selected_dir / "selection_manifest.json").read_text())
    assert manifest["variant_count"] == 15
    assert [family["family"] for family in manifest["families"]] == [
        "time_only_exit",
        "entry_filter",
        "selection_or_breadth",
    ]
    config_path = selected_dir / "family_01_primary_time_only_exit" / "rank_01" / "config.toml"
    config = config_path.read_text()
    assert 'strategy_path = "results/selected_15/family_01_primary_time_only_exit/rank_01/strategy.py"' in config
    assert 'results_dir = "results/new_15/family_01_primary_time_only_exit/rank_01"' in config
    assert 'artifact_profile = "full"' in config
    assert (selected_dir / "family_01_primary_time_only_exit" / "rank_01" / "source_summary.json").exists()
    assert (results_root / "new_15").is_dir()

    verified = verify_selected_results_package(results_root)
    assert verified["variant_count"] == 15

    rows = list(csv.DictReader((tmp_path / "results.tsv").read_text().splitlines(), delimiter="\t"))
    assert len(rows) == 15
    assert {row["run_kind"] for row in rows} == {"selected_legacy"}
    assert {row["status"] for row in rows} == {"selected"}
    assert all(row["result_dir"].startswith("results/selected_15/") for row in rows)

    removed = cleanup_results_root_after_selected_package(results_root)
    assert "campaign" in removed
    assert "old_campaign" in removed
    assert sorted(path.name for path in results_root.iterdir()) == ["new_15", "selected_15"]


def test_builds_researched_package_from_selected_results_and_new_15(tmp_path: Path):
    results_root = tmp_path / "results"
    target_repo = tmp_path / "quant_strategies"
    target_repo.mkdir()
    campaign = results_root / "campaign"
    source_strategy = tmp_path / "strategy.py"
    source_strategy.write_text("def generate_decisions(rows, params):\n    return []\n")

    variants: list[dict[str, object]] = []
    attempt_id = 1
    for family_index, family in enumerate(("time_only_exit", "entry_filter", "selection_or_breadth")):
        for rank in range(1, 6):
            attempt = write_attempt(campaign, attempt_id, family)
            variants.append(
                variant(
                    f"{family}-{rank}",
                    family,
                    attempt,
                    blended_score=0.10 - family_index * 0.01 - rank * 0.001,
                    trade_count=300 + attempt_id,
                )
            )
            attempt_id += 1
    ranking_path = write_selected_ranking(tmp_path, campaign, variants)
    selected_dir = build_selected_results_package(
        results_root=results_root,
        strategy_id="demo",
        ranking_path=ranking_path,
        strategy_template_path=source_strategy,
        replace=True,
    )
    selected_manifest = json.loads((selected_dir / "selection_manifest.json").read_text())
    for selected_variant in selected_manifest["variants"]:
        write_new_15_run(tmp_path, selected_variant)

    package_dir = build_researched_package_from_selected_results(
        results_root=results_root,
        target_repo=target_repo,
        strategy_id="demo",
    )

    manifest = verify_researched_package(package_dir, target_repo, expected_variant_count=15)
    assert manifest["variant_count"] == 15
    first = manifest["variants"][0]
    variant_dir = package_dir / first["directory"]
    config = (variant_dir / "config.toml").read_text()
    assert 'strategy_path = "researched/demo/families/' in config
    assert 'results_dir = "results/researched/demo/' in config
    assert first["rerun_score"] == 0.02
    assert (variant_dir / "evidence" / "new_15_locked_recent_2026" / "score.json").exists()
    assert (variant_dir / "evidence" / "new_15_locked_recent_2026" / "decision_records.jsonl").exists()
    assert not (variant_dir / "evidence" / "new_15_locked_recent_2026" / "engine_request.json").exists()


def test_selected_15_replace_preserves_existing_package_when_new_build_fails(tmp_path: Path):
    results_root = tmp_path / "results"
    existing_selected = results_root / "selected_15"
    existing_selected.mkdir(parents=True)
    (existing_selected / "selection_manifest.json").write_text('{"keep": true}\n')
    source_strategy = tmp_path / "strategy.py"
    source_strategy.write_text("def generate_decisions(rows, params):\n    return []\n")
    bad_ranking = tmp_path / "bad_ranking.json"
    bad_ranking.write_text(
        json.dumps(
            {
                "method_version": "research_handoff_rank_v1",
                "campaign_dir": str(results_root / "missing_campaign"),
                "selected_families": [
                    {"family": "time_only_exit", "best_variant_id": "missing", "variant_count": 1},
                ],
                "variants": [],
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError):
        build_selected_results_package(
            results_root=results_root,
            strategy_id="demo",
            ranking_path=bad_ranking,
            strategy_template_path=source_strategy,
            replace=True,
        )

    assert (existing_selected / "selection_manifest.json").read_text() == '{"keep": true}\n'


def test_selected_15_replace_restores_backup_when_final_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    results_root = tmp_path / "results"
    selected_dir = results_root / "selected_15"
    staged_dir = tmp_path / "staged" / "selected_15"
    selected_dir.mkdir(parents=True)
    staged_dir.mkdir(parents=True)
    (selected_dir / "selection_manifest.json").write_text('{"old": true}\n')
    (staged_dir / "selection_manifest.json").write_text('{"new": true}\n')
    real_move = handoff_package.shutil.move

    def flaky_move(src: str, dst: str):
        if Path(src) == staged_dir:
            raise OSError("simulated final move failure")
        return real_move(src, dst)

    monkeypatch.setattr(handoff_package.shutil, "move", flaky_move)

    with pytest.raises(OSError, match="simulated final move failure"):
        handoff_package._replace_selected_dir(selected_dir, staged_dir, results_root)

    assert (selected_dir / "selection_manifest.json").read_text() == '{"old": true}\n'
    assert not list(results_root.glob(".selected_15_backup_*"))


def test_verify_selected_15_rejects_ledger_that_does_not_match_manifest(tmp_path: Path):
    results_root = tmp_path / "results"
    campaign = results_root / "campaign"
    source_strategy = tmp_path / "strategy.py"
    source_strategy.write_text("def generate_decisions(rows, params):\n    return []\n")
    variants: list[dict[str, object]] = []
    attempt_id = 1
    for family_index, family in enumerate(("time_only_exit", "entry_filter", "selection_or_breadth")):
        for rank in range(1, 6):
            attempt = write_attempt(campaign, attempt_id, family)
            variants.append(
                variant(
                    f"{family}-{rank}",
                    family,
                    attempt,
                    blended_score=0.10 - family_index * 0.01 - rank * 0.001,
                    trade_count=300 + attempt_id,
                )
            )
            attempt_id += 1
    ranking_path = write_selected_ranking(tmp_path, campaign, variants)

    build_selected_results_package(
        results_root=results_root,
        strategy_id="demo",
        ranking_path=ranking_path,
        strategy_template_path=source_strategy,
        replace=True,
    )
    lines = (tmp_path / "results.tsv").read_text().splitlines()
    columns = lines[1].split("\t")
    result_dir_index = lines[0].split("\t").index("result_dir")
    columns[result_dir_index] = "results/selected_15/wrong"
    lines[1] = "\t".join(columns)
    (tmp_path / "results.tsv").write_text("\n".join(lines) + "\n")

    with pytest.raises(ValueError, match="selection manifest"):
        cleanup_results_root_after_selected_package(results_root)


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


def write_new_15_run(repo_root: Path, selected_variant: dict[str, object]) -> Path:
    rank_dir = repo_root / str(selected_variant["new_result_dir"])
    run_dir = rank_dir / "2026-05-27T000000Z-demo"
    run_dir.mkdir(parents=True)
    score = {
        "status": "scored",
        "score": 0.02,
        "raw_net_return": 2.4,
        "trade_count": 321,
        "window_id": "locked_recent_2026",
    }
    for name, payload in {
        "score.json": score,
        "summary.json": {"status": "ok"},
        "evidence.json": {"validation_report": {"passed": True}},
        "data_manifest.json": {"rows": 10},
        "run_manifest.json": {"run": "demo"},
        "new_15_metadata.json": {"attempt": 16},
    }.items():
        (run_dir / name).write_text(json.dumps(payload) + "\n")
    (run_dir / "notes.md").write_text("notes\n")
    (run_dir / "signals.csv").write_text("timestamp,symbol\n")
    (run_dir / "decision_records.jsonl").write_text("{}\n")
    (run_dir / "strategy_snapshot.py").write_text("def generate_decisions(rows, params):\n    return []\n")
    (run_dir / "engine_request.json").write_text("{}\n")
    return run_dir


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


def write_selected_ranking(tmp_path: Path, campaign: Path, variants: list[dict[str, object]]) -> Path:
    selected_families = [
        {"family": "time_only_exit", "best_variant_id": "time_only_exit-1", "variant_count": 5},
        {"family": "entry_filter", "best_variant_id": "entry_filter-1", "variant_count": 5},
        {"family": "selection_or_breadth", "best_variant_id": "selection_or_breadth-1", "variant_count": 5},
    ]
    path = tmp_path / "selected_ranking.json"
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
    evidence_result_dirs: list[Path] | None = None,
    blended_score: float = 0.01,
    trade_count: int = 250,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "variant_id": variant_id,
        "family": family,
        "attempt_ids": [int(attempt_dir.name.split("_")[1])],
        "attempt_dirs": [str(attempt_dir)],
        "base_score": blended_score,
        "blended_score": blended_score,
        "cost_stress_score": None,
        "promotion_score": None,
        "promotion_summary": None,
        "promotion_dir": None,
        "recent_window_score_stdev": 0.0,
        "recent_window_scores": [
            {
                "attempt_id": int(attempt_dir.name.split("_")[1]),
                "window_id": "recent",
                "score": blended_score,
                "status": "scored",
                "trade_count": trade_count,
                "result_dir": str(attempt_dir),
            }
        ],
        "trade_count": trade_count,
        "params": {"threshold": blended_score},
        "evidence_result_dirs": [str(path) for path in evidence_result_dirs or []],
    }
    if promotion_dir is not None:
        payload["promotion_score"] = 0.025
        payload["promotion_summary"] = {"attempt": 1, "promotion_score": 0.025}
        payload["promotion_dir"] = str(promotion_dir)
    return payload


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
