from __future__ import annotations

from pathlib import Path

from artifact_policy import apply_artifact_policy
from experiment_config import ArtifactConfig


def research_policy() -> ArtifactConfig:
    return ArtifactConfig(
        profile="research",
        keep_strategy_snapshot=True,
        keep_config=True,
        keep_summary=True,
        keep_evidence=True,
        keep_signals=True,
        keep_engine_request=False,
        keep_input_rows_csv=False,
        keep_input_rows_jsonl=False,
        compress_large_artifacts=False,
        large_artifact_max_mb=100,
    )


def debug_policy() -> ArtifactConfig:
    return ArtifactConfig(
        profile="debug",
        keep_strategy_snapshot=True,
        keep_config=True,
        keep_summary=True,
        keep_evidence=True,
        keep_signals=True,
        keep_engine_request=True,
        keep_input_rows_csv=True,
        keep_input_rows_jsonl=True,
        compress_large_artifacts=False,
        large_artifact_max_mb=100,
    )


def write_artifacts(result_dir: Path) -> None:
    result_dir.mkdir()
    for name in (
        "config.toml",
        "summary.json",
        "evidence.json",
        "signals.csv",
        "strategy_snapshot.py",
        "engine_request.json",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
    ):
        (result_dir / name).write_text(name + "\n")


def test_apply_artifact_policy_removes_large_debug_inputs_for_research_profile(tmp_path: Path):
    result_dir = tmp_path / "attempt"
    write_artifacts(result_dir)

    removed = apply_artifact_policy(result_dir, research_policy())

    assert sorted(removed) == [
        "engine_request.json",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
    ]
    assert (result_dir / "config.toml").exists()
    assert (result_dir / "summary.json").exists()
    assert (result_dir / "evidence.json").exists()
    assert (result_dir / "signals.csv").exists()
    assert (result_dir / "strategy_snapshot.py").exists()
    assert not (result_dir / "engine_request.json").exists()
    assert not (result_dir / "strategy_input_rows.csv").exists()
    assert not (result_dir / "strategy_input_rows.jsonl").exists()


def test_apply_artifact_policy_keeps_debug_profile_artifacts(tmp_path: Path):
    result_dir = tmp_path / "attempt"
    write_artifacts(result_dir)

    removed = apply_artifact_policy(result_dir, debug_policy())

    assert removed == []
    assert (result_dir / "engine_request.json").exists()
    assert (result_dir / "strategy_input_rows.csv").exists()
    assert (result_dir / "strategy_input_rows.jsonl").exists()


def test_apply_artifact_policy_honors_core_keep_flags_for_research_profile(tmp_path: Path):
    result_dir = tmp_path / "attempt"
    write_artifacts(result_dir)
    policy = ArtifactConfig(
        profile="research",
        keep_strategy_snapshot=False,
        keep_config=False,
        keep_summary=False,
        keep_evidence=False,
        keep_signals=False,
        keep_engine_request=False,
        keep_input_rows_csv=False,
        keep_input_rows_jsonl=False,
        compress_large_artifacts=False,
        large_artifact_max_mb=100,
    )

    removed = apply_artifact_policy(result_dir, policy)

    assert sorted(removed) == [
        "config.toml",
        "engine_request.json",
        "evidence.json",
        "signals.csv",
        "strategy_input_rows.csv",
        "strategy_input_rows.jsonl",
        "strategy_snapshot.py",
        "summary.json",
    ]
    assert not any(result_dir.iterdir())
