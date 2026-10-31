# Changes from the technical audit (31 Oct 2026)

Source: `OYTRA_AUDIT.md` (read-only audit, must-fix list §11 and Groq note §12), fixes approved by Ishan.
Backup of the pre-fix state: git tag `pre-audit-fixes`. Labels: [M] measured · model · HYPOTHETICAL.
Unchanged on purpose: thresholds 40/60/87.5, plain `config/rules.csv`, static offline dashboard and its design,
no new frameworks, no location/geocoding, backtests always use the rule judge.

## What changed

| # | Area | Change | Where |
|---|---|---|---|
| 1 | One NUDGE formula (C1) | `value()` is exactly the probability-weighted `breakdown()`. Prepaid take-up split into two HYPOTHETICAL rates (would-be-delivered 25%, would-be-RTO 10% base). Each cost counted once (1 message for CONFIRM; NUDGE = offer + confirmation only for non-switchers; discount + gateway fee only on delivered prepaid orders). | `oytra/economics.py`, `config/rules.csv`, `tests/test_audit_fixes.py` |
| 2 | CAC is not value | Marketing's ₹300 CAC removed from order value (`assumed_future_contribution_first_time_rupees` = 0). Reported separately as a Marketing metric: acquisition spend on first-time-labelled buyers we hold/cancel (sunk, not profit, not in net). | `economics.py`, `backtest.py`, dashboard, memo |
| 3 | Show the EV that drove the decision (C2) | Engine and backtest call the same `policy.apply_policy`; each order shows the ₹ of every action and says when the per-order ₹ estimate favours a different action. Argmax-EV is evaluated only as a comparison (walk-forward table C). | `oytra/policy.py`, `engine.py`, `walkforward.py` |
| 4 | Explicit precedence (C3) | Written-down order: band → first-time protect → unknown-history protect → hard data-quality rule → ₹0 order. KT100327 (repeat buyer, p 0.943, unusable address) is now CONFIRM, as rules.csv says. Test per row. | `docs/RULE_PRECEDENCE.md`, `policy.py` |
| 5 | WhatsApp (C4) | `keep_cod` intent ("keep COD", "cod rakho", …); confirmed-COD release counted once (`_release` idempotent); a late verified payment after the COD fallback is flagged `late_payment_after_cod_fallback` for refund review, not released again. Demo runs 13–14 added. | `oytra/whatsapp.py`, `oytra/llm.py`, `docs/WHATSAPP_FLOW.md` |
| 6 | rules.csv validation (C5) | Ranges (shares 0–1, non-negative ₹/hours), yes/no, enums, strictly increasing thresholds, missing/duplicate settings, https-only `RULES_CSV_URL`. Plain-English `RulesError`. | `oytra/config.py` |
| 7 | Customer history state | Every order gets `REPORTED_FIRST_TIME` / `REPORTED_RETURNING` / `UNKNOWN_OR_INCONSISTENT` from earlier orders only. Unknown history never moves an order towards HOLD. | `oytra/data.py`, `features.py` |
| 8 | History model chosen out-of-time | `no_history` vs `reported_history` vs `history_quality_flag` compared on Jun/Jul/Aug folds inside Apr–Aug; `reported_history` selected before September was looked at. | `oytra/history_variants.py`, `reports/history_model_selection.md` |
| 9 | Chronological encoding + time CV | Training pincode encoding uses earlier weekly blocks only; threshold optimiser uses out-of-time folds (diagnostic only, thresholds not applied). Leakage audit and variants switched to the same encoding. | `features.py`, `backtest.py`, `leakage_audit.py`, `variants.py` |
| 10 | Walk-forward Jun–Sep | Table A (fixed policy), table B (model + thresholds re-chosen from earlier months only), table C (argmax vs bands, 25% friction cap). Negative months shown. | `oytra/walkforward.py`, `reports/walkforward.md`, dashboard |
| 11 | Reporting honesty | "Latest day in data (30 Sep 2026)" with its measured 9 orders (previously an approximate "about ten orders" under a "Yesterday" label); "flagged, not prevented"; September labelled a retrospective holdout; ECE added; consistency script checks every headline number across reports, dashboard, memo and README and bans retired wording. | `dashboard*.py`, `scripts/check_consistency.py` |
| 12 | Groq LLM, opt-in | `GROQ_API_KEY` (env only, never written), `OYTRA_USE_LLM=0` by default, JSON mode, model `openai/gpt-oss-20b`, prompt version `judge-v2` in the cache key. 60-case synthetic eval with draft labels for human review. `.env` git-ignored, `.env.example` has an empty key. | `oytra/llm.py`, `scripts/llm_eval.py`, `reports/llm_eval.md` |

Also: `docs/THRESHOLD_MATHS.md` rewritten (no CAC, numeric break-evens, data-mean column) and re-checked by
`scripts/check_threshold_maths.py`; AI_USAGE_LOG placeholder removed; DECISION_LOG #32–#40.

## Old vs new headline numbers (September, 329 orders, 86 RTO [M])

| Metric | Before | After | Why it moved |
|---|---|---|---|
| AUC (model) | 0.736 | 0.738 | chronological pin encoding |
| PR-AUC / Brier (model) | 0.535 / 0.1644 | 0.534 / 0.1643 | same |
| ECE, 10 bins (model) | not reported | 0.042 | new |
| Ship / Confirm / Nudge / Hold | 259 / 52 / 17 / 1 | 272 / 55 / 2 / 0 | precedence fix (hard rules beat NUDGE/HOLD), new scores |
| Flagged orders, of which RTO [M] | 70, 37 | 57, 30 | same |
| RTO cost in flagged orders [M] | ₹6,268 | ₹5,082 | same |
| Base net, our rules (HYPOTHETICAL) | ₹1,087 | ₹1,387 | one NUDGE formula, no CAC, fewer nudges |
| Conservative / optimistic (HYPOTHETICAL) | −₹751 / ₹2,596 | −₹117 / ₹2,728 | same |
| Ops cancel rule (HYPOTHETICAL costs, [M] outcomes) | −₹27,095 | −₹16,595 | CAC no longer counted as value |
| Monthly projection at 1,650 COD orders (HYPOTHETICAL) | ₹5,452 | ₹6,956 | follows base net |
| HOLD-over-SHIP break-even, ₹649 | 65% repeat / 78% first-time | 64.8% for everyone | no CAC |

## Known limitations
- All ₹ are HYPOTHETICAL until a WhatsApp/prepaid pilot measures the rates; conservative is negative in 3 of 4 walk-forward months and base is negative in June.
- September was used during development, so it is a retrospective holdout, not an untouched test. Jun–Aug in table A also informed the thresholds.
- In September the no-history model scores more ₹ (HYPOTHETICAL ₹1,452) at a lower AUC (0.689); selection was made on Apr–Aug and not changed.
- LLM eval labels are drafts written by the assistant, and the offline rules were written by the same assistant, so rules-vs-draft agreement is optimistic. Needs Ishan's review.
