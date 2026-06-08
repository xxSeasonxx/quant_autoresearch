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
        "concentration drift",
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
