# History model selection (chronological validation inside Apr–Aug)

ROC-AUC / Brier / ECE are model metrics; ₹ is base-case HYPOTHETICAL at fixed 40/60/87.5 thresholds.

| Model | Jun AUC | Jul AUC | Aug AUC | mean AUC | mean PR-AUC | mean Brier | mean ECE | mean ₹/month (hyp.) |
|---|---|---|---|---|---|---|---|---|
| no_history | 0.597 | 0.671 | 0.710 | 0.659 | 0.436 | 0.1895 | 0.046 | 529 |
| reported_history | 0.615 | 0.722 | 0.735 | 0.691 | 0.469 | 0.1840 | 0.056 | 1,095 |
| history_quality_flag | 0.614 | 0.715 | 0.723 | 0.684 | 0.460 | 0.1854 | 0.052 | 916 |

Training sizes per fold: train <2026-06-01 -> test 2026-06: 637 train / 324 test, train <2026-07-01 -> test 2026-07: 961 train / 336 test, train <2026-08-01 -> test 2026-08: 1297 train / 361 test

Decision trail:

- reported_history vs no_history: mean AUC +0.031, wins 3/3 folds, mean Brier -0.0055 -> switch to reported_history
- history_quality_flag vs reported_history: mean AUC -0.007, wins 0/3 folds, mean Brier +0.0014 -> within noise / not better, keep reported_history

**Selected: `reported_history`**

## September — retrospective temporal holdout (used during development), not an untouched test set

| Model | AUC | PR-AUC | Brier | ECE | ₹ base (hyp.) |
|---|---|---|---|---|---|
| no_history | 0.689 | 0.500 | 0.1716 | 0.044 | 1,452 |
| reported_history (selected) | 0.738 | 0.534 | 0.1643 | 0.042 | 1,387 |
| history_quality_flag | 0.726 | 0.524 | 0.1663 | 0.038 | 1,500 |

Future work: Shopify customer ID instead of phone as the customer key.
