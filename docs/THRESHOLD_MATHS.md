# Threshold maths (one page)

Every number on this page is recomputed by `scripts/check_threshold_maths.py` (run by `run_all.sh` and the tests), which fails if the doc quotes a number the code does not reproduce. Inputs: `config/economics.yaml` (brief) and `config/rules.csv` (assumptions). Labels: **[brief]** given in the assignment, **[M]** measured from the CSV, **[A]** assumption in `rules.csv`, **HYPOTHETICAL** = depends on [A].

**1. Cost of an RTO and value of a delivery.** L = ₹65 forward + ₹65 return + ₹25 packing + 8% × ₹180 damaged stock = **₹169.4** [brief]. A delivered order of value v earns V = 0.62v − ₹90 [brief]. At the brief's ₹649 that is **₹312.38**; at the labelled-data mean of **₹919.96** [M] it is **₹480.38**. **No CAC is added to V** (audit fix C1): Marketing's ₹300 CAC is money already spent to acquire the customer, not value created by delivering. The future value of a first-time customer is set to ₹0 in the base case (`assumed_future_contribution_first_time_rupees`); a +₹300 version is reported only as a labelled hypothetical sensitivity in `reports/backtest.json`.

**2. Per-order break-evens vs shipping everything** (one formula, `economics.value`; same for first-time and repeat now that CAC is out):

| Risk p at which… | at ₹649 | at ₹919.96 |
|---|---|---|
| CONFIRM beats SHIP | 23.7% | 32.1% |
| NUDGE beats SHIP | 26.1% | 29.2% |
| NUDGE beats CONFIRM | 31.9% | 23.3% |
| HOLD beats CONFIRM | 77.0% | 83.8% |
| HOLD beats SHIP (= V/(V+L)) | 64.8% | 73.9% |

All rows except the last rest on assumptions [A] c = 50% (confirmation catches RTOs), g = 8% (genuine buyers lost), take-up t = 25% if the order would have been delivered and 10% if it would have been RTO, prepaid RTO 4% [brief-provided assumption].

**3. Why the bands stay at 40 / 60 / 87.5%.** The break-evens above move with order value and with every assumption, so the bands are a policy choice, not an optimum. A diagnostic grid search on Apr–Aug cross-validated predictions (not applied) picks 0.3 / 0.3 / 0.825, i.e. confirm almost everything above 30% and no nudge band. Walk-forward table C (`reports/walkforward.md`) compares a per-order argmax policy with the bands under an Ops friction cap; it is not robustly better in the conservative case, so the bands are kept. The nudge band also exists to *measure* take-up, which today is an assumption. 87.5% sits above both HOLD break-evens. September was never used to choose any threshold.

**4. NUDGE terms per order** (`economics.breakdown`, one formula used everywhere):
- Messages: ₹1 + (1−t)·₹1. Discount + gateway fee: t(1−q)(₹50 + 2%·v), q = prepaid RTO rate.
- If it would have been an RTO: RTO cost avoided t(1−q)L + (1−t)cL, plus prepaid delivered contribution t(1−q)V.
- If it would have been delivered: genuine lost t·q(V+L) + (1−t)gV.
- **Confirm:** avoids cL on an RTO; loses gV on a genuine buyer; ₹1 message. **Hold:** avoids L on an RTO; loses V on a genuine buyer.
- Silence goes to manual ops review, not auto-cancel; the cost of an ops call is unknown and not included.

**5. The ₹649 brief AOV vs the CSV.** After removing the 30 exact duplicate rows the mean order value is **₹919.64** [M]; on the 1,987 labelled orders it is **₹919.96**, median **₹748** [M]. The file holds only COD orders and may be a different mix or period. All ₹ maths use each order's own value; ₹649 is used only in the worked examples. 65% of labelled orders are first-time by our history state [M].

**6. September (329 orders, 86 RTO; retrospective holdout), HYPOTHETICAL ₹ net vs shipping everything:**

| Scenario | c / g / t(delivered) / t(RTO) | Our rules | Ops rule (hold if risk ≥ 38%, pin ≥ 40%, or bad name/address) |
|---|---|---|---|
| Conservative | 35% / 12% / 15% / 0% | **−₹117** | **−₹16,595** |
| Base | 50% / 8% / 25% / 10% | **₹1,387** | **−₹16,595** |
| Optimistic | 65% / 5% / 35% / 20% | **₹2,728** | **−₹16,595** |

The Ops rule only holds orders, so c, g and t do not move it. These are *simulated* flagged RTOs, not prevented ones. Month-by-month (including negative months) is in `reports/walkforward.md`; any per-month scale-up is a HYPOTHETICAL projection.
