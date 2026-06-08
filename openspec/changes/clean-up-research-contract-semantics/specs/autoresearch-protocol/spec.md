## ADDED Requirements

### Requirement: Default protocol documents symbol and window rationale
The active default protocol SHALL document why the default symbol universe, Train window, and subwindow count were selected for the current thesis-development setup.

#### Scenario: Protocol rationale is near owned values
- **WHEN** `protocol.toml` is read
- **THEN** symbol, Train window, and subwindow rationale is available near the corresponding protocol-owned values
