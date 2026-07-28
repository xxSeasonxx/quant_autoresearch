# Attempt-0040 capacity sensitivity

## Question

At what `[account].initial_notional` does capacity prevent the frozen
`crypto_perp_tsmom_majors` attempt-0040 survivor from reaching its 15% volatility
target?

This is a Train-window diagnostic, not a Train attempt, OOS evidence, or promotion
evidence.

## Frozen inputs

- Candidate: two-sided attempt-0040 final survivor.
- Strategy SHA-256:
  `25e9af433c01dd8a9b93effcca3d59369190d163c00c197d7ffa94d43c937fe8`.
- Data-manifest SHA-256:
  `94e7317afa06b4aa5bc85cd8bd1a4f57062a2b9f23c74b1ce922374886fe2fa1`.
- Window: 2021-03-03 through 2025-12-31; BTC-PERP, ETH-PERP, and SOL-PERP.
- Runner: `quant_strategies` commit
  `5aeb6a5a2a52716d5cd60097b57a3245b482635e`.

All seven runs have identical strategy-snapshot and data-manifest hashes. Their
configs differ only in `[account].initial_notional` and `output.results_dir`.
The capacity model uses `average_bar_impact` with the frozen 1,440-bar lookback,
60-observation
minimum, 25% average-bar cap, 50% bar cap, or impact parameters.

The runner recorded a dirty tracked diff that only raises the universe mark-loader
row ceiling from 20 million to 48 million. These three-symbol runs load 7.65 million
execution rows, so the changed ceiling is not reached.

## Results

| Notional | Target reached | Book scale | Max feasible scale | Deployed vol | Max feasible vol | Total return | Impact return |
| ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: |
| $10k | yes | 0.250030 | 1.000000 | 15.0002% | 56.9478% | 105.0374% | 0.0297% |
| $100k | yes | 0.250030 | 1.000000 | 15.0002% | 56.9479% | 104.9520% | 0.0937% |
| $1.0m | yes | 0.250027 | 0.392634 | 15.0000% | 23.2620% | 104.6806% | 0.2961% |
| $1.5m | yes | 0.250027 | 0.301394 | 15.0000% | 17.9969% | 104.5921% | 0.3625% |
| $1.6m | yes | 0.250003 | 0.288426 | 14.9986% | 17.2427% | 104.5635% | 0.3743% |
| $1.9m | yes | 0.250028 | 0.255891 | 15.0001% | 15.3434% | 104.5322% | 0.4079% |
| $2.0m | **no** | 0.246731 | 0.246731 | 14.8068% | 14.8068% | 102.7352% | 0.4068% |

| Notional | Max average-bar participation | Max bar participation | Max event utilization |
| ---: | ---: | ---: | ---: |
| $10k | 0.0744% | 0.2549% | 0.51% |
| $100k | 0.7443% | 2.5487% | 5.10% |
| $1.0m | 7.4405% | 25.4761% | 50.95% |
| $1.5m | 11.1595% | 38.2089% | 76.42% |
| $1.6m | 11.9016% | 40.7497% | 81.50% |
| $1.9m | 14.1343% | 48.3936% | 96.79% |
| $2.0m | 14.6048% | 50.0000% | 100.00% |

The observed capacity transition is
`target_reached = true` at $1.9m and `false` at $2.0m. The $1.9m deployed-path
diagnostic estimates a first-order crossover of $1.963m, inside that observed
bracket.

## Conclusion

Capacity does not bind at the operator's expected $10k-$100k capital: the 15%
target is reached and peak event utilization is at most 5.10%. Under the current
capacity assumptions, the same frozen strategy stops reaching the target between
$1.9m and $2.0m.

This study validates sensitivity to notional under the configured model; it does
not calibrate the participation caps or impact coefficient. The study predates
venue selection and therefore does not establish minimum-order or fixed-order-
cost feasibility. Lot, quantity-step, price-tick, and contract-multiplier
constraints remain outside the engine. Every run emitted the same micro-causality
timeout warning, so these diagnostics do not add causality or retention evidence.

Generated configs and artifacts are retained locally under
`quant_strategies/results/capacity-sensitivity/attempt-0040/`.
