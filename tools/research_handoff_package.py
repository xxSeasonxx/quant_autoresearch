from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from tools.research_handoff_rank import METHOD_VERSION, build_handoff_ranking


FAMILY_LABELS = ("primary", "secondary", "exploratory")


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
) -> None:
    with source.open("rb") as handle:
        payload = tomllib.load(handle)
    payload["strategy_path"] = strategy_path
    output = payload.setdefault("output", {})
    if not isinstance(output, dict):
        raise ValueError(f"expected [output] table in {source}")
    output["results_dir"] = results_dir
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

    promotion_summary = variant.get("promotion_summary")
    if promotion_summary is not None:
        path = evidence_dir / "promotion_summary.json"
        _write_json(path, promotion_summary)
        copied.append(_relative_posix(path, package_dir))

    promotion_score = variant.get("promotion_score")
    if promotion_score is not None:
        path = evidence_dir / "promotion_score.json"
        _write_json(path, {"promotion_score": promotion_score})
        copied.append(_relative_posix(path, package_dir))

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

    if include_trade_attribution:
        promotion_dir = variant.get("promotion_dir")
        if promotion_dir:
            source = Path(str(promotion_dir)).expanduser() / "trade_attribution.json"
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


def _upstream_limitations() -> str:
    return (
        "# Upstream Limitations\n\n"
        "No upstream limitations were copied automatically into this handoff package.\n\n"
        "Record data, engine, or harness limitations discovered during downstream "
        "validation here instead of encoding misleading approximations in strategy code.\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--ranking")
    parser.add_argument("--source-strategy", default="strategy.py")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)

    package_dir = build_researched_package(
        campaign_dir=args.campaign,
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
