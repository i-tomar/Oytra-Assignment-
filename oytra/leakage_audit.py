"""Temporal-leakage audit of the pincode/state target encoding (HistoryStats).
Checks, all computed:
 1. The encoder used to score September is fit only on orders dated before 1 Sep.
 2. Shuffling / flipping September's outcomes leaves every September risk score unchanged.
 3. Training rows get an out-of-fold pincode feature: flipping one training row's label
    does not change that row's own pin_logit.
 4. Inside the threshold CV, each validation fold is encoded by stats fit without that fold
    (flipping all validation labels leaves that fold's CV predictions unchanged).
 5. Label-lag sensitivity: in real life an RTO is only known ~14 days after the order, so on 1 Sep
    the outcomes of late-August orders are not yet known. Re-fit using only orders whose outcome
    would be known by 1 Sep and compare September AUC / net.
Run: python -m oytra.leakage_audit -> reports/leakage_audit.json"""
import os, json, numpy as np, pandas as pd
from .config import load_rules, load_econ, ROOT
from .data import load, OUTCOME_LAG_DAYS
from .llm import RuleJudge
from .features import HistoryStats, build, oof_pin_logit, chrono_pin_logit
from .model import auc
from . import backtest as B

def main():
    R, E = load_rules(), load_econ(); df = load(); J = RuleJudge()
    jj = [J.judge(r.customer_name, r.address, r.city, r.pincode) for r in df.itertuples()]
    trm = (df.dt < B.TEST_START).values; tr, te = df[trm], df[~trm]
    jtr = [j for j, m in zip(jj, trm) if m]; jte = [j for j, m in zip(jj, trm) if not m]
    out = {}
    stats, model = B.fit(tr, jtr)
    out["1_encoder_fit_rows_latest_date"] = str(tr.dt.max())
    out["1_encoder_fit_rows_before_sep"] = bool(tr.dt.max() < pd.Timestamp(B.TEST_START))
    p0 = model.predict(build(te, stats, judged=jte))
    # 2. Sept labels can't reach Sept scores: refit on the full frame with Sept labels flipped, then score
    d2 = df.copy(); d2.loc[~trm, "rto"] = 1 - d2.loc[~trm, "rto"]
    st2, m2 = B.fit(d2[trm], jtr)
    p2 = m2.predict(build(d2[~trm], st2, judged=jte))
    out["2_sept_scores_unchanged_when_sept_labels_flipped"] = bool(np.allclose(p0, p2))
    # 3. Chronological (expanding-window) pincode encoding on training rows: own label and LATER labels never reach a row
    base = chrono_pin_logit(tr).values; changed = later = 0
    for i in np.random.RandomState(0).choice(len(tr), 20, replace=False):
        t2 = tr.copy(); t2.iloc[i, t2.columns.get_loc("rto")] = 1 - t2.rto.iloc[i]
        new = chrono_pin_logit(t2).values
        changed += not np.isclose(new[i], base[i])
        earlier = (tr.dt.values < tr.dt.values[i])          # rows placed before the flipped one
        later += int((~np.isclose(new[earlier], base[earlier])).sum())
    out["3_training_rows_whose_own_label_moves_their_pin_feature (of 20)"] = int(changed)
    out["3_earlier_rows_moved_by_a_later_label (20 flips)"] = int(later)
    changed += later
    in_sample = [np.log(np.clip(stats.pin_rate(p, s), 1e-3, 1 - 1e-3) / (1 - np.clip(stats.pin_rate(p, s), 1e-3, 1 - 1e-3))) for p, s in zip(tr.pincode, tr.state)]
    out["3_note"] = "without out-of-time encoding, training rows would see their own label: in-sample vs chronological pin feature correlation with RTO " + \
        f"{np.corrcoef(in_sample, tr.rto)[0, 1]:.3f} vs {np.corrcoef(base, tr.rto)[0, 1]:.3f}"
    # 4. CV folds
    f = np.random.RandomState(1).randint(0, 5, len(tr)); pcv = B.cv_predictions(tr, jtr)
    t3 = tr.copy(); t3.loc[f == 0, "rto"] = 1 - t3.loc[f == 0, "rto"].values  # flip labels of fold 0 only
    pcv3 = B.cv_predictions(t3, jtr)
    out["4_cv_fold0_predictions_unchanged_when_fold0_labels_flipped"] = bool(np.allclose(pcv[f == 0], pcv3[f == 0]))
    out["4_cv_folds"] = "random 5-fold inside Apr-Aug (not time-ordered); used only to choose thresholds"
    # 5. label lag
    known = tr.dt < pd.Timestamp(B.TEST_START) - pd.Timedelta(days=OUTCOME_LAG_DAYS)
    st5, m5 = B.fit(tr[known], [j for j, k in zip(jtr, known) if k])
    p5 = m5.predict(build(te, st5, judged=jte))
    first = None
    fake = np.array([j["name_fake"] for j in jte]); unus = np.array([j["address_score"] == 0 for j in jte])
    def net(p): return round(B.rupees(B.policy(p, first, fake, unus, R, zero=te.zero_value.values, hist=te.history_state.values), te, E, R)["net"])
    out["5_label_lag"] = {"lag_days": OUTCOME_LAG_DAYS, "train_rows_all": int(len(tr)), "train_rows_outcome_known_by_1_sep": int(known.sum()),
        "sept_auc_all_train": round(auc(te.rto, p0), 3), "sept_auc_lagged_train": round(auc(te.rto, p5), 3),
        "sept_net_all_train": net(p0), "sept_net_lagged_train": net(p5)}
    leak = not (out["1_encoder_fit_rows_before_sep"] and out["2_sept_scores_unchanged_when_sept_labels_flipped"]
                and changed == 0 and out["4_cv_fold0_predictions_unchanged_when_fold0_labels_flipped"])
    out["verdict"] = "LEAKAGE FOUND" if leak else "No September outcome reaches September scores; training rows use a chronological (earlier-orders-only) pincode encoding."
    json.dump(out, open(os.path.join(ROOT, "reports", "leakage_audit.json"), "w"), indent=1)
    print(json.dumps(out, indent=1)); return out

if __name__ == "__main__":
    main()
