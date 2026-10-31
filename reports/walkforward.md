# Walk-forward Jun–Sep (no re-tuning after seeing a month)

All ₹ are HYPOTHETICAL (assumed WhatsApp/prepaid effects, rules.csv); AUC/Brier are model metrics on real outcomes. Negative months shown as-is.

## A. Fixed 40/60/87.5 policy — stability analysis

Thresholds and history-model choice were made on Apr–Aug, so **Jun–Aug are not independent tests**. Model refit on all orders before each month.

| Month | Train orders | Test orders (RTO) | AUC | Brier | Flagged (of which RTO) | Confirm+nudge share | ₹ conservative | ₹ base | ₹ optimistic |
|---|---|---|---|---|---|---|---|---|---|
| Jun | 637 | 324 (85) | 0.615 | 0.1945 | 62 (23) | 19% | -2,511 | -556 | 1,023 |
| Jul | 961 | 336 (101) | 0.722 | 0.1838 | 61 (34) | 18% | -576 | 1,200 | 2,727 |
| Aug | 1297 | 361 (101) | 0.735 | 0.1737 | 81 (46) | 22% | 265 | 2,642 | 4,795 |
| Sep | 1658 | 329 (86) | 0.738 | 0.1643 | 57 (30) | 17% | -117 | 1,387 | 2,728 |

## B. Genuine chronological model + policy evaluation

For each month, history model AND thresholds are chosen using only earlier months (inner out-of-time folds), then applied once.

| Month | Train orders | Inner validation | Model chosen | Thresholds chosen | AUC | Brier | Flagged | Confirm+nudge share | ₹ conservative | ₹ base | ₹ optimistic |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Jun | 637 | 2026-05 | reported_history | 0.275/0.275/0.850 | 0.615 | 0.1945 | 123 | 38% | -3,713 | 435 | 3,719 |
| Jul | 961 | 2026-05, 2026-06 | reported_history | 0.300/0.300/0.875 | 0.722 | 0.1838 | 105 | 31% | -1,073 | 3,463 | 7,328 |
| Aug | 1297 | 2026-05, 2026-06, 2026-07 | reported_history | 0.300/0.300/0.875 | 0.735 | 0.1737 | 132 | 37% | -1,405 | 3,012 | 6,750 |
| Sep | 1658 | 2026-05, 2026-06, 2026-07, 2026-08 | reported_history | 0.300/0.300/0.875 | 0.738 | 0.1643 | 107 | 32% | -816 | 2,904 | 6,085 |

## C. Argmax-EV (comparison only) vs bands — Ops friction cap 25% of orders

Argmax decides with base-case assumptions and is scored under each scenario; same model as table A.

| Month | Bands ₹ cons / base / opt | Argmax ₹ cons / base / opt | Bands friction | Argmax friction |
|---|---|---|---|---|
| Jun | -2,511 / -556 / 1,023 | -2,394 / 70 / 2,040 | 19% | 25% |
| Jul | -576 / 1,200 / 2,727 | -301 / 2,689 / 5,275 | 18% | 25% |
| Aug | 265 / 2,642 / 4,795 | -209 / 2,766 / 5,408 | 22% | 25% |
| Sep | -117 / 1,387 / 2,728 | 59 / 2,266 / 4,207 | 17% | 25% |

**Verdict:** argmax-EV >= bands in 11/12 month x scenario cells; Jun-Sep totals argmax vs bands: conservative -2,845 vs -2,939, base 7,791 vs 4,673, optimistic 16,930 vs 11,273; friction cap 25% respected. Pre-stated bar (better in every cell) not met: loses Aug conservative. Argmax is ahead on totals, but it decides with the same HYPOTHETICAL rates it is scored on and always runs at the friction cap, so its edge is assumption-driven. Bands kept; argmax stays a comparison and pilot candidate.
