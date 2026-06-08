## ADDED Requirements

### Requirement: Local type checking passes
The project SHALL keep local `mypy .` checks passing, with untyped upstream imports handled by explicit narrow configuration rather than broad ignores.

#### Scenario: mypy passes locally
- **WHEN** `conda run -n quant python -m mypy .` is run in the repo
- **THEN** it exits successfully

#### Scenario: upstream ignore is narrow
- **WHEN** mypy configuration is inspected
- **THEN** missing-import ignores are scoped to `quant_strategies.*`
