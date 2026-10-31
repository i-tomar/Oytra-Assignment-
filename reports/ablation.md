# Feature ablation (same Apr–Aug → Sep split)

One September month (86 RTOs): AUC differences under ~0.01 and Rs differences of a few hundred are within noise.

| Variant | AUC | ΔAUC | PR-AUC | Brier | Sep net ₹ | Δ₹ |
|---|---|---|---|---|---|---|
| full model (production) | 0.738 | +0.000 | 0.534 | 0.1643 | 1,387 | +0 |
| drop pin_logit | 0.693 | -0.045 | 0.512 | 0.1698 | 1,425 | +38 |
| drop first_time | 0.729 | -0.009 | 0.523 | 0.1658 | 1,348 | -39 |
| drop prior_rto | 0.725 | -0.013 | 0.513 | 0.1676 | 1,256 | -131 |
| drop prior_rto_rate | 0.737 | -0.001 | 0.533 | 0.1647 | 1,334 | -53 |
| drop meta_first_time | 0.727 | -0.011 | 0.528 | 0.1658 | 1,674 | +287 |
| drop single_item | 0.733 | -0.005 | 0.524 | 0.1664 | 1,522 | +135 |
| drop address_score | 0.691 | -0.047 | 0.484 | 0.1724 | 1,868 | +481 |
| drop name_fake | 0.737 | -0.001 | 0.522 | 0.1650 | 1,418 | +31 |
| drop phone_invalid | 0.741 | +0.003 | 0.543 | 0.1631 | 1,443 | +56 |
| drop value_k | 0.728 | -0.010 | 0.525 | 0.1664 | 1,831 | +444 |
| drop night | 0.737 | -0.001 | 0.535 | 0.1644 | 1,456 | +69 |
| group: customer history (reported) | 0.689 | -0.049 | 0.500 | 0.1716 | 1,452 | +65 |
| group: area (pincode/state RTO rate) | 0.693 | -0.045 | 0.512 | 0.1698 | 1,425 | +38 |
| group: address / name / phone quality | 0.683 | -0.055 | 0.451 | 0.1761 | 2,073 | +686 |
| group: order value + night-time | 0.727 | -0.011 | 0.525 | 0.1665 | 1,866 | +479 |
| group: basket (single item) | 0.733 | -0.005 | 0.524 | 0.1664 | 1,522 | +135 |
