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
When the best candidate clears all Train gates at loop end, the loop SHALL write a generated frozen handoff manifest for human review. It SHALL NOT mark the candidate as promoted, graduated, paper-ready, or live-ready.

#### Scenario: survivor handoff is produced
- **WHEN** the best candidate clears all Train gates at terminal stop
- **THEN** the loop records a frozen handoff containing strategy, params, protocol, rationale, results, attempt provenance, and an explicit not-deployability-evidence disclaimer

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

