## ADDED Requirements

### Requirement: Historical design sketches are non-contract
The agent contract SHALL make clear that historical design documents may contain stale implementation sketches and SHALL NOT override active operating docs or active specs.

#### Scenario: Historical design doc is visibly non-contract
- **WHEN** the historical simplified loop design is read
- **THEN** it clearly labels implementation sketches and open questions as historical, non-contract context
