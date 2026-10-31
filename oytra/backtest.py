"""Train on Apr-Aug, pick thresholds by rupees (cross-validated on train), test on September.
Run: python -m oytra.backtest [--write-config]"""
import os, sys, json, pickle, itertools
import numpy as np, pandas as pd
from .config import load_rules, load_econ, ROOT
from .data import load
from .features import HistoryStats, build, chrono_pin_logit
from .model import RiskModel, auc
from .llm import RuleJudge
from .economics import breakdown, LABEL, SCENARIOS, ACTIONS
from .policy import apply_policy, band, FIRST, RETURNING, UNKNOWN
from .engine import Engine, MODEL_PATH, model_version
from . import metrics as M

TEST_START = "2026-09-01"

def selected_features():
    """Production feature set = the history model chosen by chronological validation inside Apr-Aug
    (reports/history_model_selection.json, written by oytra.history_variants). Falls back to reported history."""
    from .features import HISTORY_MODELS
    f = os.path.join(ROOT, "reports", "history_model_selection.json")
    name = json.load(open(f))["selected_model"] if os.path.exists(f) else "reported_history"
    return name, HISTORY_MODELS[name]

def fit(train, judged, features=None):
    """Pincode encoder for the model's TRAINING rows is chronological (expanding window, earlier orders only).
    The returned stats (fit on all of train) score later orders."""
    stats = HistoryStats().fit(train)
    X = build(train, stats, judged=judged)
    X["pin_logit"] = chrono_pin_logit(train).values
    return stats, RiskModel(features=features or selected_features()[1]).fit(X, train.rto.values)

def _hist(df, first=None):
    if "history_state" in df: return df.history_state.values
    return np.where(first, FIRST, RETURNING)

def policy(p, first, fake, unusable, R, ops=False, pin_rate=None, zero=None, hist=None):
    """Thin wrapper over policy.apply_policy (the ONE precedence function, shared with the engine).
    `hist` = history_state per order; if omitted it is derived from `first` (first-time vs returning)."""
    if ops: return band(p, R)
    if hist is None: hist = np.where(np.asarray(first, bool), FIRST, RETURNING)
    return apply_policy(np.asarray(p, float), hist, fake, unusable, zero, R)

def _components(df, econ, R):
    """breakdown() for every order x action, computed once (vectorised lookups for the threshold grid)."""
    out = {}
    for a in ACTIONS:
        out[a] = np.array([tuple(breakdown(a, y, v, f, econ, R)) for y, v, f in
                           zip(df.rto, df.order_value, _hist(df, df.customer_prior_orders == 0) == FIRST)])
    return out

def rupees(actions, df, econ, R, comp=None):
    """Hindsight rupees vs ship-everything, using the SAME breakdown() as economics.value()."""
    comp = comp or _components(df, econ, R); actions = np.asarray(actions)
    m = np.zeros((len(df), 4))
    for a in ACTIONS: m[actions == a] = comp[a][actions == a]
    s, pdc, l, c = m.sum(0)
    return {"rto_cost_avoided": float(s), "prepaid_delivered_contribution": float(pdc), "lost_genuine": float(l),
            "flow_costs": float(c), "net": float(s + pdc - l - c)}

def cv_predictions(train, judged, folds=5, features=None):
    p = np.zeros(len(train)); f = np.random.RandomState(1).randint(0, folds, len(train))
    for k in range(folds):
        tr, te = train[f != k], train[f == k]
        st, m = fit(tr, [judged[i] for i in np.where(f != k)[0]], features)
        p[f == k] = m.predict(build(te, st, judged=[judged[i] for i in np.where(f == k)[0]]))
    return p

def search_thresholds(p, df, judged, econ, R):
    """Diagnostic only: thresholds stay 40/60/87.5 (tuned policy choice); this reports what a rupee
    optimiser would pick on Apr-Aug under the CURRENT economics."""
    hist = _hist(df, df.customer_prior_orders == 0)
    fake = np.array([j["name_fake"] for j in judged]); unus = np.array([j["address_score"] == 0 for j in judged])
    comp = _components(df, econ, R)
    grid = np.round(np.arange(0.05, 0.96, 0.025), 3)
    best = None
    for a, b, c in itertools.combinations_with_replacement(grid, 3):
        r = {**R, "ship_below_risk": a, "confirm_below_risk": b, "nudge_below_risk": c}
        net = rupees(apply_policy(p, hist, fake, unus, df.zero_value.values, r), df, econ, r, comp)["net"]
        if best is None or net > best[0] + 1e-6: best = (net, a, b, c)
    return best

def main(write_config=False):
    econ, R = load_econ(), load_rules()
    rep = {}; df = load(report=rep)
    judge = RuleJudge()   # backtest is deterministic & offline: RuleJudge ALWAYS, whatever API keys are set
    judged_all = [judge.judge(r.customer_name, r.address, r.city, r.pincode) for r in df.itertuples()]
    tr_m = (df.dt < TEST_START).values
    train, test = df[tr_m], df[~tr_m]
    jtr = [j for j, m in zip(judged_all, tr_m) if m]; jte = [j for j, m in zip(judged_all, tr_m) if not m]
    sel_name, feats = selected_features()
    stats, model = fit(train, jtr, feats)
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    pickle.dump((stats, model), open(MODEL_PATH, "wb"))

    p_cv = cv_predictions(train, jtr, features=feats)
    best = search_thresholds(p_cv, train, jtr, econ, R)
    rec = {"ship_below_risk": float(best[1]), "confirm_below_risk": float(best[2]), "nudge_below_risk": float(best[3])}
    print("Diagnostic: rupee-optimal thresholds on Apr-Aug CV under current economics:", rec, "(NOT applied; policy stays 40/60/87.5)")
    if write_config:
        rows = pd.read_csv(os.path.join(ROOT, "config", "rules.csv"), dtype=str)
        for k, v in rec.items(): rows.loc[rows.setting == k, "value"] = str(v)
        rows.to_csv(os.path.join(ROOT, "config", "rules.csv"), index=False)
        R = load_rules()

    eng = Engine(stats, model, R, econ, judge)
    dec = eng.decide_frame(test, judged=jte)
    p_te = dec.risk.values.astype(float)
    hist = test.history_state.values; first = hist == FIRST
    fake = np.array([j["name_fake"] for j in jte]); unus = np.array([j["address_score"] == 0 for j in jte])
    zero = test.zero_value.values
    p_raw = model.predict(build(test, stats, judged=jte))
    assert (apply_policy(p_raw, hist, fake, unus, zero, R) == dec.action.values).all(), "engine and backtest policy diverged"
    pin_rate = np.array([stats.pin_rate(pc, s) for pc, s in zip(test.pincode, test.state)])
    ops_actions = np.where((p_raw >= 0.38) | (pin_rate >= 0.40) | fake | unus, "HOLD", "SHIP").astype(object)
    y = test.rto.values
    res = {
        "labels": {"[M]": "measured from the CSV", "model": "model prediction", "HYPOTHETICAL": "depends on assumed intervention rates (rules.csv) - simulated, not observed"},
        "data_cleaning": rep,
        "history_state_counts_all_rows": df.history_state.value_counts().to_dict(),
        "train": {"from": str(train.dt.min().date()), "to": str(train.dt.max().date()), "orders": len(train), "rto_rate": round(train.rto.mean(), 4)},
        "test": {"from": str(test.dt.min().date()), "to": str(test.dt.max().date()), "orders": len(test), "rto_rate": round(test.rto.mean(), 4),
                 "rto_orders": int(y.sum()),
                 "label": "retrospective temporal holdout (used during development), not an untouched test set"},
        "model_version": model_version(),
        "model": {"history_model": sel_name, "features": feats, "test_auc": round(auc(y, p_raw), 3), "cv_auc_train_random_folds": round(auc(train.rto, p_cv), 3),
                  "weights_standardised": model.weights(),
                  "training_pin_encoding": "chronological expanding window (weekly blocks, earlier orders only)"},
        "calibration_test_by_quintile": [
            {"mean_pred": round(g.p.mean(), 3), "actual": round(g.y.mean(), 3), "n": len(g)}
            for _, g in pd.DataFrame({"p": p_raw, "y": y}).assign(q=lambda d: pd.qcut(d.p, 5, labels=False)).groupby("q")],
        "optimizer_diagnostic_thresholds_not_applied": rec, "optimizer_train_cv_net_rupees": round(best[0]),
        "thresholds": {k: R[k] for k in ["ship_below_risk", "confirm_below_risk", "nudge_below_risk"]},
        "september": {},
    }
    cac = econ["cac"]
    for name, acts in [("our_rules", dec.action.values), ("ship_everything (Marketing)", np.array(["SHIP"] * len(test))),
                       ("ops_cancel_risky (Operations)", ops_actions)]:
        r = rupees(acts, test, econ, R)
        cnt = pd.Series(acts).value_counts().to_dict()
        rto_by = pd.Series(y).groupby(acts).agg(["sum", "count"]).to_dict("index")
        held_first = int(((acts == "HOLD") & first).sum())
        res["september"][name] = {**{k: round(v) for k, v in r.items()}, "counts": {LABEL[k]: int(v) for k, v in cnt.items()},
            "rto_in_bucket": {LABEL[k]: f"{int(v['sum'])}/{int(v['count'])}" for k, v in rto_by.items()},
            "first_time_labelled_held_or_cancelled": held_first,
            "marketing_metric_acquisition_spend_on_held_first_time_rupees": held_first * cac,
            "genuine_cancelled": int(((acts == "HOLD") & (y == 0)).sum())}
    res["marketing_metric_note"] = (f"[M] count of first-time-labelled customers held/cancelled x Rs {cac} CAC = acquisition spend already sunk "
                                    "on customers we then turn away. A Marketing cost-of-friction metric, NOT profit and NOT added to net.")
    res["september_estimated_scenarios"] = {}
    for name, sc in SCENARIOS.items():
        r2 = {**R, **sc}
        ours = rupees(policy(p_raw, None, fake, unus, r2, zero=zero, hist=hist), test, econ, r2)
        res["september_estimated_scenarios"][name] = {"assumptions": sc, "label": "HYPOTHETICAL",
            "our_rules_net": round(ours["net"]), "our_rules_components": {k: round(v) for k, v in ours.items()},
            "ops_rule_net": round(rupees(ops_actions, test, econ, r2)["net"]), "ship_everything_net": 0}
    r2 = {**R, "assumed_future_contribution_first_time_rupees": 300}
    res["hypothetical_sensitivity_not_base_case"] = [{"what": "IF a delivered first-time order were worth +Rs 300 future contribution (unvalidated; CAC is spend, not value)",
        "our_rules": round(rupees(dec.action.values, test, econ, r2)["net"]), "ops_rule": round(rupees(ops_actions, test, econ, r2)["net"])}]
    acts = dec.action.values
    bands = {}
    for a in ACTIONS:
        m = acts == a
        bands[LABEL[a]] = {"orders": int(m.sum()), "rto": int(y[m].sum()), "delivered": int((m & (y == 0)).sum()),
                           "rto_rate": round(float(y[m].mean()), 3) if m.any() else None,
                           "share_of_all_rto": round(float(y[m].sum() / y.sum()), 3)}
    flag = acts != "SHIP"
    tp, fp, fn, tn = int((flag & (y == 1)).sum()), int((flag & (y == 0)).sum()), int((~flag & (y == 1)).sum()), int((~flag & (y == 0)).sum())
    cuts = []
    for t in [R["ship_below_risk"], R["confirm_below_risk"], R["nudge_below_risk"]]:
        f2 = p_raw >= t; tp2 = int((f2 & (y == 1)).sum())
        cuts.append({"risk_at_least": t, "orders_flagged": int(f2.sum()), "rto_caught": tp2,
                     "precision": round(tp2 / max(f2.sum(), 1), 3), "recall": round(tp2 / y.sum(), 3)})
    res["september_measured"] = {
        "note": "[M] Facts from the CSV only. 'Flagged' = routed to confirm/nudge/hold; NOT 'prevented' - what the intervention would have changed is HYPOTHETICAL.",
        "orders": len(test), "rto_orders": int(y.sum()), "rto_cost_if_ship_all": round(float(y.sum() * econ["rto_loss"])),
        "by_action": bands,
        "flagged_vs_shipped_confusion": {"flagged_and_rto": tp, "flagged_but_delivered": fp, "shipped_and_rto": fn, "shipped_and_delivered": tn,
                                         "precision": round(tp / max(tp + fp, 1), 3), "recall": round(tp / max(tp + fn, 1), 3),
                                         "f1": round(2 * tp / max(2 * tp + fp + fn, 1), 3)},
        "by_risk_cutoff": cuts,
        "rto_cost_sitting_in_flagged_orders": round(tp * econ["rto_loss"]),
        "first_time_labelled_flagged": int((flag & first).sum()), "first_time_labelled_cancelled": int(((acts == "HOLD") & first).sum()),
        "unknown_history_orders": int((hist == UNKNOWN).sum()),
        "policy_vs_best_ev_disagreements": int((dec.best_ev_action.values != acts).sum()),
    }
    res["model"]["september_metrics"] = M.summary(y, p_raw)   # unrounded scores (engine output rounds to 3dp)
    res["september_risk_buckets"] = M.risk_buckets(y, p_raw)
    svg = M.calibration_svg(res["september_risk_buckets"], os.path.join(ROOT, "reports", "calibration.svg"))
    res["calibration_chart"] = {"svg": "reports/calibration.svg",
                                "png": "reports/calibration.png" if M.svg_to_png(svg, os.path.join(ROOT, "reports", "calibration.png")) else None}
    cod_month = econ["monthly_orders"] * econ["cod_share"]
    res["scale_to_brief"] = {"cod_orders_per_month": cod_month,
        "net_per_cod_order": round(res["september"]["our_rules"]["net"] / len(test), 1),
        "monthly_net_at_1650_cod_orders": round(res["september"]["our_rules"]["net"] / len(test) * cod_month),
        "note": "HYPOTHETICAL PROJECTION: September base-case net per COD order x brief volume. One month; see walk-forward for month-to-month swings (incl. negative months)."}
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    json.dump(res, open(os.path.join(ROOT, "reports", "backtest.json"), "w"), indent=2, default=str)
    out = pd.concat([test[["order_id", "order_datetime", "customer_name", "address", "state", "pincode", "order_value",
                           "customer_prior_orders", "customer_prior_rto", "utm_source", "status"]].reset_index(drop=True),
                     dec.drop(columns=["order_id"]).reset_index(drop=True)], axis=1)
    out.to_csv(os.path.join(ROOT, "reports", "september_decisions.csv"), index=False)
    print(json.dumps({k: res[k] for k in ["test", "model", "september", "september_measured", "september_estimated_scenarios"]}, indent=1, default=str))
    return res

if __name__ == "__main__":
    main("--write-config" in sys.argv)
