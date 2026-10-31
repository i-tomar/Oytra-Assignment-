## What I would do about risky COD orders

**To:** Founder, OYTRA · **From:** Ishan Singh Tomar · **Date:** 31 October 2026 · **Subject:** COD risk decisions and expected financial impact

### Bottom line
I wouldn't automatically cancel risky COD orders. The data has patterns Operations can use, but a risky order isn't always a fake one. My plan is to ship low-risk orders, confirm the ones that need more information, offer a prepaid option to a smaller group, and keep cancellation as a last step with clear rules. In the September simulation this comes out at a base-case benefit of **₹1,387** compared with shipping every order as COD, with a range of **−₹117 to +₹2,728**. These figures are HYPOTHETICAL, because the data can't tell us how customers react to a WhatsApp message or a discount. June is negative under the fixed policy and the conservative case is negative in 3 of the 4 months, so I'd run a pilot before treating any of this as real money.

### What I found in the order data
- Address quality mattered more than language. The 183 orders with unusable addresses had 61.7% RTO, compared with 23.6% for the 1,413 orders with complete addresses. Hinglish landmark addresses sat at 31.0%, so I check whether an address is usable and don't penalise Hinglish.
- Fake-looking names were a warning sign, but not enough to cancel on. The 44 orders with names like "Test Order", "qwerty" or "asdf" had 63.6% RTO, compared with 27.6% for everyone else. This is below the illustrative 64.8% break-even for a ₹649 order, although the actual cancellation threshold depends on the individual order value.
- Pincode history is usually too thin to use on its own. There are 1,066 pincodes across 1,987 labelled orders; the median pincode has one order and only 30 have five or more. States do differ (Bihar 53.8%, Maharashtra 18.2%), so I pull small pincodes towards their state's rate rather than blocking areas.
- Basket size doesn't follow a simple pattern. Four-item orders had 36.4% RTO (107 orders) and two-item orders 25.0% (633). Adding product flags raised September AUC from 0.738 to 0.747, but the estimated net fell from ₹1,387 to ₹1,289 and the interval on the AUC change crossed zero, so products never decide whether an order ships.

Data: 2,018 raw rows. After removing 30 exact duplicates and one order still in transit, I had 1,987 labelled COD orders (Apr–Sep). The brief's AOV is ₹649, while the data's mean is ₹919.96 (median ₹748). I use each order's own value and keep ₹649 for examples based on the brief.

### The rules and what they would have done to September
The bands stay at **40% / 60% / 87.5%** predicted RTO risk (ship / confirm / prepaid nudge / hold). They are policy settings rather than universal break-evens, and I picked the 60% split by hand to leave room for a prepaid test. A fake name or unusable address always goes to WhatsApp confirmation so we can collect the right details, and buyers labelled first-time or with unknown history are never cancelled on score alone. The model uses the reported customer-history fields because that version won chronological validation inside April–August. Those fields aren't a verified identity, though.

| September action | Orders | Historical RTOs in group |
|---|---|---|
| Ship as-is | 272 | 56 |
| WhatsApp confirmation | 55 | 28 |
| Prepaid nudge | 2 | 2 |
| Hold / cancel | 0 | 0 |

57 orders were flagged and 30 of them were RTOs, out of 86 RTOs in total (precision 53%, recall 35%). Those 57 held ₹5,082 of the ₹14,568 September RTO cost. These are flagged orders; the data can't show how many RTOs would really have been avoided. Model quality: ROC-AUC 0.738, PR-AUC 0.534, Brier 0.1643 (0.1931 if you always predict the average). One caveat: on September alone, the no-history model would have scored HYPOTHETICAL ₹1,452 at a lower AUC (0.689). I didn't switch after seeing September.

### The money, and Operations vs Marketing
Using the brief's numbers, one RTO costs **₹169.40** (₹65 + ₹65 + ₹25 + an expected ₹14.40 for damage). A delivered order contributes 62% of its value minus ₹90, which is ₹312.38 at ₹649 and ₹480.38 at ₹919.96. That means **cancelling only beats shipping above 64.8% risk** (73.9% for a ₹920 order). The ₹300 CAC has already been spent, so I don't count it as profit on the current order, and I don't count any hypothetical future customer value either.

| Scenario (HYPOTHETICAL) | Jun | Jul | Aug | Sep |
|---|---|---|---|---|
| Conservative | −₹2,511 | −₹576 | +₹265 | −₹117 |
| Base | −₹556 | +₹1,200 | +₹2,642 | +₹1,387 |
| Optimistic | +₹1,023 | +₹2,727 | +₹4,795 | +₹2,728 |

In the base case, confirmation stops 50% of would-be RTOs and loses 8% of genuine buyers. Prepaid take-up is 25% for orders that would have been delivered and 10% for would-be RTOs. None of these rates is measured. The 4% prepaid RTO rate comes from the brief. I chose the thresholds on April–August data, so June to August are stability checks and not independent tests. A stricter chronological test, which re-selects the model and thresholds using only earlier months, gives base-case estimates of +₹435 in June, +₹3,463 in July, +₹3,012 in August and +₹2,904 in September. However, this approach sends 31–38% of orders through confirmation or a prepaid nudge, exceeding the assumed 25% Operations capacity. These results are therefore diagnostic estimates, not an immediately deployable policy.

**Operations' view.** I simulated it as holding any order at ≥38% risk, pincode RTO ≥40%, or with a fake name or unusable address. That's my reading; Ops didn't give me a threshold. It holds 96 September orders, 47 RTOs and 49 delivered, for <b style="white-space:nowrap">−₹16,595</b>. It also turns away 58 first-time-labelled buyers. For Marketing that's an illustrative ₹17,400 acquisition-spend proxy (58 × ₹300). The money is already spent, so it isn't a measured extra loss and it isn't in the net. **Marketing's view** is to ship everything. That's the ₹0 baseline, and it keeps all ₹14,568 of RTO cost. My rules sit between the two: no first-time acquisition spend turned away (₹0) and no cancellation on score alone.

### What could go wrong, and how we'd notice
- The behaviour assumptions could be wrong. In the pilot I'd log confirmation replies, no-replies, prepaid take-up and cancellations by risk band, then put the measured rates into `config/rules.csv` in place of my guesses.
- The model could drift. The dashboard already shows the daily ₹ trend and a predicted-vs-actual calibration chart. I'd add a weekly predicted-vs-actual RTO check with an alert, and retrain monthly.
- WhatsApp could fail or annoy customers. In the mock, no reply after a reminder goes to a manual Ops call and is never auto-cancelled. "Keep COD" replies are honoured, duplicate payment webhooks are ignored, and a payment that arrives after a COD fallback is flagged for refund review. The thing to watch is the Ops queue against the 25% capacity.
- The data has gaps. Phone isn't a reliable customer ID and the reported history is inconsistent (268 rows are unknown or inconsistent). A new order sent without history fields now goes to unknown history instead of first-time; I fixed that default and added a regression test. The pincode encoder still uses earlier outcomes with no maturity lag. A retrain with a 14-day lag gave the same September AUC, but a proper lag is needed before production.
- The LLM could misread text. It's optional and off by default. On 60 synthetic cases it agreed with my draft labels less often than the rules did (23 vs 25 of 30), and I still need to review those labels myself.

### Next two weeks
1. Connect **Shopify customer IDs** and courier final statuses so customer history comes from real records.
2. Run a 2–4 week **pilot** of confirmation and ₹30 / ₹50 / ₹75 prepaid offers to measure the two take-up rates, with any cancellation reviewed by a person.
3. Ask for house number and landmark at checkout, since unusable addresses came back 61.7% of the time.

