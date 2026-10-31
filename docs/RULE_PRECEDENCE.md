# Rule precedence (conflict resolution)

Written **before** the code change (audit bug C3). `oytra/policy.py::apply_policy` is the single
implementation; `engine.Engine._decide` and `backtest.policy` both call it, so they cannot diverge.
Every row of the table below has a regression test in `tests/test_all.py` (`test_precedence_*`).

## Priority order (applied top to bottom; a later step only sees the result of the earlier ones)

| Step | Rule | What it does | Why |
|---|---|---|---|
| 1 | Risk band | `p < 0.40` SHIP · `< 0.60` CONFIRM · `< 0.875` NUDGE · else HOLD (`config/rules.csv`, unchanged) | Tuned policy choice (see THRESHOLD_MATHS.md) |
| 2 | First-time-labelled protection | band HOLD + `history_state = REPORTED_FIRST_TIME` + `protect_first_time_customers=yes` → NUDGE | Never auto-cancel a first-time-labelled buyer on the risk score alone |
| 3 | Unknown history is not evidence | band HOLD + `history_state = UNKNOWN_OR_INCONSISTENT` + `protect_unknown_history=yes` → NUDGE (prepaid offer, then ops review) | The score may lean on reported history we know is contradictory, so it is not strong enough to cancel. This is **not** treating the buyer as first-time: no first-time wording, not counted in the first-time/CAC metric |
| 4 | Hard data-quality rules | fake name → `fake_name_action`; unusable address → `unusable_address_action`; if either is `hold` the result is HOLD, otherwise CONFIRM. **Replaces the band action, including a band HOLD or NUDGE** | WhatsApp must collect a real name / full address before anything ships; the configured action is the operator's explicit choice |
| 5 | ₹0 order | NUDGE or HOLD → `zero_value_order_action` (confirm). SHIP / CONFIRM unchanged | Nothing to discount and nothing gained by cancelling |

`UNKNOWN_OR_INCONSISTENT` never moves an order *towards* HOLD at any step. History state only ever
softens a risk-band HOLD (steps 2–3).

## Conflict table

| # | Conflict | Example | Result | Deciding step |
|---|---|---|---|---|
| 1 | Fake name + first-time-labelled | "asdf", prior_orders 0, p 0.88 | CONFIRM (band HOLD → step 2 NUDGE → step 4 `fake_name_action=confirm`) | 4 |
| 1b | same, with `fake_name_action=hold` | | HOLD (configured data-quality hold is not a risk-score cancel, so first-time protection does not apply; ops can still call) | 4 |
| 2 | Unusable address + very high risk | **KT100327**: repeat buyer, p 0.943, address unusable, `unusable_address_action=confirm` | CONFIRM — WhatsApp asks for the full address; never shipped without it. (Old code: HOLD, contradicting rules.csv) | 4 |
| 3 | Unknown history + very high risk | p 0.93, history inconsistent, clean name/address | NUDGE (step 3), never HOLD on risk alone | 3 |
| 4 | Zero-value order + low risk | ₹0, p 0.10 | SHIP (step 5 only touches NUDGE/HOLD) | 1 |
| 4b | Zero-value + high risk | ₹0, p 0.95 | CONFIRM | 5 |
| 5 | Hard rule vs risk band (general) | any band + fake/unusable | hard rule action wins (CONFIRM or HOLD), then ₹0 override | 4 → 5 |

## What is shown per order
The engine shows the action chosen by this precedence. It also shows the expected ₹ of every action
from `economics.value()` (the **same** formula the backtest uses). If the best-₹ action differs from the
policy action, the reason says so: `policy band chose X; per-order ₹ estimate favours Y`.
