## Purpose

Define the one-thesis Train loop lifecycle from initial run through keep/discard decisions, stop rules, and human handoff.
## Requirements
### Requirement: The loop runs one thesis at a time
The auto-research loop SHALL operate on one human-seeded thesis at a time. A thesis SHALL include a mechanism and falsifier. The loop SHALL end with either a frozen Train survivor handoff or a Train death result.

#### Scenario: missing thesis is rejected
- **WHEN** a climb is requested without a thesis mechanism and falsifier
- **THEN** the loop refuses to start and explains the missing fields

### Requirement: The first iteration establishes a feasible baseline
The loop SHALL establish a baseline for the starting `strategy.py` and params before comparing later changes. If no feasible baseline is found within the configured grace window, the thesis SHALL die on Train.

#### Scenario: baseline succeeds
- **WHEN** the initial candidate runs successfully and passes gates
- **THEN** its score becomes the initial best feasible score

#### Scenario: baseline grace expires
- **WHEN** no feasible candidate appears within the configured baseline grace window
- **THEN** the loop stops and records the thesis as dead on Train

### Requirement: Each iteration runs, scores, gates, logs, and keeps or reverts
Each completed iteration SHALL run the current candidate through public quick-run, compute the configured Train objective, compute all gates, append one `results.tsv` row with attempt provenance, and update the best candidate only if the score improves by the configured plateau threshold and all gates pass. Otherwise the loop SHALL leave the best candidate unchanged while allowing the working candidate to continue when no terminal stop or invalid workspace condition exists.

#### Scenario: improving gated iteration is kept
- **WHEN** an iteration succeeds, passes all gates, and improves beyond the configured threshold
- **THEN** the loop keeps it as the new best candidate and logs status `keep`

#### Scenario: non-improving iteration does not update best
- **WHEN** an iteration fails, fails a gate, or does not improve enough
- **THEN** the loop logs the attempt, leaves the best candidate unchanged, and counts the attempt toward applicable stop rules

#### Scenario: discarded working candidate can continue
- **WHEN** an iteration is discarded without crashing the workspace and no terminal stop condition fires
- **THEN** the loop allows a later thesis-guided edit to start from the current working candidate

### Requirement: The loop stops on configured stop rules
The loop SHALL stop on the first configured stop condition: plateau, complexity exhausted, max iterations, or baseline failure. Stop reasons SHALL be recorded in result rows, status output, and any generated terminal manifest.

#### Scenario: max iterations stops the thesis
- **WHEN** the completed attempt count reaches `N`
- **THEN** the loop stops with max-iterations as the stop reason

#### Scenario: plateau stops the thesis
- **WHEN** `M` consecutive completed attempts occur without improvement after a feasible baseline exists
- **THEN** the loop stops with plateau as the stop reason

#### Scenario: stopped thesis rejects new climb
- **WHEN** a terminal stop reason has already been recorded for the current thesis run
- **THEN** a new climb attempt is rejected before running `quant_strategies.runner.run_config`

### Requirement: A Train survivor is a handoff, not a promotion
When the best candidate clears all Train gates at loop end, the loop SHALL write a generated frozen handoff manifest for human review. It SHALL NOT mark the candidate as promoted, graduated, paper-ready, or live-ready. The handoff SHALL point Season toward downstream human review artifacts rather than invoking OOS evaluation inside auto-research.

#### Scenario: survivor handoff is produced
- **WHEN** the best candidate clears all Train gates at terminal stop
- **THEN** the loop records a frozen handoff containing strategy, params, protocol, rationale, results, attempt provenance, and an explicit not-deployability-evidence disclaimer

#### Scenario: handoff remains Train-only
- **WHEN** a Train survivor handoff is produced
- **THEN** the loop does not run OOS evaluation or read downstream OOS review artifacts

### Requirement: The loop derives attempt state before running
Before starting a new attempt, the loop SHALL derive the current thesis state from protocol config, current candidate snapshot, and prior `results.tsv` rows.

#### Scenario: terminal state blocks next attempt
- **WHEN** prior result rows record a terminal continuation state for the current thesis run
- **THEN** the loop refuses to run another attempt

#### Scenario: ordinary discard allows next attempt
- **WHEN** prior result rows show the latest attempt was discarded with continuation allowed
- **THEN** the loop allows another attempt unless another stop rule blocks it

#### Scenario: invalid workspace blocks next attempt
- **WHEN** prior result rows record that the workspace needs repair before evidence can be trusted
- **THEN** the loop refuses to run another attempt until the invalid workspace condition is cleared

### Requirement: Terminal Train failure is explicit
When a thesis reaches a terminal stop condition without a valid Train survivor, the loop SHALL write a generated failure manifest for human review.

#### Scenario: baseline grace failure writes manifest
- **WHEN** no feasible candidate appears within the configured baseline grace window
- **THEN** the loop records Train failure with baseline-failure as the stop reason

#### Scenario: plateau without survivor writes manifest
- **WHEN** plateau fires and no kept candidate clears all Train gates
- **THEN** the loop records Train failure rather than a survivor handoff

### Requirement: Terminal handoff snapshots the best Train survivor
When a terminal stop condition fires after at least one kept candidate exists, the loop SHALL produce a terminal manifest whose Train survivor snapshot contains the source, params, protocol, rationale, and quick-run config from the best kept attempt, not from the current workspace unless the current workspace is that same best attempt.

#### Scenario: Plateau after discard preserves prior best survivor
- **WHEN** a prior attempt was kept and a later discarded attempt triggers plateau
- **THEN** the terminal manifest identifies the prior kept attempt as the best survivor
- **AND** the best survivor snapshot hashes match the prior kept attempt hashes

#### Scenario: Train failure has no survivor snapshot
- **WHEN** a thesis reaches a terminal stop without any kept candidate
- **THEN** the terminal manifest records Train failure
- **AND** the manifest does not expose a best survivor snapshot

### Requirement: Active thesis identity blocks ordinary drift
After the first attempt in a thesis lifecycle, the loop SHALL reject ordinary continuation when the provided mechanism or falsifier no longer matches the active thesis lock.

#### Scenario: Matching thesis continues
- **WHEN** a later climb uses the same normalized mechanism and falsifier as the active thesis lock
- **THEN** the loop may continue if no other stop or repair condition blocks it

#### Scenario: Changed thesis is rejected
- **WHEN** a later climb uses a different mechanism or falsifier from the active thesis lock
- **THEN** the loop rejects the attempt before quick-run materialization
- **AND** the rejection explains that a new thesis lifecycle is required

### Requirement: Portfolio-foundation iterations consume public foundation evidence
When the protocol selects `portfolio_psr_subwindow`, each successful quick-run iteration SHALL compute score and foundation-backed gates from public `RunResult.foundation` payloads and SHALL NOT import private `quant_strategies` modules.

#### Scenario: foundation evidence drives score
- **WHEN** `run_config` succeeds and returns portfolio foundation evidence
- **THEN** the loop computes the objective score from `result.foundation`
- **AND** appends a result row using the portfolio-foundation score

#### Scenario: missing foundation evidence fails attempt
- **WHEN** `run_config` succeeds but returns no portfolio foundation evidence for `portfolio_psr_subwindow`
- **THEN** the iteration records a crash or repair-required attempt with a clear missing-foundation message

### Requirement: Micro causality evidence is surfaced for Train iteration
For Train iteration, the loop SHALL allow the protocol to request `micro` causality replay and SHALL surface causality status in the generated run card.

#### Scenario: micro causality is passed through
- **WHEN** the protocol sets `output.causality_check = "micro"`
- **THEN** the materialized quick-run config passed to `run_config` contains `causality_check = "micro"`

#### Scenario: causality status appears in run card
- **WHEN** `run_config` returns causality evidence
- **THEN** the generated run card records causality mode, verification status, replay warning, timeout status, and selected probe count when available

### Requirement: Portfolio-foundation keep rule preserves existing lifecycle semantics
For `portfolio_psr_subwindow`, the loop SHALL use the existing keep rule shape: only all-gates-pass attempts whose score exceeds the previous best by `max(eps, rho * max(1, abs(best)))` update the best Train survivor.

#### Scenario: gated PSR improvement is kept
- **WHEN** an iteration has a portfolio-foundation PSR score, passes all gates, and improves beyond the configured threshold
- **THEN** the loop logs status `keep`
- **AND** records `best_status=updated`

#### Scenario: failed foundation gate prevents keep
- **WHEN** an iteration has an improved PSR score but fails any foundation-backed gate
- **THEN** the loop logs status `discard`
- **AND** records `best_status=unchanged`

