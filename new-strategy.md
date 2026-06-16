# New Strategy Setup

Use this guide before the first Train attempt for a new thesis or reseed. The
goal is to turn Season's plain-language idea into an explicit, approved
`protocol.toml` contract before any Train result exists. After the first baseline,
`program.md` owns the active loop.

The LLM agent may interpret Season's idea, ask follow-up questions, inspect
in-scope files, and recommend protocol values. The CLI helper is deterministic:
it parses a filled setup brief, writes proposal artifacts, and refuses stale or
unapproved baselines. It does not call an LLM and does not edit `protocol.toml`.

## Flow

1. Ask Season for the mandate in plain language:
  - mechanism, observable, falsifier, and expected horizon;
  - data kind, dataset, desired symbols, or exclusions;
  - capital/notional, target volatility, max tolerable drawdown, and minimum
  annualized return;
  - Train window, data needs, attempt budget, and baseline expectations when
  Season already has an opinion.
2. Ask only missing high-impact questions. Do not interrogate Season about
  low-level fields that can be derived from data docs, current protocol, or the
   thesis.
3. Inspect `strategy.py`, `rationale.md`, `protocol.toml`, and
  `/Users/Season_Yang/Personal/quant-data/docs/consumer/` for the editable
   surface, current protocol, data readiness, cadence, liquidity, and capacity
   support.
4. When the universe should be eligibility-based, run `resolve-universe` and
  write the artifact under `.autoresearch/universe/`.
5. Create `.autoresearch/protocol_briefs/latest.md` from the template below. Keep
  `new-strategy.md` stable; do not use this guide itself as the CLI brief.
6. Run `propose-protocol`.
7. Present Season a recommendation table with current value, recommended value,
  reason, and tradeoff for each protocol-owned change.
8. Wait for explicit Season approval before editing `protocol.toml`.
9. After approval, edit `protocol.toml`, update `rationale.md`, record approval
  in the proposal JSON, and run `baseline`.

Do not inspect Train results, OOS results, PnL, Sharpe, PSR, Calmar, win rate, or
prior attempt outcomes to choose protocol values. Setup is mandate fitting, not
candidate fitting.

## Brief Template

The filled brief is the CLI input. Use Season's mandate for the human-owned
values; fill the remaining protocol fields from the current protocol, data
readiness, and the recommendation rules below. Values shown here mirror the
current protocol where a neutral default is useful; they are not automatically
approved for every strategy.

```toml protocol-brief
mechanism = ""
observable = ""
falsifier = ""
horizon = ""
decision_cadence = ""

data_needs = []
data_kind = ""
dataset = ""
train_start = ""
train_end = ""
load_start = ""
load_end = ""
bar_cadence = ""
annualization_periods_per_year = 525600

symbols = []
universe_artifact = ""
exclusions = []

capital_notional = 1000000.0
adv_lookback_bars = 1440
adv_min_observations = 60
max_bar_participation = 0.50
max_adv_participation = 0.25
impact_coefficient_bps = 10.0
impact_exponent = 0.5

max_gross_exposure = 1.0
max_net_exposure = 1.0
risk_budget_mode = "calibrate_vol"
target_volatility = 0.15

objective_subwindows = 6
min_trades = 120
min_trades_per_subwindow = 12
min_return_sample_count = 100
min_effective_sample_size = 50.0
max_symbol_concentration = 0.70
min_cost_stress_return_retention = 0.50
max_abs_drawdown = 0.25
min_annualized_return = 0.10

max_iterations = 50
baseline_grace_iterations = 50
plateau_patience = 50
min_abs_improvement = 0.001
min_rel_improvement = 0.0
max_components = 3
max_params = 50

editable_params = []
baseline_expectations = ""
```

## Recommendation Rules

State these recommendations plainly in the review table:

- `score_haircut_se = round(sqrt(2 * ln(max_iterations)), 2)`;
- target volatility maps to `[risk_budget].target_volatility`;
- max tolerable drawdown maps to `[gates].max_abs_drawdown`;
- minimum annualized return maps to `[gates].min_annualized_return`;
- `annualization_periods_per_year` comes from data cadence and market calendar,
and must be reviewed for every new data kind or bar cadence;
- Train causality stays bounded on `output.causality_check = "micro"`;
- provide either explicit `symbols` or a `universe_artifact`;
- when both `symbols` and `universe_artifact` are present, the ordered lists must
match exactly;
- a resolver artifact is an eligibility filter from catalog/readiness metadata,
not a return ranking.

Common annualization values:


| Data cadence                     | Value    |
| -------------------------------- | -------- |
| 24/7 crypto daily                | `365`    |
| 24/7 crypto hourly               | `8760`   |
| 24/7 crypto minute               | `525600` |
| US equity daily                  | `252`    |
| US equity regular-session minute | `98280`  |


## Proposal Command

When using an eligibility-based universe, first resolve the symbol list:

```bash
conda run -n quant python -m loop resolve-universe \
  --data-kind crypto_perp_funding \
  --dataset crypto_perp_1min_with_funding \
  --start 2025-03-01 \
  --end 2025-12-31 \
  --exclude MATIC-PERP \
  --out .autoresearch/universe/latest.json
```

Then reference the artifact in the setup brief:

```toml
universe_artifact = ".autoresearch/universe/latest.json"
```

`resolve-universe` uses catalog symbol constants and readiness metadata only. It
does not edit `protocol.toml`, run Train, or inspect results.

```bash
conda run -n quant python -m loop propose-protocol \
  --brief .autoresearch/protocol_briefs/latest.md \
  --out .autoresearch/protocol_proposals/latest.json
```

The command writes `.autoresearch/protocol_proposals/latest.json` and
`.autoresearch/protocol_proposals/latest.md`. It does not edit `protocol.toml`.

## Approval And Baseline

After Season approves:

1. Edit `protocol.toml` intentionally.
2. Compare the edited protocol against the approved recommendation table. Show
  any intentional delta before marking approval.
3. Update `rationale.md` with mechanism, observable, falsifier, assumptions,
  editable params, and the first failure mode to watch.
4. Ensure `results.tsv` is absent or header-only and
  `.autoresearch/thesis_lock.json` is absent.
5. Set `approval.approved = true` in the proposal JSON.
6. Set `approval.protocol_sha256` to the SHA-256 of the approved `protocol.toml`.

Then run:

```bash
conda run -n quant python -m loop baseline \
  --mechanism "<why it should work>" \
  --falsifier "<what kills it>" \
  --approved-proposal .autoresearch/protocol_proposals/latest.json
```

`baseline` refuses to run when the proposal is missing, unapproved, stale versus
the current `protocol.toml`, or when active lifecycle state already exists. When
the preflight passes, it delegates to the normal `climb` path and writes the
standard attempt row and run card.
