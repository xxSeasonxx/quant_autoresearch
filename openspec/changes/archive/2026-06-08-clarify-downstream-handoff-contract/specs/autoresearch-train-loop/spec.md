## MODIFIED Requirements

### Requirement: A Train survivor is a handoff, not a promotion
When the best candidate clears all Train gates at loop end, the loop SHALL write a generated frozen handoff manifest for human review. It SHALL NOT mark the candidate as promoted, graduated, paper-ready, or live-ready. The handoff SHALL point Season toward downstream human review artifacts rather than invoking OOS evaluation inside auto-research.

#### Scenario: survivor handoff is produced
- **WHEN** the best candidate clears all Train gates at terminal stop
- **THEN** the loop records a frozen handoff containing strategy, params, protocol, rationale, results, attempt provenance, and an explicit not-deployability-evidence disclaimer

#### Scenario: handoff remains Train-only
- **WHEN** a Train survivor handoff is produced
- **THEN** the loop does not run OOS evaluation or read downstream OOS review artifacts
