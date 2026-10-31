# WhatsApp flow (Part 2)

Mock: `python -m oytra.whatsapp` (interactive, `/wait 12` jumps the clock) or `python -m oytra.whatsapp --demo` (every branch). Code: `oytra/whatsapp.py`.

## Language
We ask once, then remember. The first message adds "Reply HINDI" (or "Reply ENGLISH"). The choice is stored per phone in `state/language_prefs.json`. A reply that doesn't change the language stores the first guess as accepted. The next order uses the stored language and doesn't ask again. The first guess:
Hindi-in-Latin script (Hinglish) if the state is in the Hindi belt (UP, Bihar, MP, Rajasthan, Delhi, …) or the address itself is Hinglish. Otherwise English. Hinglish is used instead of Devanagari because the customers' own addresses are typed in Latin script. All templates live in `T` in `whatsapp.py`. In production they'd be WhatsApp-approved utility templates.

## Timeline
| When | Ship after confirmation | Nudge to prepaid | Bad address / fake name |
|---|---|---|---|
| t+0 (within 5 min of order) | Order summary + "reply YES / NO" | "Pay online, get ₹50 off" + link, "1 = pay online, 2 = keep COD" | "Please send full name + house no., street, landmark" |
| t+12h, no reply | Reminder ("reply YES to ship, NO to cancel") | Reminder ("discount expires in 12h") | Reminder |
| t+24h, no reply | **MANUAL_OPS_REVIEW** (`no_reply_action_confirm`): ops calls, then ship or cancel | **Switch to COD confirmation** (`no_reply_action_nudge`), with another 24h | **MANUAL_OPS_REVIEW** (`no_reply_action_address`): ops calls for the address; never shipped blind |

No order is auto-cancelled on silence by default. `no_reply_action_confirm` accepts `manual_review` (default), `cancel` or `ship`; `no_reply_action_address` accepts `manual_review` or `cancel`; `load_rules` rejects other values. Ops records the call result with `ops_review("ship" | "cancel")`.

## Replies
Intent comes from keywords (English, Hindi, Hinglish: haan/ha/ok/ji, nahi/nhi/cancel, upi/online/pay, kab/delivery). If an `OPENAI_API_KEY` is set, an LLM is tried first, and keywords are the fallback.
- **yes** → confirmed, ship today.
- **no** → cancel politely and invite a reorder. ("haan nahi chahiye" counts as **no**: a "no" word wins over a "yes" word.)
- **pay_online / "1"** → payment link, state `PAYMENT_PENDING`. The state becomes `PAID` **only when the payment gateway confirms** (`payment_result`), never because the customer says "paid". If a payment fails, a retry link is sent. A second failure, or no verified payment within `payment_timeout_hours` (2h), switches the order to the COD confirmation flow. "2", or a keep-COD reply ("keep COD", "cod rakho", "cash on delivery hi"), → keep COD, which counts as confirmed and releases the order exactly once (`order_released`; a second request logs `release_duplicate_ignored`). The rule classifier checks keep-COD phrases before the no/pay keywords, unless the reply also says "cancel".
  - **Late payment after the COD fallback.** If a verified `paid` webhook arrives after the order already fell back to COD (a payment link had been sent), the order is **not** released again. It gets an `ops_flags` entry `late_payment_after_cod_fallback` and a `late_payment_refund_review` event, so ops can refund the online payment or cancel the COD collection.
  - **Idempotent webhooks.** Gateways retry webhooks, so `payment_result(ok, event_id)` remembers every event id it has processed. A repeated id is logged as `payment_duplicate_ignored` and does nothing. A `paid` event that arrives when the order is not `PAYMENT_PENDING` (for example, already `PAID`) is also ignored. The order is released to the warehouse (`order_released` event) exactly once; `tests/test_all.py::test_duplicate_paid_webhook_releases_once` checks this.
- **question** (e.g. "kab aayega?") → answer, then re-ask.
- **random / unclear** → one clarification. A second unclear reply goes to a human agent (we don't cancel someone who is trying to talk to us).
- **no reply** → see timeline. After the reminder and 24h of silence, the order goes to `MANUAL_OPS_REVIEW`: someone from ops calls once, then ships or cancels. We don't auto-cancel because silence on WhatsApp is not the same as a refusal; a call costs ops time, but a wrongly cancelled genuine buyer costs about ₹312 of contribution (₹649 order; Marketing CAC is sunk spend and not counted) (see `docs/THRESHOLD_MATHS.md`). The ₹ backtest is unchanged: `confirm_catches_rto_share` (50%) and `confirm_genuine_loss_share` (8%) already describe the *final* result of the confirmation step, whoever closes it. The cost of an ops call is not known, so it is not in the ₹ figures; the workload is reported instead (number of orders sent to confirmation).

## Why ₹50 for prepaid (maths)
- RTO cost L = 65 + 65 + 25 + 0.08×180 = **₹169.4**. Prepaid RTO is 4%.
- Nudge band starts at 60% risk. Switching one such order to prepaid saves at least (0.60 − 0.04) × ₹169.4 = **₹95** in RTO costs alone. It also adds the margin from the extra delivered order (0.62×649 − 90 = ₹312 × 0.56 ≈ ₹175 more expected margin). In the backtest the prepaid take-up is split into two HYPOTHETICAL rates: buyers who would have been delivered anyway (25% base) and would-be RTOs (10% base); `value()` and `breakdown()` use the same formula (tested).
- `oytra/economics.py:max_discount` gives the break-even discount where prepaid still beats plain COD confirmation: **₹226** (repeat buyer, ₹649, 60% risk), rising with risk.
- So ₹50 sits well inside break-even. It stays profitable even counting only shipping savings (₹95 − ₹50 − 2% gateway fee ≈ ₹32 buffer). It is ~7.7% of AOV, enough to be noticed but not worth gaming. The money-maximising number is not knowable without testing take-up, so the plan is to A/B **₹30 / ₹50 / ₹75** and put the winner in `rules.csv`.

## Event log
Every message, reply, payment callback and state change is appended to `reports/whatsapp_events.jsonl` and `.csv`. Each row has:
- `ts` (IST)
- `order_id`
- `actor`
- `event`
- `text`
- `flow`
- `state`
- `payment_status`
- `lang`
- `action`
- `risk`
- `model_version` (`model-<hash of engine.pkl>/rules-<hash of rules>`)

This means any message can be traced back to the score and rules that triggered it.
