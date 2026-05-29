from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import shutil
import sys
import tempfile
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.research_handoff_rank import FAMILY_PRIORITY, METHOD_VERSION, build_handoff_ranking


FAMILY_LABELS = ("primary", "secondary", "exploratory")
SELECTED_VARIANTS_PER_FAMILY = 5
SELECTED_FAMILY_COUNT = 3
SELECTED_VARIANT_COUNT = SELECTED_FAMILY_COUNT * SELECTED_VARIANTS_PER_FAMILY
SELECTED_KEEP_DIRS = {"selected_15", "new_15"}
SELECTED_LEDGER_STATUS = "selected"
SELECTED_LEDGER_RUN_KIND = "selected_legacy"
COMPACT_NEW_15_EVIDENCE_FILES = (
    "score.json",
    "summary.json",
    "evidence.json",
    "data_manifest.json",
    "run_manifest.json",
    "new_15_metadata.json",
    "notes.md",
    "signals.csv",
    "decision_records.jsonl",
    "strategy_snapshot.py",
)
OMITTED_LARGE_NEW_15_ARTIFACTS = (
    "engine_request.json",
    "strategy_input_rows.csv",
    "strategy_input_rows.jsonl",
)


def build_researched_package(
    *,
    campaign_dir: str | Path,
    target_repo: str | Path,
    strategy_id: str,
    ranking_path: str | Path | None = None,
    source_strategy_path: str | Path = "strategy.py",
    replace: bool = False,
) -> Path:
    campaign_path = Path(campaign_dir).expanduser().resolve()
    target_repo_path = Path(target_repo).expanduser().resolve()
    package_dir = target_repo_path / "researched" / strategy_id
    if package_dir.exists():
        if not replace:
            raise FileExistsError(f"destination already exists: {package_dir}")
        shutil.rmtree(package_dir)

    ranking = _load_ranking(campaign_path, ranking_path)
    selected_families = [str(item["family"]) for item in ranking.get("selected_families", [])]
    if len(selected_families) != 3:
        raise ValueError("expected exactly three selected families in handoff ranking")

    package_dir.mkdir(parents=True)
    selection_dir = package_dir / "selection"
    selection_dir.mkdir()
    _write_json(selection_dir / "handoff_ranking.json", ranking)
    (selection_dir / "scoring_method.md").write_text(_scoring_method_markdown(ranking), encoding="utf-8")

    variants_by_family = _variants_by_family(ranking)
    source_strategy = _resolve_source_strategy(source_strategy_path)
    variant_manifests: list[dict[str, Any]] = []
    family_entries: list[dict[str, Any]] = []

    for family_index, family_id in enumerate(selected_families, start=1):
        family_label = FAMILY_LABELS[family_index - 1]
        family_dir_name = f"family_{family_index:02d}_{family_label}_{_slug(family_id)}"
        family_dir = package_dir / "families" / family_dir_name
        family_dir.mkdir(parents=True)
        family_entries.append(
            {
                "family": family_id,
                "directory": f"families/{family_dir_name}",
                "role": family_label,
            }
        )

        retained_variants = variants_by_family.get(family_id, [])
        for rank, variant in enumerate(retained_variants, start=1):
            variant_dir = family_dir / "variants" / f"rank_{rank:02d}"
            variant_dir.mkdir(parents=True)
            variant_manifest = _write_variant_package(
                campaign_path=campaign_path,
                package_dir=package_dir,
                strategy_id=strategy_id,
                family_dir_name=family_dir_name,
                variant_dir=variant_dir,
                rank=rank,
                variant=variant,
                source_strategy=source_strategy,
            )
            variant_manifests.append(variant_manifest)

    manifest = {
        "source_repo_path": str(source_strategy.parent.resolve()),
        "target_repo_path": str(target_repo_path),
        "campaign_path": str(campaign_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "ranking_method_version": ranking.get("method_version", METHOD_VERSION),
        "selected_family_ids": selected_families,
        "variant_ids": [entry["variant_id"] for entry in variant_manifests],
        "families": family_entries,
        "variants": variant_manifests,
    }
    _write_json(package_dir / "manifest.json", manifest)
    (package_dir / "README.md").write_text(_readme(strategy_id, family_entries), encoding="utf-8")
    (package_dir / "HANDOFF.md").write_text(_handoff(strategy_id, family_entries), encoding="utf-8")
    notes_dir = package_dir / "notes"
    notes_dir.mkdir()
    (notes_dir / "llm_research_summary.md").write_text(_llm_summary(strategy_id), encoding="utf-8")
    (notes_dir / "upstream_limitations.md").write_text(_upstream_limitations(), encoding="utf-8")
    return package_dir


def build_selected_results_package(
    *,
    results_root: str | Path,
    strategy_id: str,
    ranking_path: str | Path | None = None,
    campaign_dirs: list[str | Path] | tuple[str | Path, ...] | None = None,
    strategy_template_path: str | Path = "strategy.py",
    replace: bool = False,
    rebuild_ledger: bool = True,
) -> Path:
    results_root_path = Path(results_root).expanduser().resolve()
    repo_root = results_root_path.parent
    selected_dir = results_root_path / "selected_15"
    new_dir = results_root_path / "new_15"
    strategy_template = _resolve_source_strategy(strategy_template_path)
    if not strategy_template.exists():
        raise FileNotFoundError(f"strategy template does not exist: {strategy_template}")

    if selected_dir.exists():
        if not replace:
            raise FileExistsError(f"destination already exists: {selected_dir}")

    ranking = _load_selected_results_ranking(
        results_root_path=results_root_path,
        campaign_dirs=campaign_dirs,
        ranking_path=ranking_path,
    )

    with tempfile.TemporaryDirectory(prefix=".selected_15_build_", dir=repo_root) as temp_root_raw:
        temp_repo_root = Path(temp_root_raw)
        temp_results_root = temp_repo_root / results_root_path.name
        temp_selected_dir = temp_results_root / "selected_15"
        temp_new_dir = temp_results_root / "new_15"
        _write_selected_results_package_contents(
            selected_dir=temp_selected_dir,
            new_dir=temp_new_dir,
            results_root_path=temp_results_root,
            repo_root=temp_repo_root,
            strategy_id=strategy_id,
            ranking=ranking,
            strategy_template=strategy_template,
        )
        verify_selected_results_package(temp_results_root)

        results_root_path.mkdir(parents=True, exist_ok=True)
        backup_dir = _replace_selected_dir(selected_dir, temp_selected_dir, results_root_path)
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir)

    new_dir.mkdir(parents=True, exist_ok=True)
    manifest = _read_json(selected_dir / "selection_manifest.json")
    if rebuild_ledger:
        _write_selected_results_ledger(repo_root / "results.tsv", manifest)
    verify_selected_results_package(results_root_path)
    return selected_dir


def build_researched_package_from_selected_results(
    *,
    results_root: str | Path,
    target_repo: str | Path,
    strategy_id: str,
    replace: bool = False,
) -> Path:
    results_root_path = Path(results_root).expanduser().resolve()
    repo_root = results_root_path.parent
    target_repo_path = Path(target_repo).expanduser().resolve()
    package_dir = target_repo_path / "researched" / strategy_id
    if package_dir.exists():
        if not replace:
            raise FileExistsError(f"destination already exists: {package_dir}")
        shutil.rmtree(package_dir)

    selected_manifest = verify_selected_results_package(results_root_path)
    variants = selected_manifest["variants"]
    if len(variants) != SELECTED_VARIANT_COUNT:
        raise ValueError(f"expected {SELECTED_VARIANT_COUNT} selected variants")

    package_dir.mkdir(parents=True)
    selection_dir = package_dir / "selection"
    selection_dir.mkdir()
    _write_json(selection_dir / "selected_15_manifest.json", selected_manifest)

    variant_manifests: list[dict[str, Any]] = []
    family_entries: list[dict[str, Any]] = []
    for family_entry in selected_manifest["families"]:
        family_dir_name = str(family_entry["directory"])
        target_family_dir = package_dir / "families" / family_dir_name
        target_family_dir.mkdir(parents=True)
        family_entries.append(
            {
                "family": family_entry["family"],
                "directory": f"families/{family_dir_name}",
                "role": family_entry["role"],
            }
        )

    for variant in variants:
        variant_manifest = _write_researched_selected_variant(
            results_root=results_root_path,
            repo_root=repo_root,
            package_dir=package_dir,
            target_repo=target_repo_path,
            strategy_id=strategy_id,
            variant=variant,
        )
        variant_manifests.append(variant_manifest)

    rerun_summary = _new_15_rerun_summary(variant_manifests)
    _write_json(selection_dir / "new_15_rerun_summary.json", rerun_summary)
    (selection_dir / "scoring_method.md").write_text(
        _selected_researched_scoring_method(selected_manifest),
        encoding="utf-8",
    )

    manifest = {
        "source_repo_path": str(repo_root),
        "target_repo_path": str(target_repo_path),
        "source_results_root": _relative_or_absolute(results_root_path, repo_root),
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_id": strategy_id,
        "ranking_method_version": selected_manifest.get("ranking_method_version", METHOD_VERSION),
        "selected_family_ids": selected_manifest.get("selected_family_ids", []),
        "family_count": len(family_entries),
        "variant_count": len(variant_manifests),
        "families": family_entries,
        "variants": variant_manifests,
        "notes": "Research handoff package. Not market validation.",
    }
    _write_json(package_dir / "manifest.json", manifest)
    (package_dir / "README.md").write_text(_selected_researched_readme(strategy_id, family_entries), encoding="utf-8")
    (package_dir / "HANDOFF.md").write_text(_handoff(strategy_id, family_entries), encoding="utf-8")
    notes_dir = package_dir / "notes"
    notes_dir.mkdir()
    (notes_dir / "llm_research_summary.md").write_text(
        _selected_researched_summary(strategy_id, rerun_summary),
        encoding="utf-8",
    )
    (notes_dir / "upstream_limitations.md").write_text(_upstream_limitations(), encoding="utf-8")
    verify_researched_package(package_dir, target_repo_path, expected_variant_count=SELECTED_VARIANT_COUNT)
    return package_dir


def verify_researched_package(
    package_dir: str | Path,
    target_repo: str | Path,
    *,
    expected_variant_count: int | None = None,
) -> dict[str, Any]:
    package_path = Path(package_dir).expanduser().resolve()
    target_repo_path = Path(target_repo).expanduser().resolve()
    manifest = _read_json(package_path / "manifest.json")
    variants = manifest.get("variants")
    if not isinstance(variants, list):
        raise ValueError(f"researched package manifest missing variants: {package_path}")
    if expected_variant_count is not None and len(variants) != expected_variant_count:
        raise ValueError(f"expected {expected_variant_count} variants; got {len(variants)}")

    for variant in variants:
        if not isinstance(variant, dict):
            raise ValueError("researched package variants must be objects")
        variant_dir = package_path / _required_manifest_str(variant, "directory")
        strategy_path = variant_dir / "strategy.py"
        config_path = variant_dir / "config.toml"
        if not strategy_path.exists() or not config_path.exists():
            raise FileNotFoundError(f"researched variant is incomplete: {variant_dir}")
        _verify_researched_strategy(strategy_path, repo_root=target_repo_path)
        _verify_researched_config(config_path, repo_root=target_repo_path, strategy_path=strategy_path)
        for evidence_file in variant.get("evidence_files", []):
            evidence_path = package_path / str(evidence_file)
            if not evidence_path.exists():
                raise FileNotFoundError(f"missing researched evidence file: {evidence_path}")
    return manifest


def _replace_selected_dir(selected_dir: Path, staged_selected_dir: Path, results_root_path: Path) -> Path | None:
    backup_dir: Path | None = None
    if selected_dir.exists():
        backup_dir = Path(tempfile.mkdtemp(prefix=".selected_15_backup_", dir=results_root_path))
        backup_dir.rmdir()
        shutil.move(str(selected_dir), str(backup_dir))
    try:
        shutil.move(str(staged_selected_dir), str(selected_dir))
    except Exception:
        if selected_dir.exists():
            shutil.rmtree(selected_dir)
        if backup_dir is not None and backup_dir.exists():
            shutil.move(str(backup_dir), str(selected_dir))
        raise
    return backup_dir


def _write_selected_results_package_contents(
    *,
    selected_dir: Path,
    new_dir: Path,
    results_root_path: Path,
    repo_root: Path,
    strategy_id: str,
    ranking: dict[str, Any],
    strategy_template: Path,
) -> dict[str, Any]:
    selected_families = [str(item["family"]) for item in ranking["selected_families"]]
    variants_by_family = _variants_by_family(ranking)

    selected_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True, exist_ok=True)

    variant_manifests: list[dict[str, Any]] = []
    family_entries: list[dict[str, Any]] = []
    for family_index, family_id in enumerate(selected_families, start=1):
        family_label = FAMILY_LABELS[family_index - 1]
        family_dir_name = f"family_{family_index:02d}_{family_label}_{_slug(family_id)}"
        family_dir = selected_dir / family_dir_name
        family_dir.mkdir(parents=True)
        family_entries.append(
            {
                "family": family_id,
                "directory": family_dir_name,
                "role": family_label,
            }
        )

        retained_variants = variants_by_family.get(family_id, [])
        if len(retained_variants) != SELECTED_VARIANTS_PER_FAMILY:
            raise ValueError(
                f"expected {SELECTED_VARIANTS_PER_FAMILY} variants for family {family_id}; "
                f"got {len(retained_variants)}"
            )
        for rank, variant in enumerate(retained_variants, start=1):
            rank_dir = family_dir / f"rank_{rank:02d}"
            rank_dir.mkdir()
            variant_manifest = _write_selected_variant_package(
                selected_dir=selected_dir,
                repo_root=repo_root,
                results_root=results_root_path,
                new_dir=new_dir,
                family_dir_name=family_dir_name,
                rank_dir=rank_dir,
                rank=rank,
                variant=variant,
                strategy_template=strategy_template,
                strategy_id=strategy_id,
            )
            variant_manifests.append(variant_manifest)

    if len(variant_manifests) != SELECTED_VARIANT_COUNT:
        raise ValueError(f"expected {SELECTED_VARIANT_COUNT} selected variants; got {len(variant_manifests)}")

    manifest = {
        "strategy_id": strategy_id,
        "results_root": _relative_or_absolute(results_root_path, repo_root),
        "new_results_root": _relative_or_absolute(new_dir, repo_root),
        "generated_at": datetime.now(UTC).isoformat(),
        "ranking_method_version": ranking.get("method_version", METHOD_VERSION),
        "source_campaigns": ranking.get("source_campaigns", []),
        "selected_family_ids": selected_families,
        "family_count": len(family_entries),
        "variant_count": len(variant_manifests),
        "families": family_entries,
        "variants": variant_manifests,
    }
    _write_json(selected_dir / "selection_manifest.json", manifest)
    (selected_dir / "README.md").write_text(_selected_readme(strategy_id, family_entries), encoding="utf-8")
    return manifest


def _write_researched_selected_variant(
    *,
    results_root: Path,
    repo_root: Path,
    package_dir: Path,
    target_repo: Path,
    strategy_id: str,
    variant: dict[str, Any],
) -> dict[str, Any]:
    selected_dir = results_root / "selected_15"
    selected_variant_dir = _selected_variant_dir_from_manifest(selected_dir, variant)
    family_dir_name = selected_variant_dir.parent.name
    rank = int(variant["rank"])
    variant_dir = package_dir / "families" / family_dir_name / "variants" / f"rank_{rank:02d}"
    variant_dir.mkdir(parents=True)

    new_run_dir = _new_15_run_dir(repo_root, variant)
    strategy_source = new_run_dir / "strategy_snapshot.py"
    if not strategy_source.exists():
        strategy_source = selected_variant_dir / "strategy.py"

    strategy_dest = variant_dir / "strategy.py"
    shutil.copyfile(strategy_source, strategy_dest)

    config_dest = variant_dir / "config.toml"
    strategy_rel = _relative_or_absolute(strategy_dest, target_repo)
    results_rel = f"results/researched/{strategy_id}/{family_dir_name}/rank_{rank:02d}"
    _rewrite_config(
        selected_variant_dir / "config.toml",
        config_dest,
        strategy_path=strategy_rel,
        results_dir=results_rel,
    )

    evidence_files = _copy_selected_researched_evidence(
        package_dir=package_dir,
        selected_variant_dir=selected_variant_dir,
        new_run_dir=new_run_dir,
        evidence_dir=variant_dir / "evidence",
    )
    rerun_score = _read_json(new_run_dir / "score.json")
    return {
        "variant_id": str(variant.get("variant_id")),
        "family": str(variant.get("family")),
        "rank": rank,
        "directory": _relative_posix(variant_dir, package_dir),
        "source_selected_dir": str(variant.get("result_dir")),
        "source_new_15_result_dir": _relative_or_absolute(new_run_dir, repo_root),
        "legacy_blended_score": _finite_float(variant.get("blended_score")),
        "legacy_trade_count": _int_or_none(variant.get("trade_count")),
        "rerun_score": _finite_float(rerun_score.get("score")),
        "rerun_raw_net_return": _finite_float(rerun_score.get("raw_net_return")),
        "rerun_trade_count": _int_or_none(rerun_score.get("trade_count")),
        "rerun_status": rerun_score.get("status"),
        "code_sha256": _file_sha256(strategy_dest),
        "config_sha256": _file_sha256(config_dest),
        "evidence_files": evidence_files,
        "omitted_large_artifacts": [
            f"new_15/{name}" for name in OMITTED_LARGE_NEW_15_ARTIFACTS if (new_run_dir / name).exists()
        ],
    }


def _copy_selected_researched_evidence(
    *,
    package_dir: Path,
    selected_variant_dir: Path,
    new_run_dir: Path,
    evidence_dir: Path,
) -> list[str]:
    evidence_dir.mkdir()
    copied: list[str] = []

    source_summary = selected_variant_dir / "source_summary.json"
    if source_summary.exists():
        dest = evidence_dir / "selected_source_summary.json"
        shutil.copyfile(source_summary, dest)
        copied.append(_relative_posix(dest, package_dir))

    selected_evidence = selected_variant_dir / "evidence"
    if selected_evidence.exists():
        legacy_dir = evidence_dir / "legacy_selection"
        legacy_dir.mkdir()
        for source in sorted(path for path in selected_evidence.iterdir() if path.is_file()):
            dest = legacy_dir / source.name
            shutil.copyfile(source, dest)
            copied.append(_relative_posix(dest, package_dir))

    rerun_dir = evidence_dir / "new_15_locked_recent_2026"
    rerun_dir.mkdir()
    for name in COMPACT_NEW_15_EVIDENCE_FILES:
        source = new_run_dir / name
        if not source.exists():
            continue
        dest = rerun_dir / name
        shutil.copyfile(source, dest)
        copied.append(_relative_posix(dest, package_dir))
    _write_json(
        rerun_dir / "artifact_policy.json",
        {
            "copied_files": sorted(path.name for path in rerun_dir.iterdir() if path.is_file()),
            "omitted_large_artifacts": [
                name for name in OMITTED_LARGE_NEW_15_ARTIFACTS if (new_run_dir / name).exists()
            ],
        },
    )
    copied.append(_relative_posix(rerun_dir / "artifact_policy.json", package_dir))
    return sorted(copied)


def _new_15_run_dir(repo_root: Path, variant: dict[str, Any]) -> Path:
    raw_new_result_dir = _required_manifest_str(variant, "new_result_dir")
    rank_result_dir = Path(raw_new_result_dir).expanduser()
    if not rank_result_dir.is_absolute():
        rank_result_dir = (repo_root / rank_result_dir).resolve()
    if not rank_result_dir.exists():
        raise FileNotFoundError(f"missing new_15 result directory: {rank_result_dir}")
    run_dirs = sorted(path for path in rank_result_dir.iterdir() if path.is_dir() and (path / "score.json").exists())
    if len(run_dirs) != 1:
        raise ValueError(f"expected exactly one scored new_15 run under {rank_result_dir}; got {len(run_dirs)}")
    return run_dirs[0]


def _new_15_rerun_summary(variant_manifests: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [entry for entry in variant_manifests if entry.get("rerun_status") == "scored"]
    ranked = sorted(
        variant_manifests,
        key=lambda entry: (
            -(_finite_float(entry.get("rerun_score")) or -math.inf),
            str(entry.get("family")),
            int(entry.get("rank", 0)),
        ),
    )
    return {
        "variant_count": len(variant_manifests),
        "scored_count": len(scored),
        "top_variants": [
            {
                "family": entry.get("family"),
                "rank": entry.get("rank"),
                "rerun_score": entry.get("rerun_score"),
                "rerun_raw_net_return": entry.get("rerun_raw_net_return"),
                "rerun_trade_count": entry.get("rerun_trade_count"),
            }
            for entry in ranked[:5]
        ],
    }


def verify_selected_results_package(results_root: str | Path) -> dict[str, Any]:
    results_root_path = Path(results_root).expanduser().resolve()
    repo_root = results_root_path.parent
    selected_dir = results_root_path / "selected_15"
    new_dir = results_root_path / "new_15"
    manifest_path = selected_dir / "selection_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing selected manifest: {manifest_path}")
    if not new_dir.is_dir():
        raise FileNotFoundError(f"missing new_15 directory: {new_dir}")

    manifest = _read_json(manifest_path)
    variants = manifest.get("variants")
    if not isinstance(variants, list) or len(variants) != SELECTED_VARIANT_COUNT:
        raise ValueError(f"expected {SELECTED_VARIANT_COUNT} selected variants")

    config_paths = sorted(selected_dir.glob("family_*/rank_*/config.toml"))
    strategy_paths = sorted(selected_dir.glob("family_*/rank_*/strategy.py"))
    if len(config_paths) != SELECTED_VARIANT_COUNT:
        raise ValueError(f"expected {SELECTED_VARIANT_COUNT} selected configs; got {len(config_paths)}")
    if len(strategy_paths) != SELECTED_VARIANT_COUNT:
        raise ValueError(f"expected {SELECTED_VARIANT_COUNT} selected strategies; got {len(strategy_paths)}")

    seen_directories: set[str] = set()
    seen_result_dirs: set[str] = set()
    for entry in variants:
        if not isinstance(entry, dict):
            raise ValueError("selected manifest variants must be objects")
        variant_dir = _selected_variant_dir_from_manifest(selected_dir, entry)
        directory = _relative_posix(variant_dir, selected_dir)
        if directory in seen_directories:
            raise ValueError(f"duplicate selected variant directory: {directory}")
        seen_directories.add(directory)

        result_dir = entry.get("result_dir")
        if result_dir != _relative_or_absolute(variant_dir, repo_root):
            raise ValueError(f"manifest result_dir does not match variant directory: {variant_dir}")
        if result_dir in seen_result_dirs:
            raise ValueError(f"duplicate selected result_dir: {result_dir}")
        seen_result_dirs.add(str(result_dir))

        strategy_path = variant_dir / "strategy.py"
        config_path = variant_dir / "config.toml"
        summary_path = variant_dir / "source_summary.json"
        if not strategy_path.exists() or not config_path.exists() or not summary_path.exists():
            raise FileNotFoundError(f"selected variant is incomplete: {variant_dir}")
        _verify_selected_strategy(strategy_path, repo_root=repo_root)
        _verify_selected_config(config_path, repo_root=repo_root, strategy_path=strategy_path)

    return manifest


def cleanup_results_root_after_selected_package(results_root: str | Path) -> list[str]:
    results_root_path = Path(results_root).expanduser().resolve()
    manifest = verify_selected_results_package(results_root_path)
    _verify_selected_results_ledger(results_root_path.parent / "results.tsv", manifest)

    removed: list[str] = []
    for child in sorted(results_root_path.iterdir(), key=lambda path: path.name):
        if child.name in SELECTED_KEEP_DIRS:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed.append(child.name)
    return removed


def _load_ranking(campaign_path: Path, ranking_path: str | Path | None) -> dict[str, Any]:
    if ranking_path is None:
        return build_handoff_ranking(campaign_path)
    path = Path(ranking_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected ranking JSON object: {path}")
    return payload


def _load_selected_results_ranking(
    *,
    results_root_path: Path,
    campaign_dirs: list[str | Path] | tuple[str | Path, ...] | None,
    ranking_path: str | Path | None,
) -> dict[str, Any]:
    if ranking_path is not None:
        path = Path(ranking_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        ranking = _read_json(path)
        campaign = Path(str(ranking.get("campaign_dir", path.parent))).expanduser()
        if not campaign.is_absolute():
            campaign = (path.parent / campaign).resolve()
        return _strict_selected_ranking(ranking, source_campaign=campaign)

    campaign_paths = _selected_campaign_paths(results_root_path, campaign_dirs)
    ranked_campaigns = [(campaign_path, build_handoff_ranking(campaign_path)) for campaign_path in campaign_paths]
    return _merge_selected_rankings(ranked_campaigns)


def _selected_campaign_paths(
    results_root_path: Path,
    campaign_dirs: list[str | Path] | tuple[str | Path, ...] | None,
) -> list[Path]:
    if campaign_dirs:
        paths = []
        for raw_path in campaign_dirs:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            paths.append(path)
        return paths

    paths = [
        path
        for path in sorted(results_root_path.iterdir(), key=lambda item: item.name)
        if path.is_dir() and path.name not in SELECTED_KEEP_DIRS and _looks_like_campaign_dir(path)
    ]
    if not paths:
        raise ValueError(f"no scored campaign directories found under {results_root_path}")
    return paths


def _looks_like_campaign_dir(path: Path) -> bool:
    return any(
        child.is_dir() and (child / "attempt_metadata.json").exists() and (child / "score.json").exists()
        for child in path.iterdir()
    )


def _strict_selected_ranking(ranking: dict[str, Any], *, source_campaign: Path) -> dict[str, Any]:
    selected_family_names = [str(item["family"]) for item in ranking.get("selected_families", [])]
    if len(selected_family_names) != SELECTED_FAMILY_COUNT:
        raise ValueError(f"expected exactly {SELECTED_FAMILY_COUNT} selected families")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for variant in ranking.get("variants", []):
        if not isinstance(variant, dict):
            raise ValueError("expected variant entries to be JSON objects")
        family = str(variant.get("family"))
        payload = dict(variant)
        payload.setdefault("source_campaign", str(source_campaign))
        grouped.setdefault(family, []).append(payload)

    selected_families: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    for family in selected_family_names:
        family_variants = sorted(grouped.get(family, []), key=_selected_variant_sort_key)[
            :SELECTED_VARIANTS_PER_FAMILY
        ]
        if len(family_variants) != SELECTED_VARIANTS_PER_FAMILY:
            raise ValueError(
                f"expected {SELECTED_VARIANTS_PER_FAMILY} variants for family {family}; "
                f"got {len(family_variants)}"
            )
        selected_families.append(
            {
                "family": family,
                "best_variant_id": family_variants[0]["variant_id"],
                "variant_count": len(family_variants),
            }
        )
        variants.extend(family_variants)

    return {
        "method_version": ranking.get("method_version", METHOD_VERSION),
        "generated_at": datetime.now(UTC).isoformat(),
        "source_campaigns": [str(source_campaign)],
        "selected_families": selected_families,
        "variants": variants,
    }


def _merge_selected_rankings(ranked_campaigns: list[tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    variants_by_id: dict[str, dict[str, Any]] = {}
    source_campaigns: list[str] = []
    for campaign_path, ranking in ranked_campaigns:
        source_campaigns.append(str(campaign_path))
        for variant in ranking.get("variants", []):
            if not isinstance(variant, dict):
                raise ValueError("expected variant entries to be JSON objects")
            payload = dict(variant)
            payload["source_campaign"] = str(campaign_path)
            variant_id = str(payload.get("variant_id"))
            existing = variants_by_id.get(variant_id)
            if existing is None or _selected_variant_sort_key(payload) < _selected_variant_sort_key(existing):
                variants_by_id[variant_id] = payload

    grouped: dict[str, list[dict[str, Any]]] = {}
    for variant in variants_by_id.values():
        grouped.setdefault(str(variant.get("family")), []).append(variant)
    if len(grouped) < SELECTED_FAMILY_COUNT:
        raise ValueError(f"expected at least {SELECTED_FAMILY_COUNT} logic families")

    for family, variants in grouped.items():
        variants.sort(key=_selected_variant_sort_key)
        if len(variants) < SELECTED_VARIANTS_PER_FAMILY:
            continue

    eligible_families = {
        family: variants
        for family, variants in grouped.items()
        if len(variants) >= SELECTED_VARIANTS_PER_FAMILY
    }
    if len(eligible_families) < SELECTED_FAMILY_COUNT:
        counts = {family: len(variants) for family, variants in grouped.items()}
        raise ValueError(f"not enough families with five variants: {counts}")

    selected_family_names = sorted(
        eligible_families,
        key=lambda family: _selected_variant_sort_key(eligible_families[family][0]),
    )[:SELECTED_FAMILY_COUNT]

    selected_families: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    for family in selected_family_names:
        family_variants = eligible_families[family][:SELECTED_VARIANTS_PER_FAMILY]
        selected_families.append(
            {
                "family": family,
                "best_variant_id": family_variants[0]["variant_id"],
                "variant_count": len(family_variants),
            }
        )
        variants.extend(family_variants)

    return {
        "method_version": f"{METHOD_VERSION}_selected_15",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_campaigns": source_campaigns,
        "selected_families": selected_families,
        "variants": variants,
    }


def _selected_variant_sort_key(variant: dict[str, Any]) -> tuple[float, float, float, int, int, str]:
    blended_score = _finite_float(variant.get("blended_score"))
    if blended_score is None:
        raise ValueError(f"variant missing finite blended_score: {variant.get('variant_id')}")
    promotion_score = _finite_float(variant.get("promotion_score"))
    stdev = _finite_float(variant.get("recent_window_score_stdev"))
    trade_count = _int_or_none(variant.get("trade_count"))
    family = str(variant.get("family"))
    return (
        -blended_score,
        -(promotion_score if promotion_score is not None else -math.inf),
        stdev if stdev is not None else math.inf,
        -(trade_count or 0),
        FAMILY_PRIORITY.get(family, len(FAMILY_PRIORITY)),
        str(variant.get("variant_id")),
    )


def _variants_by_family(ranking: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for variant in ranking.get("variants", []):
        if not isinstance(variant, dict):
            raise ValueError("expected variant entries to be JSON objects")
        family = str(variant.get("family"))
        grouped.setdefault(family, []).append(variant)
    return grouped


def _write_variant_package(
    *,
    campaign_path: Path,
    package_dir: Path,
    strategy_id: str,
    family_dir_name: str,
    variant_dir: Path,
    rank: int,
    variant: dict[str, Any],
    source_strategy: Path,
) -> dict[str, Any]:
    attempt_dirs = [_resolve_attempt_dir(campaign_path, value) for value in variant.get("attempt_dirs", [])]
    if not attempt_dirs:
        raise ValueError(f"variant missing attempt_dirs: {variant.get('variant_id')}")
    generated_config = _selected_generated_config(campaign_path, attempt_dirs)

    strategy_dest = variant_dir / "strategy.py"
    strategy_source = _selected_strategy_source(attempt_dirs, source_strategy)
    shutil.copyfile(strategy_source, strategy_dest)

    config_dest = variant_dir / "config.toml"
    strategy_rel = f"researched/{strategy_id}/families/{family_dir_name}/variants/rank_{rank:02d}/strategy.py"
    results_rel = f"results/researched/{strategy_id}/{family_dir_name}/rank_{rank:02d}"
    _rewrite_config(generated_config, config_dest, strategy_path=strategy_rel, results_dir=results_rel)

    evidence_files = _copy_evidence(
        package_dir=package_dir,
        evidence_dir=variant_dir / "evidence",
        attempt_dirs=attempt_dirs,
        variant=variant,
        include_trade_attribution=rank == 1,
    )
    return {
        "variant_id": str(variant.get("variant_id")),
        "family": str(variant.get("family")),
        "rank": rank,
        "directory": _relative_posix(variant_dir, package_dir),
        "code_sha256": _file_sha256(strategy_dest),
        "config_sha256": _file_sha256(config_dest),
        "evidence_files": evidence_files,
    }


def _write_selected_variant_package(
    *,
    selected_dir: Path,
    repo_root: Path,
    results_root: Path,
    new_dir: Path,
    family_dir_name: str,
    rank_dir: Path,
    rank: int,
    variant: dict[str, Any],
    strategy_template: Path,
    strategy_id: str,
) -> dict[str, Any]:
    source_campaign = Path(str(variant.get("source_campaign"))).expanduser()
    if not source_campaign.is_absolute():
        source_campaign = (Path.cwd() / source_campaign).resolve()
    attempt_dirs = [_resolve_attempt_dir(source_campaign, value) for value in variant.get("attempt_dirs", [])]
    if not attempt_dirs:
        raise ValueError(f"variant missing attempt_dirs: {variant.get('variant_id')}")
    generated_config = _selected_generated_config(source_campaign, attempt_dirs)
    source_strategy_id = _strategy_id_from_config(generated_config)
    if source_strategy_id != strategy_id:
        raise ValueError(
            f"selected package strategy_id {strategy_id!r} does not match "
            f"source config strategy_id {source_strategy_id!r}"
        )

    strategy_dest = rank_dir / "strategy.py"
    shutil.copyfile(strategy_template, strategy_dest)

    config_dest = rank_dir / "config.toml"
    strategy_rel = _relative_or_absolute(strategy_dest, repo_root)
    results_rel = _relative_or_absolute(new_dir / family_dir_name / f"rank_{rank:02d}", repo_root)
    _rewrite_config(generated_config, config_dest, strategy_path=strategy_rel, results_dir=results_rel)

    evidence_files = _copy_evidence(
        package_dir=selected_dir,
        evidence_dir=rank_dir / "evidence",
        attempt_dirs=attempt_dirs,
        variant=variant,
        include_trade_attribution=rank == 1,
    )
    source_summary = _selected_source_summary(
        variant=variant,
        rank=rank,
        source_campaign=source_campaign,
        generated_config=generated_config,
        result_dir=results_rel,
        evidence_files=evidence_files,
    )
    _write_json(rank_dir / "source_summary.json", source_summary)

    return {
        "variant_id": str(variant.get("variant_id")),
        "family": str(variant.get("family")),
        "rank": rank,
        "directory": _relative_posix(rank_dir, selected_dir),
        "result_dir": _relative_or_absolute(rank_dir, repo_root),
        "new_result_dir": results_rel,
        "source_campaign": str(source_campaign),
        "blended_score": _finite_float(variant.get("blended_score")),
        "promotion_score": _finite_float(variant.get("promotion_score")),
        "trade_count": _int_or_none(variant.get("trade_count")),
        "code_sha256": _file_sha256(strategy_dest),
        "config_sha256": _file_sha256(config_dest),
        "evidence_files": evidence_files,
    }


def _selected_source_summary(
    *,
    variant: dict[str, Any],
    rank: int,
    source_campaign: Path,
    generated_config: Path,
    result_dir: str,
    evidence_files: list[str],
) -> dict[str, Any]:
    return {
        "variant_id": str(variant.get("variant_id")),
        "family": str(variant.get("family")),
        "rank": rank,
        "source_campaign": str(source_campaign),
        "source_generated_config": str(generated_config),
        "attempt_ids": variant.get("attempt_ids", []),
        "attempt_dirs": variant.get("attempt_dirs", []),
        "evidence_result_dirs": variant.get("evidence_result_dirs", []),
        "recent_window_scores": variant.get("recent_window_scores", []),
        "blended_score": variant.get("blended_score"),
        "base_score": variant.get("base_score"),
        "promotion_score": variant.get("promotion_score"),
        "cost_stress_score": variant.get("cost_stress_score"),
        "trade_count": variant.get("trade_count"),
        "params": variant.get("params", {}),
        "result_dir": result_dir,
        "evidence_files": evidence_files,
    }


def _resolve_attempt_dir(campaign_path: Path, raw_path: object) -> Path:
    path = Path(str(raw_path)).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (campaign_path / path).resolve()


def _selected_generated_config(campaign_path: Path, attempt_dirs: list[Path]) -> Path:
    for attempt_dir in attempt_dirs:
        metadata_path = attempt_dir / "attempt_metadata.json"
        if not metadata_path.exists():
            continue
        metadata = _read_json(metadata_path)
        raw_config = metadata.get("generated_config")
        if raw_config is None:
            continue
        config_path = Path(str(raw_config)).expanduser()
        if not config_path.is_absolute():
            config_path = (campaign_path / config_path).resolve()
        if config_path.exists():
            return config_path
    raise FileNotFoundError(f"no generated_config found for attempts: {attempt_dirs}")


def _selected_strategy_source(attempt_dirs: list[Path], fallback: Path) -> Path:
    for attempt_dir in attempt_dirs:
        snapshot = attempt_dir / "strategy_snapshot.py"
        if snapshot.exists():
            return snapshot
    if not fallback.exists():
        raise FileNotFoundError(f"source strategy does not exist: {fallback}")
    return fallback


def _resolve_source_strategy(source_strategy_path: str | Path) -> Path:
    path = Path(source_strategy_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _rewrite_config(
    source: Path,
    dest: Path,
    *,
    strategy_path: str,
    results_dir: str,
    artifact_profile: str = "full",
) -> None:
    with source.open("rb") as handle:
        payload = tomllib.load(handle)
    payload["strategy_path"] = strategy_path
    output = payload.setdefault("output", {})
    if not isinstance(output, dict):
        raise ValueError(f"expected [output] table in {source}")
    output["results_dir"] = results_dir
    if output.get("mode") == "validate":
        output["mode"] = "screen"
    output["artifact_profile"] = artifact_profile
    dest.write_text(_dumps_toml(payload), encoding="utf-8")


def _copy_evidence(
    *,
    package_dir: Path,
    evidence_dir: Path,
    attempt_dirs: list[Path],
    variant: dict[str, Any],
    include_trade_attribution: bool,
) -> list[str]:
    evidence_dir.mkdir()
    copied: list[str] = []

    raw_promotion_dir = variant.get("promotion_dir")
    promotion_dir = Path(str(raw_promotion_dir)).expanduser() if raw_promotion_dir else None

    summary_dest = evidence_dir / "promotion_summary.json"
    if promotion_dir is not None and (promotion_dir / "promotion_summary.json").exists():
        shutil.copyfile(promotion_dir / "promotion_summary.json", summary_dest)
        copied.append(_relative_posix(summary_dest, package_dir))
    else:
        promotion_summary = variant.get("promotion_summary")
        if promotion_summary is not None:
            _write_json(summary_dest, promotion_summary)
            copied.append(_relative_posix(summary_dest, package_dir))

    score_dest = evidence_dir / "promotion_score.json"
    if promotion_dir is not None and (promotion_dir / "promotion_score.json").exists():
        shutil.copyfile(promotion_dir / "promotion_score.json", score_dest)
        copied.append(_relative_posix(score_dest, package_dir))
    else:
        promotion_score = variant.get("promotion_score")
        if promotion_score is not None:
            _write_json(score_dest, {"promotion_score": promotion_score})
            copied.append(_relative_posix(score_dest, package_dir))

    for attempt_dir in attempt_dirs:
        score_path = attempt_dir / "score.json"
        if score_path.exists():
            metadata_path = attempt_dir / "attempt_metadata.json"
            metadata = _read_json(metadata_path) if metadata_path.exists() else {}
            attempt_id = metadata.get("attempt", _attempt_id_from_name(attempt_dir.name))
            window_id = str(metadata.get("window_id", "window"))
            dest = evidence_dir / f"attempt_{int(attempt_id):04d}_{_slug(window_id)}_score.json"
            shutil.copyfile(score_path, dest)
            copied.append(_relative_posix(dest, package_dir))

    for index, raw_result_dir in enumerate(variant.get("evidence_result_dirs", []), start=1):
        result_dir = Path(str(raw_result_dir)).expanduser()
        score_path = result_dir if result_dir.is_file() else result_dir / "score.json"
        if not score_path.exists():
            continue
        dest = evidence_dir / (
            f"promotion_source_{index:02d}_{_slug(result_dir.parent.name)}_{_slug(result_dir.name)}_score.json"
        )
        shutil.copyfile(score_path, dest)
        copied.append(_relative_posix(dest, package_dir))

    if include_trade_attribution:
        if promotion_dir is not None:
            source = promotion_dir / "trade_attribution.json"
            if source.exists():
                dest = evidence_dir / "trade_attribution.json"
                shutil.copyfile(source, dest)
                copied.append(_relative_posix(dest, package_dir))

    return sorted(copied)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_selected_results_ledger(path: Path, manifest: dict[str, Any]) -> None:
    from runner import LEDGER_HEADER

    rows = []
    for attempt, variant in enumerate(manifest["variants"], start=1):
        rows.append(
            {
                "attempt": attempt,
                "commit": "",
                "window_id": "selected_legacy",
                "result_dir": variant["result_dir"],
                "window_start": "",
                "window_end": "",
                "window_days": "",
                "symbol_count": "",
                "score": "" if variant.get("blended_score") is None else variant["blended_score"],
                "raw_net_return": "",
                "trade_count": "" if variant.get("trade_count") is None else variant["trade_count"],
                "status": SELECTED_LEDGER_STATUS,
                "description": _single_line(
                    f"selected legacy {variant['family']} rank {int(variant['rank']):02d}"
                ),
                "run_kind": SELECTED_LEDGER_RUN_KIND,
                "candidate_score": "",
                "recent_mean_score": "",
                "worst_recent_score": "",
                "passed_window_count": "",
                "failed_window_count": "",
                "promotion_decision": "",
                "promotion_score": "" if variant.get("promotion_score") is None else variant["promotion_score"],
                "score_dispersion": "",
                "cost_stress_score": "",
                "cost_stress_ratio": "",
                "rotating_probe_window_id": "",
                "rotating_probe_score": "",
                "promoted_commit": "",
            }
        )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_HEADER, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in LEDGER_HEADER})


def _verify_selected_results_ledger(path: Path, manifest: dict[str, Any]) -> None:
    if not path.exists():
        raise FileNotFoundError(f"missing selected ledger: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != SELECTED_VARIANT_COUNT:
        raise ValueError(f"expected {SELECTED_VARIANT_COUNT} selected ledger rows; got {len(rows)}")
    if {row.get("run_kind") for row in rows} != {SELECTED_LEDGER_RUN_KIND}:
        raise ValueError("selected ledger must contain only selected_legacy rows")
    if {row.get("status") for row in rows} != {SELECTED_LEDGER_STATUS}:
        raise ValueError("selected ledger must contain only selected rows")
    if not all(str(row.get("result_dir", "")).startswith("results/selected_15/") for row in rows):
        raise ValueError("selected ledger result_dir values must point under results/selected_15")
    manifest_result_dirs = [str(variant.get("result_dir", "")) for variant in manifest["variants"]]
    ledger_result_dirs = [str(row.get("result_dir", "")) for row in rows]
    if ledger_result_dirs != manifest_result_dirs:
        raise ValueError("selected ledger result_dir values must match selection manifest order")


def _verify_selected_strategy(strategy_path: Path, *, repo_root: Path) -> None:
    from quant_strategies.decisions import load_decision_strategy

    generate_decisions = load_decision_strategy(strategy_path, repo_root=repo_root)
    if not callable(generate_decisions):
        raise ValueError(f"selected strategy does not expose generate_decisions: {strategy_path}")
    module_name = f"selected_strategy_{hashlib.sha256(str(strategy_path).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, strategy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not import selected strategy: {strategy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    exported = getattr(module, "__all__", ())
    if isinstance(exported, (list, tuple, set)) and "generate_signals" in exported:
        raise ValueError(f"selected strategy exports legacy generate_signals: {strategy_path}")


def _verify_selected_config(config_path: Path, *, repo_root: Path, strategy_path: Path) -> None:
    from quant_strategies.runner.config import load_config as load_runner_config

    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    expected_strategy_path = _relative_or_absolute(strategy_path, repo_root)
    if payload.get("strategy_path") != expected_strategy_path:
        raise ValueError(f"unexpected strategy_path in {config_path}")
    loaded = load_runner_config(config_path, repo_root=repo_root)
    if loaded.strategy_path != strategy_path.resolve():
        raise ValueError(f"upstream config loader resolved unexpected strategy path: {config_path}")
    if loaded.output.artifact_profile != "full":
        raise ValueError(f"selected config must use upstream artifact_profile full: {config_path}")
    output = payload.get("output")
    if not isinstance(output, dict):
        raise ValueError(f"missing [output] in {config_path}")
    if output.get("artifact_profile") != "full":
        raise ValueError(f"selected config must use artifact_profile full: {config_path}")
    results_dir = output.get("results_dir")
    if not isinstance(results_dir, str) or not results_dir.startswith("results/new_15/"):
        raise ValueError(f"selected config results_dir must point under results/new_15: {config_path}")


def _verify_researched_strategy(strategy_path: Path, *, repo_root: Path) -> None:
    from quant_strategies.decisions import load_decision_strategy

    generate_decisions = load_decision_strategy(strategy_path, repo_root=repo_root)
    if not callable(generate_decisions):
        raise ValueError(f"researched strategy does not expose generate_decisions: {strategy_path}")


def _verify_researched_config(config_path: Path, *, repo_root: Path, strategy_path: Path) -> None:
    from quant_strategies.runner.config import load_config as load_runner_config

    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    expected_strategy_path = _relative_or_absolute(strategy_path, repo_root)
    if payload.get("strategy_path") != expected_strategy_path:
        raise ValueError(f"unexpected strategy_path in {config_path}")
    loaded = load_runner_config(config_path, repo_root=repo_root)
    if loaded.strategy_path != strategy_path.resolve():
        raise ValueError(f"upstream config loader resolved unexpected strategy path: {config_path}")
    output = payload.get("output")
    if not isinstance(output, dict):
        raise ValueError(f"missing [output] in {config_path}")
    if output.get("artifact_profile") != "full":
        raise ValueError(f"researched config must use artifact_profile full: {config_path}")
    results_dir = output.get("results_dir")
    if not isinstance(results_dir, str) or not results_dir.startswith("results/researched/"):
        raise ValueError(f"researched config results_dir must point under results/researched: {config_path}")


def _selected_variant_dir_from_manifest(selected_dir: Path, entry: dict[str, Any]) -> Path:
    raw_directory = entry.get("directory")
    if not isinstance(raw_directory, str) or raw_directory == "":
        raise ValueError("selected manifest variant missing directory")
    variant_dir = (selected_dir / raw_directory).resolve()
    selected_root = selected_dir.resolve()
    try:
        variant_dir.relative_to(selected_root)
    except ValueError as exc:
        raise ValueError(f"selected manifest directory escapes selected_15: {raw_directory}") from exc
    return variant_dir


def _strategy_id_from_config(config_path: Path) -> str:
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    value = payload.get("strategy_id")
    if not isinstance(value, str) or value == "":
        raise ValueError(f"selected source config missing strategy_id: {config_path}")
    return value


def _required_manifest_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"manifest entry missing {key}")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dumps_toml(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    top_level = {key: value for key, value in payload.items() if not isinstance(value, dict)}
    tables = {key: value for key, value in payload.items() if isinstance(value, dict)}

    for key, value in top_level.items():
        lines.append(f"{key} = {_toml_value(value)}")
    if top_level and tables:
        lines.append("")

    for table_index, (table_name, table_payload) in enumerate(tables.items()):
        if table_index > 0:
            lines.append("")
        lines.append(f"[{table_name}]")
        for key, value in table_payload.items():
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, date):
        return json.dumps(value.isoformat())
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if value is None:
        raise ValueError("cannot serialize None to TOML")
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def _attempt_id_from_name(name: str) -> int:
    digits = "".join(character for character in name if character.isdigit())
    return int(digits) if digits else 0


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _slug(value: str) -> str:
    slug = "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in value)
    return slug.strip("_") or "unknown"


def _scoring_method_markdown(ranking: dict[str, Any]) -> str:
    method = ranking.get("method_version", METHOD_VERSION)
    return (
        "# Scoring Method\n\n"
        f"Ranking method version: `{method}`.\n\n"
        "This package preserves the handoff ranking JSON as the authoritative "
        "selection record. The ranked candidates are research handoff candidates, "
        "not market-validated strategies.\n"
    )


def _readme(strategy_id: str, families: list[dict[str, Any]]) -> str:
    family_lines = "\n".join(
        f"- `{entry['directory']}`: {entry['role']} family `{entry['family']}`"
        for entry in families
    )
    return (
        f"# {strategy_id}\n\n"
        "Self-contained researched candidate handoff package.\n\n"
        "This package contains selected research candidates for downstream "
        "comprehensive validation. A researched candidate is not market validated.\n\n"
        "## Families\n\n"
        f"{family_lines}\n\n"
        "## Authoritative Inputs\n\n"
        "- `selection/handoff_ranking.json`\n"
        "- per-variant `config.toml`\n"
        "- per-variant `strategy.py`\n"
        "- per-variant `evidence/`\n"
    )


def _selected_readme(strategy_id: str, families: list[dict[str, Any]]) -> str:
    family_lines = "\n".join(
        f"- `{entry['directory']}`: {entry['role']} family `{entry['family']}`"
        for entry in families
    )
    return (
        f"# Selected 15: {strategy_id}\n\n"
        "Local package of the retained legacy research candidates. These are "
        "smoke-screened research candidates, not validated or live-ready strategies.\n\n"
        "## Families\n\n"
        f"{family_lines}\n\n"
        "Each rank directory contains the current strategy contract, a rewritten "
        "`config.toml`, copied score evidence, and `source_summary.json`.\n"
    )


def _selected_researched_readme(strategy_id: str, families: list[dict[str, Any]]) -> str:
    family_lines = "\n".join(
        f"- `{entry['directory']}`: {entry['role']} family `{entry['family']}`"
        for entry in families
    )
    return (
        f"# {strategy_id}\n\n"
        "Researched handoff package built from the selected 15 archive and the "
        "fresh new_15 rerun. These candidates are smoke-screened research "
        "outputs, not market validation or live-trading approval.\n\n"
        "## Families\n\n"
        f"{family_lines}\n\n"
        "Each variant contains a rewritten `config.toml`, the strategy snapshot "
        "used by the rerun, compact selected evidence, and compact new_15 rerun "
        "evidence. Large raw input artifacts are intentionally omitted and can be "
        "recreated by rerunning the config.\n"
    )


def _selected_researched_scoring_method(selected_manifest: dict[str, Any]) -> str:
    method = selected_manifest.get("ranking_method_version", METHOD_VERSION)
    return (
        "# Scoring Method\n\n"
        f"Selected-15 ranking method version: `{method}`.\n\n"
        "The preserved `selected_15` score is a blended handoff score. The "
        "new_15 rerun score is the single-window `locked_recent_2026` smoke "
        "score produced by the current `quant_strategies` runner. Both are loop "
        "feedback only, not market evidence.\n"
    )


def _handoff(strategy_id: str, families: list[dict[str, Any]]) -> str:
    family_lines = "\n".join(f"- {entry['role']}: `{entry['family']}`" for entry in families)
    return (
        f"# Handoff: {strategy_id}\n\n"
        "Use this package as a starting point for comprehensive validation in "
        "`quant_strategies`. Do not treat the screening scores as live-trading "
        "evidence.\n\n"
        "## Selected Families\n\n"
        f"{family_lines}\n\n"
        "## Next Checks\n\n"
        "- Re-run each retained config in the target repository.\n"
        "- Review costs, fills, data availability, and trade attribution.\n"
        "- Promote only after downstream validation passes.\n"
    )


def _llm_summary(strategy_id: str) -> str:
    return (
        f"# LLM Research Summary: {strategy_id}\n\n"
        "This is an initial machine-written scaffold. The source JSON, config, "
        "strategy, and evidence files in this package are authoritative.\n\n"
        "## Research Hypothesis\n\n"
        "TODO: summarize the economic hypothesis from the original campaign notes.\n\n"
        "## Evidence Summary\n\n"
        "TODO: summarize promotion, score, and trade-attribution evidence after human review.\n\n"
        "## Validation Risks\n\n"
        "TODO: document data, fill, cost, regime, and overfit risks before validation.\n"
    )


def _selected_researched_summary(strategy_id: str, rerun_summary: dict[str, Any]) -> str:
    top_lines = "\n".join(
        "- `{family}` rank `{rank}`: score `{score}`, raw net `{raw}`, trades `{trades}`".format(
            family=entry.get("family"),
            rank=entry.get("rank"),
            score=entry.get("rerun_score"),
            raw=entry.get("rerun_raw_net_return"),
            trades=entry.get("rerun_trade_count"),
        )
        for entry in rerun_summary.get("top_variants", [])
    )
    return (
        f"# LLM Research Summary: {strategy_id}\n\n"
        "This package moves the selected 15 research variants out of the "
        "`quant_autoresearch` bench and into `quant_strategies/researched`.\n"
        "The source JSON, config, strategy, and evidence files in this package "
        "are authoritative.\n\n"
        "## New 15 Rerun\n\n"
        f"- Variant count: `{rerun_summary.get('variant_count')}`\n"
        f"- Scored count: `{rerun_summary.get('scored_count')}`\n\n"
        "Top rerun variants:\n\n"
        f"{top_lines}\n\n"
        "## Validation Risks\n\n"
        "These are smoke-screened research candidates. Before paper trading or "
        "live trading, run downstream validation for costs, fills, venue/data "
        "availability, regime robustness, exposure limits, and duplicate variant "
        "behavior.\n"
    )


def _upstream_limitations() -> str:
    return (
        "# Upstream Limitations\n\n"
        "No upstream limitations were copied automatically into this handoff package.\n\n"
        "Record data, engine, or harness limitations discovered during downstream "
        "validation here instead of encoding misleading approximations in strategy code.\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", action="append")
    parser.add_argument("--target-repo")
    parser.add_argument("--strategy-id")
    parser.add_argument("--ranking")
    parser.add_argument("--source-strategy", default="strategy.py")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--selected-15", action="store_true")
    parser.add_argument("--results-root", default="results")
    parser.add_argument("--strategy-template", default="strategy.py")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--from-selected-results", action="store_true")
    args = parser.parse_args(argv)

    if args.from_selected_results:
        if not args.target_repo:
            parser.error("--target-repo is required with --from-selected-results")
        if not args.strategy_id:
            parser.error("--strategy-id is required with --from-selected-results")
        package_dir = build_researched_package_from_selected_results(
            results_root=args.results_root,
            target_repo=args.target_repo,
            strategy_id=args.strategy_id,
            replace=args.replace,
        )
        print(package_dir)
        return 0

    if args.selected_15 or args.verify_only or args.cleanup:
        if args.verify_only:
            manifest = verify_selected_results_package(args.results_root)
            if args.cleanup:
                cleanup_results_root_after_selected_package(args.results_root)
            print(json.dumps({"selected_dir": str(Path(args.results_root) / "selected_15"), "variant_count": manifest["variant_count"]}))
            return 0

        if not args.write:
            ranking = _load_selected_results_ranking(
                results_root_path=Path(args.results_root).expanduser().resolve(),
                campaign_dirs=args.campaign,
                ranking_path=args.ranking,
            )
            print(
                json.dumps(
                    {
                        "selected_families": ranking["selected_families"],
                        "variant_count": len(ranking["variants"]),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        if not args.strategy_id:
            parser.error("--strategy-id is required with --selected-15 --write")
        selected_dir = build_selected_results_package(
            results_root=args.results_root,
            strategy_id=args.strategy_id,
            ranking_path=args.ranking,
            campaign_dirs=args.campaign,
            strategy_template_path=args.strategy_template,
            replace=args.replace,
        )
        if args.cleanup:
            cleanup_results_root_after_selected_package(args.results_root)
        print(selected_dir)
        return 0

    if not args.campaign or len(args.campaign) != 1:
        parser.error("exactly one --campaign is required for researched-package mode")
    if not args.target_repo:
        parser.error("--target-repo is required for researched-package mode")
    if not args.strategy_id:
        parser.error("--strategy-id is required for researched-package mode")
    package_dir = build_researched_package(
        campaign_dir=args.campaign[0],
        target_repo=args.target_repo,
        strategy_id=args.strategy_id,
        ranking_path=args.ranking,
        source_strategy_path=args.source_strategy,
        replace=args.replace,
    )
    print(package_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
