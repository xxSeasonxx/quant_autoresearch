# Harness & Docs Review — `program.md`, `AGENTS.md`, and the Train loop

**Status:** point-in-time review, 2026-07-20. This is an evidence record and recommendation set, **not** an active contract — do not treat it as governance or wire it into the loop. Owning contracts stay in `program.md`, `protocol.toml`, `docs/score_research.md`, and the module docstrings.

> **Update 2026-07-20 — P0 applied.** Action-map items 1–6 (the `program.md` / `README.md` / `AGENTS.md` language fixes) and item 21 (F8) are implemented; `program.md` was rewritten 404→279 lines with every durable contract preserved. **Line references below describe the pre-fix docs** and are kept as the rationale for the change. P1/P2 items remain open.
>
> **Update 2026-07-21 — P1 applied (full suite green, 92 passed).** Shipped, some with a deliberately different shape than first proposed: **item 7 (F13)** — lowered `max_iterations` to 30 with `plateau_patience == max_iterations` (a fixed budget with no machine auto-stop, per Season) plus a load guard rejecting `plateau_patience`/`baseline_grace_iterations` above `max_iterations`, and corrected the plateau claim in `program.md`/`README.md`; **item 12 (F15)** — a loose PnL-share inverse-HHI `effective_symbol_count` floor gate (`min_effective_symbol_count = 2.0`; exposure-based breadth is not emitted upstream, so the metric is PnL-share); **item 8 (F11)** — surfaced `max_positive_subwindow_return_share` as a run-card/ledger **diagnostic**, not a gate (Season's call; the proxy is a return ratio, not currency PnL); **item 13 (F16)** — bound `universe_resolver_sha256` into `protocol.toml` (covered by `protocol_sha256`) and the runtime `thesis_lock.json`, and threaded it through the onboarding recommendation, so provenance is explicit-and-bound rather than silently absent (a bare list is recorded, not hard-forbidden, preserving the legitimate explicit-list case); **item 11 (F14)** — the component parser fails closed on a missing/empty Signal Components section (the `max_params`/count-consumed tightening was dropped as an unexercised path); **item 19 (F25)** — unit-tested `_stop_reason_after_attempt` and deleted the dead `plateau_reached`/`max_iterations_reached`. **Deferred: item 9 (F10)** — recorded in `UPSTREAM_LIMITATIONS_TODO.md` as verify-first; the root fix is upstream. **Not done: item 10 (F22)** — the ≤5-sample premise was false (`economics.trades` is the full ledger), so impact is ~nil; and **item 14 (F7)** — subsumed by the P0 rewrite.

**Reviewer lenses:** skeptical quant researcher + LLM/prompt-design expert + adversarial red-team + harness engineer (four independent fresh-context passes reconciled against a direct line-by-line read of both docs and all seven harness modules).

**Method:** source code and frozen config are primary evidence; docs are claims audited against code. Upstream `quant_strategies` / `quant_data` behavior is taken from the consumer contract, not re-verified against upstream source (see Residual Risk).

---

## 1. Executive verdict

The foundation is **sound in its spine and over-built in its skin.** The evidence engine is trustworthy: one model of money (the netted-book NAV path, not a per-trade bag), a money-denominated score made honest by upstream vol-targeting and fail-closed exposure limits, gates read from the foundation rather than the trade sample, a schema-validated ledger, and per-attempt provenance snapshots. The intellectual core — *"idle notional earns nothing, so relieving a feasibility constraint is itself an alpha move"* — is a genuinely strong, correct framing that most shops never write down. **Keep all of that.**

The problems are concentrated in exactly the three places you flagged, and they share one root cause:

> **`program.md` over-invests words in norms the harness cannot enforce (don't stop early, don't launder the universe, keep it simple) and under-leverages the constraints the harness already enforces.** Prose is the weakest form of constraint for an LLM; the doc leans on it hardest precisely where the code is silent.

Consequences, mapped to your concerns:

- **Premature stopping (your pain #1):** the doc contains a *literal contradiction* that hands the agent a blessed early-exit ("enumeration closed"), and the one machine-checkable continue-signal is buried under ~7 softer restatements. This is the single highest-leverage fix in the review.
- **Over-constraint (your pain #2):** the contract is prohibition-dominated and imposes five mandatory per-attempt write/check artifacts, pushing a capable agent into compliance-and-paperwork mode instead of bold research.
- **Verbosity / contradiction (your pain #3):** ~1/3 of `program.md` is restatement; there are at least three genuine cross-doc contradictions (bounds editability, who writes `results.tsv`, the `docs/score_research.md` scope paradox).
- **Score (your Q5):** right *family*, one real gap — no robustness/consistency dimension is enforced anywhere, and the sole in-loop robustness gate (`train_strength`) rests on an upstream `n_eff` that barely discounts this thesis's overlapping holds.
- **Universe (your Q4):** conceptually excellent and hash-frozen, but return-blindness is setup-only and *optional*, and the "reduce the book, not the universe" norm has no teeth against threshold-laundering.

Nothing here corrupts the score or mis-selects keepers today. But the loop is a weaker foundation for *fast, legible, honest* iteration than the docs claim, and the docs are a weaker agent-prompt than their strong skeleton deserves. Both are fixable without a rewrite.

---

## 2. The core tension (the organizing insight)

Karpathy's `autoresearch` works *because* its `program.md` is short: one file, one metric, one loop, and the human trusts the loop. This repo deliberately trades that minimalism for quant rigor — and rigor is the right call. But rigor was added almost entirely as **prose rules in `program.md`**, and every added sentence has three costs: it is one more thing the agent must hold, one more surface for contradiction, and one more nudge toward caution over research.

The design principle to recover: **put each constraint at the lowest enforceable layer, and let the prose only explain what the code guarantees.**

| Constraint | Enforced by code? | So the prose should… |
|---|---|---|
| Gross/net ≤ budget, fail-closed | ✅ upstream | …explain in one line. (It over-explains: 4 places.) |
| Thesis identity frozen | ✅ lock hash | …explain in one line. (Good, but see F26 fragility.) |
| Gates / score / keep-rule | ✅ harness | …name the fields once and point to the owner. (Owner is out-of-scope; see F2.) |
| Loop won't stop before the cap | ✅ config (as tuned) | …but the *agent* can still stop itself, which code can't prevent → this is the one norm worth heavy, sharp prose (see F1/F5). |
| "Don't launder the universe" | ❌ | …is honor-system; harden with a gate (F15) instead of more paragraphs. |
| "Keep it simple" | ❌ (cap is inert) | …is honor-system; give the cap teeth (F14) instead of an ethos. |

Read the whole review through this lens: **cut prose where the code already binds; add code where only prose binds today; sharpen prose only where neither can be replaced by code (agent-initiated stopping).**

---

## 3. Scope & evidence inspected

- **Docs, line-by-line:** `program.md` (403 lines), `AGENTS.md` (`CLAUDE.md` is a byte-identical symlink — findings apply to both), `README.md`, `docs/score_research.md`, `docs/adr/0001-curated-few-research-regime.md`, `HISTORY.md`, `UPSTREAM_LIMITATIONS_TODO.md`, `rationale.md`.
- **Harness, full read:** `loop.py`, `objective.py`, `gates.py`, `protocol.py`, `universe_resolver.py`, `results_log.py`, `onboarding.py`; configs `protocol.toml`, `experiment.toml`; strategy surface `strategy.py`.
- **Cross-checks:** `tests/*`, `quant_strategies` consumer docs (score/sizing/causality/trade semantics).

**Live contract, confirmed from source (correcting stale notes):** ranking `score = realistic_costs.full_train.total_return` (`objective.py:257,291`); the book is vol-targeted upstream to 0.15 (`protocol.toml:41-45`, `calibrate_vol`); `train_strength` is a *separate binary gate*, full-Train `R − 2·SE ≥ 0` (`gates.py:165-172`). The `return_lcb_subwindow` / `money_floor` / `k_accept` scheme is fully superseded (`protocol.py:379` hard-rejects the old key); `HISTORY.md` still narrates it in present tense (F9).

---

## 4. What is right and must be preserved

These are load-bearing and correct. Protect them from "simplification" and from the fixes below.

1. **One model of money.** Scoring the netted-book NAV path, with the per-trade tape as derived attribution only (`objective.py:1-11`, `README.md:123`). Prevents PnL-bag cherry-picking. **Preserve.**
2. **Vol-targeting removes scale/leverage gaming.** Because the book is sized to 0.15 vol, total return is effectively *risk-adjusted return at the operator's budget, scaled by feasibly-deployed fraction* — and "leverage is magnitude too… not a knob you turn" (`program.md:196-203`) is a genuinely sophisticated instruction. **Preserve.**
3. **Fail-closed feasibility.** Exposure over budget is non-scoreable, never clamped (`protocol.py:58-69`). **Preserve** (but log it as its own verdict — F23).
4. **Capacity-as-alpha framing** (`program.md:24-26,206-219`). The standout contribution and directly on-thesis for "maximize return while feasible." **Preserve** — and pair it with the consistency gate (F11) so "deploy more" can't quietly mean "harvest more noise."
5. **Thesis lock for comparability** (`loop.py:183-223`) and **the "widest defensible mechanism / don't embed an editable lever in the identity" rule** (`program.md:126-134`) — subtle and correct. **Preserve** the rule; fix the re-entry fragility (F26) and relocate the *explanation* to setup (F7).
6. **Return-blind universe resolver + hashing** (`universe_resolver.py`). **Preserve**, and make it mandatory (F16).
7. **ADR-0001 "curated-few" scope.** The right altitude — it explicitly warns against bolting on automated-many machinery. **Use it to right-size every "add a gate/check" recommendation below**; prefer the lightest mechanism that gives the norm teeth.

---

## 5. Findings

Severity: **Critical / High / Medium / Low.** Action class: **Refactor / Simplify / Add / Retire / Preserve.** Each finding has file:line evidence, the first-principles reason it matters, and a recommendation. Redlines for the language items are in §6.

### A. Premature stopping (your pain #1)

**F1 — [Critical · Retire] The "enumeration closed" self-stop contradicts "only a configured stop rule ends the run."**
`program.md:269-274` says the run "ends at whichever comes first — the enumeration genuinely closed (… no new distinct hypothesis can be articulated …) or the `max_iterations` cap," and calls running out of ideas "the honest signal of near-exhaustion." This flatly contradicts `program.md:378-388` ("Do not conclude … before a configured stop rule fires … a judgment that 'research has converged' … is not a stop rule") and the harness, whose only terminal reasons are `plateau`, `max_iterations`, `complexity_exhausted`, `baseline_failure` (`loop.py:882-898`) — enumeration-closure is **not** among them. *Why it matters:* "I can't articulate a new distinct lever" is a subjective test the agent can satisfy whenever it wants to stop, and the text explicitly blesses it as a run-*ending* condition. An LLM resolving a contradiction defaults to the reading that lets it finish. This is the most direct enabler of your #1 pain. **Fix:** make enumeration drive *what to try next*, never *whether to stop*; delete the "ends at… enumeration closed… or max_iterations" clause and the "near-exhaustion" terminal framing. Redline in §6.1.

**F5 — [High · Refactor] The one machine-checkable continue-signal is buried under ~7 restatements.**
The bright line — *the run is not done while the latest run card shows `continuation: allowed`* — appears once, mid-paragraph (`program.md:383-384`), while the softer "don't stop early" sentiment is restated at L64-67, L213-215, L269-274, L332-335, L363-369, L390, L398-399. *Why it matters:* repetition does not linearly strengthen an instruction; past ~3 restatements an LLM habituates and the phrases blur — and the *only* form it cannot rationalize around (a printed flag) reads as one exhortation among many. **Fix:** promote a single imperative "Continue rule" to the top of *Stop* and cut 4-5 soft restatements. Redline in §6.2.

**F18 — [Medium · Add] Agent-initiated early stop is invisible.**
The loop is agent-invoked; nothing forces the next `climb`. If the agent simply stops while `continuation: allowed`, no `terminal_manifest.json` is written and there is no machine-detectable record that the run was abandoned early (`loop.py:1319-1329`). *Why it matters:* the harness genuinely cannot force the agent to continue — so make abandonment *visible* to you. **Fix:** add a `status` command note or a `loop_incomplete` marker whenever the last row is non-terminal, so an early stop is auditable.

### B. Over-constraint & the compliance trap (your pain #2)

**F4 — [High · Simplify] Prohibition-dominated tone + five mandatory per-attempt artifacts push the agent into paperwork/caution.**
The doc is dominated by "Do not / Never / fails closed / non-scoreable" (L21-22, 58, 73, 80-92, 116-120, 156-166, 189-206, 237-238, 304-306, 332-345, 382-388); affirmative "what to do" is concentrated in only two places (L282-301, L311-349). The author patches the resulting timidity with abstract pep-talk — "do not confuse caution with passivity" (L279), "This is a bias, not a cage" (L373) — which is itself a tell that the baseline tone over-constrains. Compounding it: **five overlapping required artifacts per iteration** — the 5-point Quant Research Standard statement (L221-232), `rationale.md` refresh (L327), Lever Enumeration update (L266), a dated Reseed Log line *every attempt* (L395-397), and a post-edit causality review (L248-251). *Why it matters:* concrete prohibitions beat abstract encouragement in an LLM's action selection, so "be bold" loses to 20+ "do not"s; and heavy per-loop documentation shifts the model into compliance mode, burns context, and slows the compute-bound loop — the opposite of the "run while Season is away" cadence. **Fix:** lead each section with the affirmative move and subordinate the guardrail; collapse the five artifacts into **one** structured `rationale.md` entry (mechanism / observable / falsifier / expected book effect / result / next lever), and make the Reseed Log an *as-warranted* note, not a per-attempt line.

**F8 — [Medium · Refactor] "If the available evidence cannot explain the result, do not edit" invites stall.**
`program.md:237-238`. Phrased as a prohibition on acting, it reads as "when confused, freeze," which collides with the never-stop mandate (no edit → no climb, yet told not to conclude). **Fix:** redirect to an action — "if you cannot explain the last result, your next step is to gather the missing diagnostic (trade tape, failure class, gate detail), not a blind edit and not stopping."

### C. Verbosity, duplication & contradiction (your pain #3)

**F3 — [High · Refactor] Three genuine cross-doc contradictions, with no stated precedence.**
- **(a) Editable bounds.** `README.md:33` says the agent edits `experiment.toml [params]` *"within the existing `[bounds.*]`"*; `program.md:109-112,136-140` says *"You own this search space … widen or tighten it … Widening or tightening a bound is an ordinary loop edit."* Opposite instructions on whether bounds are editable.
- **(b) Who writes the ledger.** `README.md:80` (step 8): *"Append one compact row to `results.tsv`"*; `program.md:304-306` and loop step 7: *"Do not append `results.tsv` yourself."* A first-time agent following README can corrupt scan state.
- **(c) No precedence rule.** README presents `program.md` as the contract (L23) but never says it wins on conflict.
**Fix:** correct README to match `program.md` on both, and add one line: *"On any conflict, `program.md` and `protocol.toml` govern."* Redlines in §6.3-6.4.

**F2 — [High · Refactor] The score/gate authority is out-of-scope for the agent that must follow it.**
The North Star points to `docs/score_research.md` for the score and gates (`program.md:17-20`), and the loop steps require parsing gate/score fields (L322-324) — but that file is **absent from the in-scope list** (L48-56) and L58 says *"do not browse the rest of this repo."* *Why it matters:* the definitional owner of the contract is formally off-limits; a literal agent faces a contradiction, and a first-time agent cannot find the field semantics it must use. (The raw `continuation`/`stop_reason` values do reach the agent via the run card, so the operational signal survives — but the *semantics* do not.) **Fix:** add `docs/score_research.md` to the in-scope set (a frozen contract is not "browsing"), or inline the ~6 field names the loop parses.

**F6 — [Medium · Simplify] High-frequency duplication across the always-read corpus dilutes salience.**
"A Train survivor is only a candidate, not deployability proof" appears 5+ times (`program.md:16-18,28-30,390-392`, `AGENTS.md:58`, `README.md:5,84`, `score_research.md:140`); "generated artifacts are evidence not source," "don't hide data/cost/fill limits," "leverage/scale is not a knob," and "protocol is frozen" each recur 3-5 times. *Why it matters:* when everything is emphasized, nothing is; the agent can't separate load-bearing rules from mantra, and the 403-line contract is re-read every session. It also violates the repo's own MECE doc rule (one owning section per contract). **Fix:** state each once in its owning section; `AGENTS.md`/`README.md` already defer to `program.md`, so drop their restatements. Removes ~80-120 lines with zero contract loss.

**F7 — [Medium · Simplify] Setup/reseed-scoped essays are loaded into the iteration contract.**
The universe multiple-testing / "direction of flow" essay (L168-176) and the mechanism-identity rules (L126-134) govern things *frozen during ordinary iteration* (the universe can't change; the identity is set at setup). They are two of the densest passages in the doc and change no iteration behavior. **Fix:** compress each to one line in `program.md` and move the reasoning to the `new-thesis-setup` skill / `HISTORY.md`.

**F9 — [Low · Refactor] `HISTORY.md` narrates superseded score schemes in present tense.**
Its lower sections describe `return_lcb_subwindow` / `money_floor` / `significance` / `k_accept` as if current; only the top section states the cutover. **Fix:** add a one-line "current contract lives in `docs/score_research.md`" banner and past-tense the superseded sections. (Low; it is correctly *in* HISTORY, just ambiguous.)

### D. Is the score the right metric? (your Q5)

**Verdict: right numerator, under-penalized for overfitting.** Full-window realistic-cost total return on a vol-targeted book captures exactly what Sharpe/PSR/Calmar cannot — duty cycle, idle drag, compounding, and (when capacity binds) deployable scale — so it ranks *tradeable dollars under feasibility*, and the fixed 0.15 vol target quietly normalizes realized volatility (ranking ≈ realized Sharpe when capacity is slack, Sharpe × deployable-vol when it binds). Keep the objective. The gaps:

**F10 — [High · Add/Refactor · partly upstream] The sole in-loop robustness gate rests on a lag-1-only `n_eff`.**
`train_strength` is `R − 2·SE ≥ 0` with `SE = σ·P/√n_eff` (`objective.py:227,327-343`), i.e. a t≥2 test on the at-risk per-minute return series. But upstream `effective_sample_size` is a *lag-1* autocorrelation adjustment capped to `[1, sample_count]` (`quant_strategies` reference). This thesis holds ~720-min positions on a 240-min cadence (`experiment.toml:32-33`), so at-risk minute returns are positively autocorrelated across *hundreds* of lags; a lag-1 adjustment leaves `n_eff ≈ sample_count`, understating SE and overstating t. `min_effective_sample_size=50` runs on the same `n_eff`, so it does not backstop. *Why it matters:* this is the hinge of score honesty — the one gate meant to reject weak edges can pass a materially weaker true edge for a multi-hour-hold strategy. **Fix:** anchor the strength evidence unit to *independent bets* (≈ closed-trade / decision count), not autocorrelation-thin minutes — a consumer-side change; and file an `UPSTREAM_LIMITATIONS_TODO.md` item for a block/Newey-West `n_eff`. **Verify first:** the realized multi-lag ρ-profile of the at-risk NAV series (upstream-owned; if autocorrelation is material this is Critical, not High).

**F11 — [High · Add] Time-slice concentration is computed but ungated — contradicting your own falsifier.**
Six subwindows are computed and required for `minimum_evidence`, but subwindow *return* is excluded from both score and gates (`gates.py:24-29`, `score_research.md:79-81`), while `rationale.md:81` lists *"returns depend on one symbol or one time slice"* as a kill condition. Symbol concentration **is** gated (breadth ≤ 0.70); there is no time analogue. A strategy earning all its PnL in one subwindow passes `minimum_evidence`, `train_strength` (the full-window t-stat is invariant to *when* the return occurred), and `path_risk`, then tops the ranking. The `gates.py:28-29` claim that a slice gate "duplicates the full-Train strength calculation" is **wrong** — temporal concentration is an axis the full-window stat cannot see. *Why it matters:* this is the enforceable fix for the score's robustness gap, and it is the cleanest one because it does **not** re-introduce a ranking haircut. **Fix:** add a time-concentration gate *mirroring the symbol-breadth gate* — cap any single subwindow's share of total positive PnL (not "all six positive," which induces worse overfitting and duplicates the OOS regime test).

**F12 — [Medium · Refactor] Point-estimate ranking over a forced ~50-way search climbs the luckiest gate-passer.**
The score is a raw point estimate; `is_improvement` ranks purely on it among gate-passers (`objective.py:391-412`); the only robustness filter is the binary floor at 0. Over up to 50 attempts with a fixed (non-deflating) 2-SE hurdle, this is unpriced multiple-testing — the survivor is the max of ~50 noisy draws. *Reconciliation (important):* the obvious fix — an SE haircut on the ranking — was **removed on purpose** (`HISTORY.md`) so that low-duty / capacity-relieving books are not penalized for their higher SE. Re-adding it would fight your capacity-as-alpha principle. **Prefer instead:** (i) the consistency *gate* (F11), which catches luck without penalizing duty cycle, and (ii) fixing the stop config (F13) so the loop is not a forced best-of-50. Treat a lower-variance ranking discount as a last resort only if F11+F13 prove insufficient.

### E. Universe / symbol tuning (your Q4)

**Verdict: conceptually excellent, operationally under-enforced.** The frozen-universe-vs-active-book split, "reduce the book not the universe," and treating cross-universe search as unpriced multiplicity resolved only downstream are all correct and more rigorous than most shops write down. But they are *guidance*, backed by only a loose gate.

**F15 — [High · Add] Breadth gates the wrong quantity; the honest breadth measure is ungated.**
The breadth gate caps one name's *realized-PnL share* at a loose 0.70 (`gates.py:241-245`), and `min_cross_section`/`top_n` bounds permit a 1-2 name book (`experiment.toml:78-84`). Meanwhile `effective_symbol_count` — a real Herfindahl breadth measure — is computed and logged but **never gated** (`loop.py:539`, `objective.py:92`). *Why it matters:* this is the teeth your Q4 laundering concern lacks. An agent can tune the threshold battery (`min_abs_funding_bps`, `min_idiosyncratic_*`, `top_n`, side toggles) until the signal effectively fires only on names that historically paid — formally signal-driven, actually return-informed — and still pass 0.70. `program.md:162-166` names this exact exploit; nothing enforces it. **Fix:** gate `effective_symbol_count` (a floor on effective names traded) and/or tighten `max_symbol_concentration`, and measure concentration on *exposure/trade count*, not realized PnL.

**F16 — [Medium · Refactor] Return-blindness is setup-only and *optional*.**
`symbols == resolver.resolved_symbols` is enforced only when a universe artifact is supplied (`onboarding.py:161-162`); a bare hand-typed symbol list with `universe_resolver_sha256=None` is permitted with only a soft warning (`onboarding.py:578`). The loop then reads `protocol.data.symbols` directly and never re-resolves. *Why it matters:* a lifecycle can freeze a symbol list with no return-blind provenance at all — the guarantee your Q4 relies on is skippable. **Fix:** require a resolver artifact + hash for every lifecycle (forbid the bare-list path), and record the resolver hash in the thesis lock.

**F21 — [Low · Refactor] `rationale.md` invites the exact information that enables laundering.**
`rationale.md:96` directs the agent to *"inspect per-symbol economics"* before edits; that per-symbol return knowledge is what makes threshold-laundering possible, while `program.md` forbids using it to pick names. Mild self-undermining. **Fix:** pair the instruction with the guard — "inspect per-symbol economics to understand the mechanism, not to select names; breadth is signal-driven and measured by `effective_symbol_count`."

**F19 — [Low · Add · Season-level] Cross-lifecycle universe multiple-testing is unenforced.**
`program.md:167-176` correctly frames trying several universes as unpriced multiplicity, but nothing logs the universes a thesis line has tried or binds downstream OOS to all of them. **Fix (operator-level):** keep a tried-universe ledger and require OOS to span every universe a thesis touched. Low; it needs Season-level reseeds to trigger.

### F. Harness correctness & iteration ergonomics (supporting)

**F13 — [High · Refactor] The stop taxonomy collapses to "run exactly 50, then stop."**
`plateau_patience = max_iterations = baseline_grace_iterations = 50` (`protocol.toml:58-62`). Plateau needs ≥50 non-improving rows *after* a keep, but the cap fires at 50 attempts total, so **plateau can never fire** (`loop.py:874-898`); `baseline_failure` also can't fire before the cap. The only terminations are `max_iterations`, `complexity_exhausted` (agent-controlled — F14), or `baseline_failure` at exactly 50. Onboarding's own recommended brief uses `plateau_patience=30` (`tests/test_onboarding.py:145,219`), so the frozen 50 looks like a hand-edit that silently disabled convergence detection. *Why it matters:* with minute-replay compute as the binding constraint, a converged thesis is *contractually forced* to burn all 50 heavy attempts — and `program.md:378` / `README.md:82` advertise plateau as a real safeguard that cannot fire. **Fix:** set `plateau_patience` strictly `< max_iterations` (e.g. 20-30) and add a load-time guard in `protocol.py`/`onboarding.py` rejecting `plateau_patience >= max_iterations` and `baseline_grace_iterations >= max_iterations`. If the forced-50 is *intended* (anti-premature-closure via config), say so in the docs and drop the plateau language.

**F14 — [High · Refactor] The complexity cap is honor-system and effectively inert.**
`complexity_value = max(component_count, param_count)` (`gates.py:126-128`), where `component_count` is the number of `### Component:` headings the agent writes in `rationale.md` (`loop.py:71-115`) and `param_count` is `len(experiment.toml [params])` (~35, cap 50). Neither reflects `strategy.py`, which is ~42 KB with dozens of conditional branches, enum arms (`weighting`, `idiosyncratic_mode`, `selection_score`), and hardcoded constants under "3 components." Worse: `validate_params` merges `_DEFAULT_PARAMS` (`strategy.py:135`), so a knob can live in code with a default and never appear in `experiment.toml`, escaping `max_params` entirely; and a heading typo makes the parser return **zero** components with a warning (`loop.py:102-114`) — weakening the gate instead of failing closed. *Why it matters:* "simplicity wins ties" (`program.md:276-280`) is unenforced, and the one early stop the agent *can* trip (`complexity_exhausted`) is self-reported. **Fix (right-sized per ADR-0001, not full AST):** tighten `max_params` materially (e.g. 15-20) so the cap can bind; count params *actually consumed* rather than only declared; and fail closed on a missing/empty Signal Components section.

**F22 — [High · Refactor] Four steering diagnostics are computed from the ≤5-trade sample and contradict `trade_count`.**
`win_rate`, `profit_factor`, `avg_trade_net`, `cost_return_sum` are computed over `economics.trades` (`loop.py:540-551`), which is the bounded diagnostic sample (`protocol.toml:53` `diagnostic_sample_trades=5`), while `trade_count` in the same row is the authoritative full-book count (`loop.py:531`). So a row can read `trade_count=300` beside a `win_rate` from 5 trades, and the run card carries no authoritative cross-check. Upstream exposes full-book `economics.hit_rate / profit_factor / average_trade_net / sum_cost_return`. *Why it matters:* score and gates are unaffected (they read the foundation), but `program.md:234-238` explicitly tells the agent to steer next edits by these diagnostics — so four columns actively mislead the research loop. **Fix:** populate the ledger from the authoritative `economics.*` scalars; keep the trade sample for spot inspection only.

**F23 — [Medium · Refactor] Infeasible runs are logged identically to code crashes.**
A `leverage_budget_breach` / `capacity_limit_breach` is an economic verdict, but `loop.py:1191-1214` routes it to `_finalize_crash`, which hardcodes `status="crash"`, `failure_class="run_error"` (`loop.py:454,478`); the typed reason lands only in `failure_reason`/`note`. *Why it matters:* `program.md`/`score_research.md` insist "infeasible is no score, not a low score, a distinct verdict" — yet the ledger labels it a harness error, so an agent scanning `failure_class` may read a feasibility outcome as a bug. **Fix:** give infeasible its own `failure_class` (e.g. `infeasible`) or status.

**F24 — [Medium · Refactor] `failure_class` disagrees between `results.tsv` and `run_card.json` for crashes.**
`_make_crash_row` hardcodes `run_error` (`loop.py:478`) while `_write_run_card` computes it via `_failure_class` (`loop.py:863`); for a foundation-parse crash the run card says `foundation_unavailable` and the ledger says `run_error` for the same attempt. **Fix:** have `_make_crash_row` call `_failure_class` so the two artifacts agree.

**F25 — [Medium · Add/Retire] The production stop logic is untested; a parallel tested implementation is dead.**
`objective.plateau_reached` / `max_iterations_reached` (`objective.py:415-429`) are unit-tested but **not imported by `loop.py`**; the logic actually used (`_stop_reason_after_attempt`, `loop.py:874-898`) has no test. The real terminal behavior — including the F13 defect — is unverified, and a direct test would have caught it. **Fix:** unit-test `_stop_reason_after_attempt`; delete the dead `objective.py` helpers or wire the loop to them.

**F17 — [Medium · Add] The ledger is structurally validated but not reconciled to run cards.**
`_validate_result_chain` enforces contiguity/uniqueness/terminal-last only (`results_log.py:216-237`); it never reconciles `score`/`gates_passed`/`status`/`stop_reason` against the attempt's `run_card.json`, and the loop recomputes best-score and stop-state fresh from the ledger every climb. A single hand-edit (the doc forbids it, but forbidding is the only guard) silently changes the survivor. *Right-sized fix (per ADR-0001, not a hash chain):* on read, recompute `score`/`gates_passed` from each attempt's run card and refuse on mismatch.

**F26 — [Medium · Refactor] The thesis identity is re-passed as free text every climb; a paraphrase wedges the lifecycle.**
`climb` requires `--mechanism`/`--falsifier` each call and `_ensure_active_thesis_lock` raises "active thesis identity changed; start a new thesis lifecycle" on any wording change (`loop.py:218-219`), normalizing only whitespace. *Why it matters:* an autonomous LLM regenerating CLI args across ~50 calls can easily paraphrase and hard-stop its own run (`reset` archives `results.tsv` — recoverable, but disruptive). **Fix:** after lock creation, source the identity from the lock (or `rationale.md`) so `climb` need not re-pass it; offer a non-destructive re-sync.

**F20 — [Low · Preserve/Retire-concern] Causality micro-timeout does *not* over-kill (retract stale concern).**
Upstream: a micro timeout "may still score"; only a *detected violation* fails closed. `_causality_admissible` reads `evidence.causality_admissible` (True on timeout) and only falls back to `verified` on legacy objects (`loop.py:679-696`); the gate passes iff admissible (`gates.py:259-265`). Train gates on *admissibility*, OOS requires *verification* — a correct firewall. **Any prior "timeout over-kills" note is stale.** Residual: on a legacy upstream result lacking `causality_admissible`, the fallback would over-kill on timeout; and `selected_probe_count`/`timed_out` are ungated, so a near-zero-coverage replay could pass — an upstream-semantics question (Residual Risk).

**F27 — [Low · Refactor] One flat subwindow makes a valid full-window return non-scoreable.**
`_window_return_se` returns `None` on zero variance, and any `None` window forces `score=None` (`objective.py:225,267-286`). A sparse edge with one quiet subwindow is dropped as `score_unavailable` despite a valid `total_return`. Documented as intended, but harsh for the sparse edges the North Star wants to allow, and surfaced only as a coarse `failure_class`. **Fix:** treat a zero-variance subwindow as a diagnostic, not a score-killer, or surface the specific window in the ledger reason.

**F28 — [Low · Refactor] `reset` orphans the attempt artifact tree.**
`reset_lifecycle` archives `results.tsv`, the lock, and `.autoresearch/quick/`, but leaves `results/autoresearch/attempt-*/` (run cards, snapshots, terminal manifests) in place (`loop.py:1466-1492`), and `README.md:5` calls `results.tsv` "append-only." Stale higher-numbered dirs from a longer prior run can mislead. **Fix:** archive the attempt tree too, or note the reset scope explicitly.

---

## 6. Concrete redlines (highest-leverage language fixes)

These eight move the needle most. Apply piecemeal.

### 6.1 Kill the self-stop loophole (F1) — `program.md:269-274`

> **Before:** "…the run may not conclude while a plausible distinct lever is un-run and no stop rule has fired, and it ends at whichever comes first — the enumeration genuinely closed (every distinct lever has a result and no new distinct hypothesis can be articulated with a real mechanism) or the `max_iterations` cap. Running out of distinct hypotheses before the cap is the honest signal of near-exhaustion; manufacturing threshold-nudges to fill the cap is the dishonesty this forbids."

> **After:** "Maintain the Lever Enumeration to decide *what to try next*, never *whether to stop*. If no distinct lever remains, your next move is a larger structural variant or a genuinely new mechanism — not stopping, and not manufacturing threshold-nudges to look busy. Only the harness ends the run (see Stop); keep issuing attempts until it reports a stop reason."

### 6.2 One bright-line continue rule (F5) — new lead sentence of *Stop* (`program.md:377`)

> **Add, as the first line of Stop:** "**Continue rule — the only authority on whether the run is over:** if the latest `run_card.json` shows `continuation: allowed` and an empty `stop_reason`, immediately begin another attempt. Your own judgment that research has converged, that the envelope binds, or that you are out of ideas is *not* a stop and must not end the run."

Then delete the softer restatements at L332-335, L363-369, L390, L398-399 (keep the overfit checklist in *When The Loop Looks Overfit*).

### 6.3 Fix the editable-bounds contradiction (F3a) — `README.md:33`

> **Before:** "`experiment.toml` `[params]`, within the existing `[bounds.*]`"

> **After:** "`experiment.toml` `[params]` **and their `[bounds.*]` ranges** — you own the search space and may widen or tighten a bound as the mechanism demands (an ordinary loop edit, not a reseed)."

### 6.4 Fix the ledger-write contradiction + add precedence (F3b/F3c) — `README.md:80` and a new line

> **Before (step 8):** "Append one compact row to `results.tsv`; source provenance is preserved…"

> **After (step 8):** "Confirm `climb` appended exactly one row to `results.tsv`; do not write it yourself. Source provenance is preserved…"

> **Add near `README.md:23`:** "On any conflict between documents, `program.md` and `protocol.toml` govern."

### 6.5 Put the score contract in scope (F2) — `program.md:48-56`

> **Add to the in-scope list:** "`docs/score_research.md` for the frozen score, gate, and result-ledger field semantics (reading a frozen contract is not 'browsing the repo')."

### 6.6 Compress the universe guidance (F7/Q4) — replace `program.md:145-176` (four paragraphs) with

> "**Universe vs book.** The *universe* is the protocol-frozen, return-blind set of eligible names; changing it is a reseed, never a loop edit. The *active book* is how many of those names your signal holds — narrow it only through the signal itself (`top_n`, thresholds), never by naming names or by thresholds reverse-engineered to keep only past winners. Never compare Train scores across different universes; universe generalization is resolved only downstream, OOS. The breadth you land on is evidence to record, not a number to optimize. *(Rationale and the multiple-testing argument live in `new-thesis-setup` and `HISTORY.md`.)*"

### 6.7 Turn the stall prohibition into an action (F8) — `program.md:237-238`

> **Before:** "If the available evidence cannot explain the result, do not edit."

> **After:** "If you cannot explain the last result, make your next step *gathering the missing diagnostic* — the trade tape, failure class, or gate detail — not a blind edit and not stopping."

### 6.8 De-duplicate `AGENTS.md` Research Rules (F6) — `AGENTS.md:53-65`

Reduce the bullet list to the posture line and a pointer: "Think like a skeptical quant: bold about strategy research, conservative about evidence. `program.md` governs the loop; do not restate its rules here." (The bullets are all restated in `program.md`'s owning sections.)

---

## 7. Doc-vs-code mismatch table

| # | Doc claim | Code reality | Fix |
|---|---|---|---|
| 1 | `program.md:378`, `README.md:82`: plateau is an operative stop | `protocol.toml:58-62` (50/50/50) makes plateau unreachable | Config or docs (F13) |
| 2 | `README.md:33`: params edited within existing bounds | `program.md`: bounds are agent-owned | README (F3a) |
| 3 | `README.md:80`: agent appends `results.tsv` | `program.md:304`, `loop.py`: agent must not | README (F3b) |
| 4 | `program.md:17-20`: follow `docs/score_research.md` | that file is out-of-scope + "don't browse" (L48-58) | Add to scope (F2) |
| 5 | `score_research.md:92-127`: one `failure_class`/attempt | ledger `run_error` vs run card computed class | `loop.py` (F24) |
| 6 | `score_research.md:100`: `win_rate` etc. are book diagnostics | computed from ≤5-trade sample | `loop.py` (F22) |
| 7 | onboarding brief recommends `plateau_patience=30` | frozen protocol uses 50 | Reconcile (F13) |
| 8 | `README.md:5`: `results.tsv` "append-only" | `reset` renames it; artifact tree orphaned | Note scope (F28) |

---

## 8. Prioritized action map

Status = Open for all. Priority: **P0** = fixes your named pains directly / cheap and high-impact; **P1** = material correctness or Q4/Q5 teeth; **P2** = polish / Season-level.

| No. | Status | Priority | Finding | Action class | Owner surface |
|---|---|---|---|---|---|
| 1 | Done | P0 | F1 Kill "enumeration closed" self-stop | Retire | `program.md` |
| 2 | Done | P0 | F5 One bright-line continue rule; cut restatements | Refactor | `program.md` |
| 3 | Done | P0 | F3 Three cross-doc contradictions + precedence | Refactor | `README.md` |
| 4 | Done | P0 | F2 Put `score_research.md` in scope | Refactor | `program.md` |
| 5 | Done | P0 | F4 De-prohibit tone; 5 artifacts → 1 | Simplify | `program.md` |
| 6 | Done | P0 | F6 Remove duplication (~1/3 of doc) | Simplify | `program.md`/`AGENTS.md`/`README.md` |
| 7 | Done | P1 | F13 lower `max_iterations`; `plateau_patience == max` (no auto-stop) + load guard | Refactor | `protocol.toml`/`protocol.py`/`onboarding.py` |
| 8 | Done (diagnostic) | P1 | F11 Time-concentration surfaced as a diagnostic, not a gate | Add | `loop.py`/`results_log.py` |
| 9 | Deferred | P1 | F10 Anchor strength to independent bets; verify ρ / upstream `n_eff` | Add | `UPSTREAM_LIMITATIONS_TODO.md` |
| 10 | Skipped | P1 | F22 Ledger diagnostics (nil impact: `economics.trades` is the full ledger) | Refactor | `loop.py` |
| 11 | Done (fail-closed) | P1 | F14 Component parser fails closed on missing/empty section | Refactor | `loop.py` |
| 12 | Done | P1 | F15 Loose `effective_symbol_count` floor gate (PnL-share HHI) | Add | `gates.py`/`protocol.toml` |
| 13 | Done | P1 | F16 Bind `universe_resolver_sha256` into protocol + lock + onboarding | Refactor | `protocol.py`/`loop.py`/`onboarding.py` |
| 14 | Skipped | P1 | F7 Compress universe/identity essays (subsumed by P0 rewrite) | Simplify | `program.md` |
| 15 | Open | P2 | F12 Prefer F11+F13 over a ranking haircut (document the choice) | Refactor | `docs/score_research.md` |
| 16 | Open | P2 | F17 Reconcile ledger rows against run cards on read | Add | `results_log.py`/`loop.py` |
| 17 | Open | P2 | F18 Machine-visible early-stop marker | Add | `loop.py` |
| 18 | Open | P2 | F23/F24 Distinct `infeasible` class; agree crash class across artifacts | Refactor | `loop.py` |
| 19 | Done | P2 | F25 Test `_stop_reason_after_attempt`; delete dead helpers | Add/Retire | `tests/`/`objective.py` |
| 20 | Open | P2 | F26 Source identity from lock, not re-passed args | Refactor | `loop.py` |
| 21 | Done | P2 | F8 Stall prohibition → gather-diagnostic action | Refactor | `program.md` |
| 22 | Open | P2 | F9/F20/F21/F27/F28/F19 (HISTORY banner; retract causality note; rationale guard; flat-window; reset scope; tried-universe ledger) | Refactor/Add | various |

**If you do only five:** #1, #2, #3, #4 (all `program.md`/`README.md` — directly kill premature-stopping and the contradictions) and #8 (the time-concentration gate — the one enforceable close of the score's robustness gap).

---

## 9. Preservation constraints

Do not "fix" these; they are right-sized and load-bearing: the NAV-path score, upstream vol-targeting and fail-closed exposure limits, the thesis lock's *existence* (fix only its re-entry ergonomics), the return-blind resolver's *design* (make it mandatory, don't change it), the capacity-as-alpha North Star, and the ADR-0001 "curated-few" scope — which is itself the reason every "add a gate" recommendation above is deliberately the lightest mechanism that gives the norm teeth, not an automated-many validation platform.

---

## 10. Unknowns / residual risk

- **`n_eff` magnitude (F10):** I confirmed the *method* (lag-1, capped) from the consumer contract, not the realized multi-lag ρ of the at-risk NAV series. If autocorrelation is material, F10 is **Critical**, not High. Upstream-owned.
- **`calibrate_vol` estimator:** whether it targets ex-ante or realized vol is unverified; "score ≈ Sharpe when capacity is slack" is qualitative.
- **Trade-sample truncation (F22):** the contract labels `economics.trades` a "sample" under `diagnostic_sample_trades=5`; the exact count is upstream-owned. Sufficient to establish the defect; precise count unconfirmed.
- **Causality admissibility semantics (F20):** whether upstream can mark `admissible=True` on a near-zero-coverage or timed-out replay is upstream-owned and unverified.
- **Whether a return-blind resolver artifact actually backs the current 14-symbol universe:** the code path permits a bare list; I did not confirm a matching artifact/hash exists for this lifecycle.
- **No end-to-end execution:** all findings are read-only/reasoned from source; per F25 the production stop path is also untested in the suite.
- Upstream `total_return` / `max_symbol_concentration` / `effective_symbol_count` are trusted as-emitted (the harness fails closed on missing values but never audits them).

---

## 11. Not in scope

Strategy *alpha* quality (whether funding-crowding reversal is a real edge — that is what the loop and downstream OOS are for); OOS/paper/live tooling; upstream `quant_strategies`/`quant_data` internals; the `new-thesis-setup` skill beyond its stop-knob guard and the return-blind requirement; and any change to the thesis currently loaded in `rationale.md`.
