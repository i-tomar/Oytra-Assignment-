"""Model-variant experiments (out-of-time: train Apr-Aug, test Sep) -> reports/model_variants.json
  1. Customer-history audit: reported customer_prior_* columns vs history rebuilt from this file.
  2. Does adding product-presence / item-count features help?
Run: python -m oytra.variants"""
import os, json
import numpy as np, pandas as pd
from .config import load_rules, load_econ, ROOT
from .data import load, OUTCOME_LAG_DAYS
from .features import FEATURES, PRODUCT_FEATURES, HISTORY_FEATURES, INDATA_HISTORY_FEATURES, HistoryStats, build, chrono_pin_logit
from .model import RiskModel, auc
from .llm import RuleJudge
from .backtest import TEST_START, policy, rupees

VARIANTS = {
    "production (reported history)": ([], []),
    "no customer history": (HISTORY_FEATURES, []),
    "history rebuilt from this file only": (HISTORY_FEATURES, INDATA_HISTORY_FEATURES),
    "reported + rebuilt history": ([], INDATA_HISTORY_FEATURES),
    "+ 8 product flags": ([], PRODUCT_FEATURES),
    "+ item count (numeric)": ([], ["n_items"]),
}

def _X(d, st, jj, feats, oof=False):
    X = build(d, st, judged=jj)
    if oof: X["pin_logit"] = chrono_pin_logit(d).values   # training rows: earlier orders only
    X["n_items"] = d.num_items.values
    return X

def run_variant(df, J, drop, extra, R, E):
    feats = [f for f in FEATURES if f not in drop] + extra
    m = (df.dt < TEST_START).values; tr, te = df[m], df[~m]
    jt = [x for x, k in zip(J, m) if k]; je = [x for x, k in zip(J, m) if not k]
    st = HistoryStats().fit(tr)
    mod = RiskModel(features=feats).fit(_X(tr, st, jt, feats, True), tr.rto.values)
    p, y = mod.predict(_X(te, st, je, feats)), te.rto.values
    f = np.random.RandomState(1).randint(0, 5, len(tr)); pc = np.zeros(len(tr))
    for k in range(5):
        a, b = tr[f != k], tr[f == k]; s2 = HistoryStats().fit(a)
        mm = RiskModel(features=feats).fit(_X(a, s2, [jt[i] for i in np.where(f != k)[0]], feats, True), a.rto.values)
        pc[f == k] = mm.predict(_X(b, s2, [jt[i] for i in np.where(f == k)[0]], feats))
    fake = np.array([x["name_fake"] for x in je]); unus = np.array([x["address_score"] == 0 for x in je])
    net = rupees(policy(p, None, fake, unus, R, zero=te.zero_value.values, hist=te.history_state.values), te, E, R)["net"]
    q = pd.qcut(p, 5, labels=False)
    return p, y, {"test_auc": round(auc(y, p), 3), "cv_auc_train": round(auc(tr.rto.values, pc), 3),
                  "brier": round(float(np.mean((p - y) ** 2)), 4),
                  "top_quintile_pred_vs_actual": [round(float(p[q == 4].mean()), 3), round(float(y[q == 4].mean()), 3)],
                  "september_net_rupees_base_case": round(net)}

def history_audit(df):
    later = df[df.indata_prior_orders > 0]
    no_hist = df[df.indata_prior_orders == 0]
    return {
        "phones_with_more_than_one_order": int((df.groupby("phone10").size() > 1).sum()),
        "orders_on_those_phones": int(df.phone10.map(df.phone10.value_counts()).gt(1).sum()),
        "reported_prior_orders_below_orders_visible_in_file": int((df.customer_prior_orders < df.indata_prior_orders).sum()),
        "reported_first_time_but_earlier_order_in_file": int(((df.customer_prior_orders == 0) & (df.indata_prior_orders > 0)).sum()),
        "phones_where_reported_prior_orders_goes_down": int(sum(not g.customer_prior_orders.is_monotonic_increasing
                                                               for _, g in df.groupby("phone10") if len(g) > 1)),
        "later_orders_after_an_rto_in_file": int((later.indata_prior_rto > 0).sum()),
        "   of_which_report_prior_rto_above_0": int(((later.indata_prior_rto > 0) & (later.customer_prior_rto > 0)).sum()),
        "rows_prior_rto_gt_prior_orders": int((df.customer_prior_rto > df.customer_prior_orders).sum()),
        "   of_which_rto": int(df[df.customer_prior_rto > df.customer_prior_orders].rto.sum()),
        "rto_rate_by_reported_prior_rto_when_file_shows_no_history": {
            str(k): f"{int(g.rto.sum())}/{len(g)}" for k, g in no_hist.groupby(no_hist.customer_prior_rto.clip(0, 2))},
        "rto_rate_after_previous_order_in_file": {
            "previous_delivered": round(float(df[(df.indata_prior_orders > 0) & (df.indata_prior_rto == 0)].rto.mean()), 3),
            "previous_rto_known": round(float(later[later.indata_prior_rto > 0].rto.mean()), 3)},
        "outcome_lag_days_used": OUTCOME_LAG_DAYS,
    }

def main():
    df, R, E = load(), load_rules(), load_econ(); j = RuleJudge()
    J = [j.judge(r.customer_name, r.address, r.city, r.pincode) for r in df.itertuples()]
    out, preds = {"history_audit": history_audit(df), "variants": {}}, {}
    for name, (drop, extra) in VARIANTS.items():
        preds[name], y, out["variants"][name] = run_variant(df, J, drop, extra, R, E)
    rng, base = np.random.RandomState(0), preds["production (reported history)"]
    for name in ["no customer history", "+ 8 product flags"]:
        d = []
        for _ in range(1000):
            i = rng.randint(0, len(y), len(y)); d.append(auc(y[i], preds[name][i]) - auc(y[i], base[i]))
        out["variants"][name]["test_auc_change_95pct_ci"] = [round(float(x), 3) for x in np.percentile(d, [2.5, 97.5])]
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "reports", "model_variants.json"), "w"), indent=1)
    print(json.dumps(out, indent=1)); return out

if __name__ == "__main__":
    main()
