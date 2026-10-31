# AI Usage Log — OYTRA COD Risk Engine

I used AI tools during this assignment for research, coding support, testing, and reviewing the decisions. I did not rely on an AI response just because it sounded convincing. When a number or code change mattered, I checked it against the CSV, the backtest, a test, or the output of the application.

## Tools I used

| Tool | How I used it |
|---|---|
| **Grok Bot (AI assistant app)** | Helped inspect the assignment and CSV, write and revise the Python modules, train/evaluate the model, build the HTML dashboard, create the WhatsApp simulator, run tests, and prepare the documentation. I reviewed the results and asked for changes when the numbers or behaviour did not match the intended policy. |
| **ChatGPT** | Helped me understand the assignment and its financial calculations, question the approach, review the dataset findings and code-level claims, and prepare the audit and implementation instructions I gave to the coding agent. I used it as a second opinion, not as the source of truth. |
| **Groq API (`openai/gpt-oss-20b`)** | Used only for the optional name/address and WhatsApp-intent assessment in the prototype. It does not calculate RTO risk or choose the action. The backtests use the rule-based judge so the results stay repeatable. |

The Groq key is read from an environment variable and is not included in the repository or ZIP. The LLM is optional and can be disabled.

## Examples where AI output or implementation was weak

### 1. Cancelling orders with fake names or unusable addresses

An early version treated a fake-looking name or an unusable address as a reason to hold/cancel the order. The September backtest showed that this could cancel genuine orders and made the estimated result negative (about −₹5,334 in that early version, with 13 delivered orders cancelled).

I checked the result against the historical outcomes and changed the policy so these cases ask for confirmation or corrected address details instead of being cancelled automatically. A stricter hold setting remains configurable for Operations.

The same mistake came back once. A later "tidy-up" re-introduced hold for flagged orders in the high-risk band, and the September backtest flipped to about −₹2,084. I reverted it. (Both figures are from the development record in the repository's logs; no report file stores those discarded runs.)

### 2. Customer-history fields looked more reliable than they were

The first model treated `customer_prior_orders` and `customer_prior_rto` as normal historical features. When I compared them with earlier orders for the same phone number, I found rows where the reported previous-order count went down over time and rows marked first-time even though an earlier order was visible in the file.

I asked for a separate history analysis and model comparison. The final report keeps the reported-history model because it performed better in chronological validation inside April–August, but the fields are described as reported signals, not verified customer identity. I also noted that the current new-order adapter defaulted omitted history counts to zero; this was fixed so missing history maps to unknown, with a regression test (`tests/test_missing_history.py`). The next real integration should use Shopify's customer ID and order history.

### 3. The order explanations said the wrong thing for safe orders

A dashboard row for a returning customer read "Ship as-is: low risk (8%); first order from this customer". The explanation generator was using risk-raising wording for features that were actually lowering the risk. I caught it by reading individual dashboard rows rather than only the totals. The fix added separate wording for risk-lowering reasons, such as "returning customer (2 past orders)". A later version also gave a ₹0 order with a bad address two contradictory reasons; that was fixed and a test was added.

### 4. The two prepaid-nudge financial calculations did not match

During the technical audit, I found that the per-order `value()` calculation and the backtest `breakdown()` calculation treated a prepaid conversion differently. This meant that the rupee value shown next to an order could disagree with the financial calculation used in the backtest.

I asked for one shared formula and regression tests so the dashboard, per-order explanation and backtest use the same assumptions. The prepaid take-up assumptions are now split between orders that would otherwise have been delivered and orders that would otherwise have become RTOs. Both rates are hypothetical until measured in a pilot.

### 5. CAC was being treated like extra profit

An earlier version added the ₹300 customer acquisition cost to the value of delivering a first-time customer's order. I checked the accounting logic and removed it from the base contribution calculation. CAC is money already spent to acquire the customer; it is not extra profit created by delivering the current order. It is shown separately as a Marketing metric.

### 6. A WhatsApp reply was interpreted incorrectly

In an earlier mock flow, replying `1` to a prepaid nudge could be interpreted as a general confirmation instead of choosing the pay-online path. I checked the demo transcript and the state transition, then asked for reply handling to depend on the current flow. The test now checks that the prepaid choice moves to `PAYMENT_PENDING`.

### 7. A missing-pincode check was wrong

The first data-cleaning report showed zero missing pincodes. I compared it with the raw CSV and found 12 missing values. The conversion to strings had made the missing-value check unreliable. The cleaning step was changed to handle missing values explicitly.

### 8. Product features improved one metric but did not improve the decision result

Adding product flags increased the September ROC-AUC from 0.738 to 0.747, but the estimated (HYPOTHETICAL) net fell from ₹1,387 to ₹1,289, and the confidence interval for the AUC change (−0.005 to +0.021) crosses zero. The difference is small and comes from one month, so I did not add product categories to the production model. I kept product analysis in the findings and decided not to cancel orders based on the product they contain.

### 9. The ChatGPT approach document needed checking too

I gave the coding agent an approach document I had produced with ChatGPT and asked it to challenge every claim before changing anything. Its data figures checked out against the CSV, and some of its points were right: the history fields had never been checked, the payment state changed without verification, and there was no event log or ₹0 rule. Other parts were wrong for this task: placeholder thresholds of 15% / 35% / 60% would have sent about 74% of September orders through friction, its "₹402 per order" figure left out shipping and packing, and it pushed YAML, Streamlit and SQLite. I kept the CSV settings and the static HTML dashboard. The lesson for me: an AI-written brief is a good checklist and a bad source of numbers.

### 10. The LLM evaluation labels are not ground truth yet

The 60-case LLM test uses synthetic examples, so no customer data was sent to Groq. The draft expected labels and the rule-based classifier were written by the same AI assistant, so their agreement is circular: it is not an independent accuracy measurement. The LLM agreed with the draft name/address labels on 23 of 30 cases; the rules agreed on 25 of 30. For intent, the LLM agreed on 29 of 30 and the rules on 30 of 30.

The run itself also needed care. All 60 answers came back as valid JSON (prompt version `judge-v2`), with a median latency of 491 ms and a total cost of $0.0049 for the run. But 44 calls failed with a network error on the first attempt and only succeeded after retries. An earlier run without retries made the LLM look worse than it was, so retries were added and first-attempt errors are now reported (`reports/llm_eval.md`).

I have not treated these figures as a final accuracy score. The `human_label` column in `reports/llm_eval_labels.csv` still needs my review. Until that is done, the LLM comparison is preliminary and the LLM stays optional.

## How I checked the work

- I compared calculations with the figures in the assignment and the actual CSV.
- I checked order-level decisions and their explanations, not only the totals.
- I used backtests to compare alternative policies and kept negative months in the reports.
- I asked for regression tests when a bug was found.
- I checked that the memo, reports, and dashboard use the same financial numbers.
- I kept the deterministic backtests on the rule-based judge so repeated runs do not depend on variable LLM responses.

## Current limitations

- The intervention rates for WhatsApp confirmation and prepaid conversion are assumptions, not measured customer behaviour. The rupee impact is therefore hypothetical.
- September has already been used during development. It is a retrospective temporal holdout, not an untouched final test set.
- The dataset has about 2,000 COD orders across six months and no Shopify customer ID. Reported customer-history fields are inconsistent.
- The 60 synthetic LLM labels still need human review. The LLM's agreement with the draft labels should not be presented as proven accuracy.
- A real pilot is needed to measure confirmation response, customer drop-off, prepaid conversion and actual avoided RTOs.
