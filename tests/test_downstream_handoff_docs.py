from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_oos_drift_template_is_downstream_and_one_look():
    text = _read("docs/templates/oos-drift-review.md").lower()

    for phrase in [
        "one-look downstream review",
        "must not be used to tune the same candidate",
        "run id",
        "strategy sha-256",
        "experiment sha-256",
        "protocol sha-256",
        "rationale sha-256",
        "score delta",
        "trade-count drift",
        "net-return contribution concentration drift",
        "net-return contribution concentration",
        "cost-stress drift",
        "decision",
    ]:
        assert phrase in text


def test_curated_few_adr_records_regime_and_escalation_triggers():
    text = _read("docs/adr/0001-curated-few-research-regime.md").lower()

    assert "curated-few thesis-driven regime" in text
    assert "one human-seeded thesis at a time" in text
    assert "oos, paper, and small-live review" in text
    for trigger in [
        "automated generation",
        "repeated oos looks",
        "historical validation being treated as deployment evidence",
    ]:
        assert trigger in text


def test_auto_research_docs_keep_oos_out_of_loop():
    text = "\n".join(
        [
            _read("README.md").lower(),
            _read("program.md").lower(),
        ]
    )

    assert "downstream oos drift review is season-owned" in text
    assert "must not feed back into this loop" in text


def test_docs_define_active_loop_and_downstream_artifact_authority():
    readme = _read("README.md").lower()
    oos_template = _read("docs/templates/oos-drift-review.md").lower()

    assert "artifact authority" in readme
    assert "active loop inputs" in readme
    assert "latest quick-run artifact directory recorded in `results.tsv`" in readme
    assert "generated audit and handoff artifacts" in readme
    assert "season downstream-only artifacts" in readme
    assert "historical or non-contract context" in readme
    assert "terminal manifests" in readme
    assert "not routine inputs for choosing train edits" in readme
    assert "do not browse the rest of the repo during ordinary train iteration" in readme
    assert "one-look downstream review" in oos_template
    assert "not an active-loop input" in oos_template


def test_downstream_handoff_spec_has_concrete_purpose():
    text = _read("openspec/specs/autoresearch-downstream-handoff/spec.md").lower()

    assert "tbd" not in text
    assert "downstream oos" in text
    assert "paper" in text
    assert "small-live" in text
