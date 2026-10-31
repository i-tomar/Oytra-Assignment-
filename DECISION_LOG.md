# Decision Log — OYTRA COD Risk Engine

This is the record of the main choices I made while working on the assignment. I have kept the reasons and the alternatives I considered. Some early experiments were changed after checking the data or running the backtest; where that happened, I have noted the final choice.

## Data and model

1. **I focused on rupees, not accuracy alone.** I still report model metrics, but the main question is whether an action is likely to improve the business result. An RTO has a direct estimated cost of ₹169.40. A delivered order contributes a different amount depending on its value, so treating every wrong prediction equally would not make sense.

2. **I cleaned the CSV before analysing it.** There are 2,018 raw rows. I removed 30 exact duplicate rows, normalised the status labels and excluded one order that was still in transit. That leaves 1,987 labelled COD orders from April to September 2026. I kept the three ₹0 orders and flagged them rather than deleting them.

3. **I kept the assignment AOV and the dataset AOV separate.** The brief says ₹649. The mean in the labelled CSV is ₹919.96 and the median is ₹748. I use each order's own value in the model and financial calculations. I use ₹649 only when showing the brief's example economics. I do not assume the CSV and the brief describe the exact same order mix.

4. **I used a time-based split instead of a random train/test split.** The main September evaluation trains on April–August and tests on September. A random split would make the exercise less like predicting future orders. September has already been examined during development, so I describe it as a retrospective temporal holdout, not a completely untouched final test.

5. **I used a small logistic-regression model.** I considered more complex models, but the training data is small. Logistic regression is easier to inspect, fast to run and gives a probability that can be checked against actual outcomes. I did not use an LLM to calculate the RTO score.

6. **I smoothed pincode rates instead of using raw percentages.** Most pincodes have very little history: there are 1,066 pincodes for 1,987 orders, the median is one order, and only 30 pincodes have at least five orders. A raw rate from one or two orders would be too noisy. I smooth pincode information towards the state rate and the state rate towards the overall rate.

7. **I use chronological pincode features for the model.** Training rows are encoded using earlier time blocks, rather than random out-of-fold values. This is more consistent with how the system would work when a new order arrives. One honest gap: the pincode encoder applies no outcome-maturity lag. It uses an earlier order's RTO/delivered outcome as soon as that order is placed, although in reality the courier result arrives days later (`oytra/features.py`, note in `chrono_pin_logit`). A 14-day lag is used only in two checks: the customer-history audit, and one leakage-audit run that retrains only on labels known by 1 September (1,491 of 1,658 training rows), which gave the same September AUC of 0.738. The CSV has no courier finalisation timestamps, so adding a proper lag to the encoder is needed before production retraining.

8. **I compared three customer-history versions before keeping the reported-history model.** I compared the reported fields, a model without customer history, and a model with history-quality flags on chronological folds inside April–August. The reported-history version had the best average AUC across those three folds (0.691, compared with 0.659 without history and 0.684 with quality flags). I kept it for the prototype, but I do not treat the reported fields as a verified customer identity. One caveat I owe: on September alone, the no-history model scored a HYPOTHETICAL ₹1,452 against ₹1,387, with a lower AUC (0.689 vs 0.738). I did not switch, because choosing after seeing September would be selecting on the holdout.

9. **I kept a separate unknown/inconsistent history state.** The file has 1,292 reported first-time rows, 427 reported returning rows and 268 unknown/inconsistent rows. The reported counts do not always match the earlier orders visible for the same phone. A phone number is only a rough key in this dataset. For a real Shopify integration, I would use Shopify's customer ID and order history. The new-order adapter has a known bug here; see entry 38.

10. **I did not penalise Hinglish addresses.** A Hinglish landmark address is not automatically a bad address. The data suggests completeness matters more than language: unusable addresses have a much higher RTO rate, while Hinglish landmark addresses are much closer to the overall rate (31.0% against 28.4% overall). The address check should look for useful delivery details, not the language used.

11. **I kept product analysis, but did not make product category a production risk rule.** Basket size is not a straight line: four-item orders have a 36.4% RTO rate (107 orders), while two-item orders have 25.0% (633 orders). Product groups overlap because one order can contain more than one product. Adding product flags raised AUC from 0.738 to 0.747, but estimated net fell from ₹1,387 to ₹1,289 and the AUC confidence interval crossed zero. I therefore report product patterns as findings and do not cancel or hold an order because of its product.

## Decision policy and money

12. **I kept four possible actions.** The system can ship as-is, ask for WhatsApp confirmation, offer a prepaid discount, or hold/cancel. A risky order is not automatically a fake order, so the system needs options between shipping everything and cancelling it.

13. **I kept the 40% / 60% / 87.5% bands for the current prototype.** The thresholds are editable in `config/rules.csv`. The original rupee-based optimiser on April–August picked 40% / 87.5% / 87.5%, which means no nudge band at all. The 60% split was my manual choice, so that prepaid take-up can actually be measured. After the audit fixes, a diagnostic time-ordered search on April–August picks 30% / 30% / 82.5%; I report it but did not apply it. They are policy settings, not universal break-even points. I did not change them just to make a later month look better.

14. **I made address/name checks a reason to confirm, not an automatic cancellation.** The early version cancelled fake-name and unusable-address orders. That version produced a negative September estimate and cancelled orders that were ultimately delivered. I changed these cases to confirmation/address collection. Operations can choose a stricter setting, but the action must be explicit in the rules.

15. **I wrote the rule precedence down before changing the code.** The full table is in `docs/RULE_PRECEDENCE.md`, and the engine and the backtest call the same function, so they cannot disagree. In short: the risk band comes first; then first-time and unknown-history protection can soften a risk-band hold; then the fake-name/unusable-address rule replaces the band action (including a hold or nudge); then the ₹0 rule. Examples: a fake name on a first-time-labelled order ends in confirmation; an unusable address at very high risk (order KT100327, 94.3%) ends in confirmation to collect the address, not a hold; unknown history at very high risk ends in a prepaid nudge, never a hold. Every row of the conflict table has a regression test.

16. **First-time and unknown-history buyers are never cancelled on the risk score alone.** With `protect_first_time_customers` and `protect_unknown_history` set to yes, the worst outcome on score alone is a prepaid nudge. Unknown or inconsistent history is never itself evidence for cancelling, and it is not treated as first-time either: no first-time wording and no CAC metric for those orders.

17. **₹0 orders are confirmed, not nudged or cancelled.** There is nothing to discount and nothing gained by cancelling. All 3 ₹0 orders are from April–June and were delivered, so September is not affected.

18. **I do not use the ₹300 CAC as profit.** The company has already spent that money to acquire the customer. It is a Marketing metric, not extra contribution earned by delivering an order. I keep the base future-customer contribution at ₹0 until there is repeat-purchase data. Any future-value scenario would need its own evidence and must stay separate from CAC.

19. **I use a single financial formula for all four actions.** The per-order expected rupee values and the backtest breakdown must come from the same calculation. For the prepaid offer, I use separate hypothetical take-up rates for customers who would otherwise have been delivered and those who would otherwise have become RTOs. These are counterfactual groups, not customer types that can be directly observed before shipment.

20. **I kept the prepaid discount at ₹50 for the prototype.** At the 60% lower edge of the nudge band, moving to the assignment's 4% prepaid RTO assumption represents about ₹95 of RTO-cost difference before considering the chance of conversion and the other costs. The ₹50 offer is a test value, not a proven optimum. I would A/B test ₹30, ₹50 and ₹75.

21. **I made the intervention rates explicit assumptions.** The base case assumes confirmation catches 50% of would-be RTOs and loses 8% of genuine buyers. It assumes prepaid take-up of 25% for orders that would have been delivered and 10% for orders that would have been RTOs. Conservative and optimistic values are in `config/rules.csv`. None of these intervention rates has been measured in a live pilot.

22. **I send unanswered confirmation/address requests to manual Operations review.** No reply is not proof of fraud. A customer may miss the message. The system sends a reminder and then asks Operations to call. The cost of that call is not included because I do not have a measured cost for it.

23. **I keep the ₹-based argmax policy as a comparison, not the production policy.** It performed better in 11 of 12 month/scenario comparisons, but it lost the August conservative case and its result depends on the same assumed intervention rates used to score it. It also tends to use the full 25% Operations capacity. I kept the simpler threshold bands until a pilot measures the assumptions.

## Checks on the model

24. **Target leakage checks.** No September target leakage or self-target leakage was found in the checks performed. However, the PIN-code encoder still lacks a 14-day outcome-maturity lag, so some earlier delivery outcomes may not have been available at the actual prediction time. The September pincode encoder is fitted only on orders before 1 September, and flipping every September label leaves September scores unchanged. Flipping 20 training labels moves neither those rows' own pincode feature nor any earlier row's. The 14-day label-lag retraining gives the same September AUC (0.738). Details: `reports/leakage_audit.json`.

25. **Feature ablation.** Removing any single feature group lowers September AUC. The biggest drops are address/name/phone quality (0.738 → 0.683) and reported customer history (0.689). The only single feature whose removal raises AUC is `phone_invalid` (0.741). I did not remove anything on one month of evidence; `phone_invalid` is the first candidate to drop. Details: `reports/ablation.md`.

26. **Why the history fields are inconsistent.** Every timestamp parses in one format, so it is not a parsing problem. The order IDs are not in time order (rank correlation with time 0.024), and the reported counts look like they were accumulated in order-ID order: 204 phones show a decreasing prior-order count when sorted by time, against 57 when sorted by order ID. Shared phones are not the explanation either: of the 364 phones with two or more orders, only 6 carry more than one name. Details: `reports/history_rootcause.json`.

## Product, AI and application choices

27. **I use the LLM only for text that is difficult to judge with simple rules.** It can help interpret names, address completeness and WhatsApp intent. It does not set the RTO probability, financial assumptions or action thresholds. The rule-based judge is the default, so the application can run without an API key and the backtests stay repeatable.

28. **I kept the LLM optional after the 60-case test.** The test used synthetic examples and draft labels that still need my human review. The LLM's agreement with those draft labels was lower than the rule-based check on the reported name/address and intent tasks. Since the labels are not ground truth, I do not describe this as an accuracy benchmark. The LLM does not affect the backtest or the final decisions.

29. **I kept the dashboard as a generated static HTML file.** A founder can open it without starting a server or installing a frontend framework. Python calculates the values and writes the HTML. The current dashboard is a snapshot of the supplied data, not a live Shopify dashboard.

30. **I used CSV settings and kept the application small.** Operations can edit `config/rules.csv` in a spreadsheet. I did not add Streamlit, FastAPI, SQLite or a larger service architecture because the assignment only needs a working local prototype and a mock WhatsApp flow.

31. **I kept an event log for the WhatsApp simulation.** The log records messages and state changes with timestamps and model/rule versions. Payment status changes only after a verified payment result in the mock. Payment webhooks are idempotent: a repeated payment-event id is logged and ignored, and an order is released only once. A verified payment that arrives after the order has already fallen back to COD is not released again; it is flagged for a refund/Operations review. A "keep COD" reply is treated as a confirmed COD order.

32. **I report measured results separately from estimated results.** September's 57 flagged orders and the 30 RTO outcomes among them are historical observations. They were flagged by the policy; they were not proven to have been prevented. The rupee impact depends on the WhatsApp and prepaid assumptions, so I label it HYPOTHETICAL.

33. **I show month-by-month results, including losses.** With the fixed policy, the base estimates are June −₹556, July +₹1,200, August +₹2,642 and September +₹1,387. June is negative. Under the conservative assumptions, three of the four months are negative (June −₹2,511, July −₹576, August +₹265, September −₹117). The fixed thresholds were selected using April–August data, so June–August are stability checks, not independent tests. The separate chronological policy table reselects thresholds using earlier months only, but its intervention share is 31%–38%, above the assumed 25% Operations limit; I treat it as a diagnostic, not an immediately deployable policy. Its base results are June +₹435, July +₹3,463, August +₹3,012 and September +₹2,904.

34. **I did not treat the September result as proof that the system saves money.** The current September base estimate is +₹1,387, with a conservative estimate of −₹117 and an optimistic estimate of +₹2,728. These figures depend on unmeasured behaviour. The fixed-policy walk-forward is negative in June; the separately reselected chronological policy table exceeds the 25% Operations capacity in all four months and is only a diagnostic. A 2–4 week pilot is needed before calling any of this actual savings.

## What I would do next

35. **Connect Shopify customer IDs and courier outcomes.** This would make customer history more reliable and give the model better information about whether an order was delivered or returned.

36. **Run a small live pilot before automatic actions.** I would start with confirmation and prepaid offers, measure reply and conversion rates by risk band, and keep cancellation under manual review until the economics are supported by actual results.

37. **Review the LLM labels manually.** The 60 synthetic cases are still waiting for my labels. Until I review them, the LLM comparison stays preliminary and the LLM remains optional.

38. **Known bug, disclosed and not yet fixed: missing history becomes first-time for new orders.** `Engine.decide()` (`oytra/engine.py`, around line 70) fills a missing `customer_prior_orders` / `customer_prior_rto` with 0. A new order sent without history fields is therefore labelled REPORTED_FIRST_TIME instead of UNKNOWN_OR_INCONSISTENT, which breaks my own rule that missing history never means first-time. It does not change the backtests or September numbers, because every CSV row has the history fields. It does affect single new orders scored through the engine. The fix is to keep missing fields as missing and map them to UNKNOWN_OR_INCONSISTENT, with a regression test, before any live integration. Update: this has since been fixed. Missing, None and NaN history now map to UNKNOWN_OR_INCONSISTENT, covered by `tests/test_missing_history.py`.
