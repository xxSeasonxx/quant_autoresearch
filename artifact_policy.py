from __future__ import annotations

from pathlib import Path

from experiment_config import ArtifactConfig


_ARTIFACTS = {
    "strategy_snapshot.py": "keep_strategy_snapshot",
    "config.toml": "keep_config",
    "summary.json": "keep_summary",
    "artifact_profile_summary.json": "keep_summary",
    "data_manifest.json": "keep_summary",
    "run_manifest.json": "keep_summary",
    "notes.md": "keep_summary",
    "evidence.json": "keep_evidence",
    "signals.csv": "keep_signals",
    "decision_records.jsonl": "keep_signals",
    "engine_request.json": "keep_engine_request",
    "strategy_input_rows.csv": "keep_input_rows_csv",
    "strategy_input_rows.jsonl": "keep_input_rows_jsonl",
}


def apply_artifact_policy(result_dir: Path, config: ArtifactConfig) -> list[str]:
    removed: list[str] = []
    if config.profile == "debug":
        return removed

    for filename, flag_name in _ARTIFACTS.items():
        keep = bool(getattr(config, flag_name))
        path = result_dir / filename
        if keep or not path.exists():
            continue
        path.unlink()
        removed.append(filename)

    return removed
