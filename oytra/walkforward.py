"""Month-by-month walk-forward, Jun-Sep. Nothing is re-tuned after seeing a test month.
Table A - STABILITY of the fixed policy: production history model + fixed 40/60/87.5 thresholds, model refit on
  all orders before the month. The thresholds and the history-model choice were made using Apr-Aug, so Jun-Aug
  are NOT independent tests; this only shows how stable the fixed policy is month to month.
Table B - GENUINE chronological model+policy evaluation: for each month, using ONLY earlier orders,
  (1) pick the history model with the same rule as oytra.history_variants (inner chronological folds),
  (2) pick thresholds with the same rupee optimiser on those inner out-of-time predictions (base assumptions),
  then apply once to the month.
Table C - argmax-EV comparison (comparison only, never deployed): per order pick the action with the best
  base-case expected Rs, same guardrails (precedence steps 2-5), and an Ops friction cap on confirm+nudge share.
All Rs figures are HYPOTHETICAL (depend on assumed intervention rates); negative months are shown.
Run: python -m oytra.walkforward -> reports/walkforward.{json,md}"""
import os, json, numpy as np, pandas as pd
from .config import load_rules, load_econ, ROOT
from .data import load
from .llm import RuleJudge
from .features import HISTORY_MODELS, build
from .model import auc
from .policy import apply_policy, FIRST, UNKNOWN
from .economics import SCENARIOS, ACTIONS, value
from . import backtest as B, metrics as M, history_variants as H

MONTHS = ["2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"]
NAMES = {"2026-06-01": "Jun", "2026-07-01": "Jul", "2026-08-01": "Aug", "2026-09-01": "Sep"}

def _end(m): return str((pd.Timestamp(m) + pd.offsets.MonthBegin(1)).date())

def _split(df, J, start, end):
    trm = (df.dt < start).values; tem = ((df.dt >= start) & (df.dt < end)).values
    return df[trm], df[tem], [j for j, k in zip(J, trm) if k], [j for j, k in zip(J, tem) if k]

def _flags(jj): return np.array([j["name_fake"] for j in jj], bool), np.array([j["address_score"] == 0 for j in jj], bool)

def _nets(acts, te, E, R):
    return {k: round(B.rupees(acts, te, E, {**R, **sc})["net"]) for k, sc in SCENARIOS.items()}

def argmax_policy(p, te, fake, unus, R, E):
    """Best base-case EV action per order, with the SAME guardrails, then the Ops friction cap."""
    hist, zero, v = te.history_state.values, te.zero_value.values, te.order_value.values
    ev = np.array([[value(a, pi, vi, h == FIRST, E, R) for a in ACTIONS] for pi, vi, h in zip(p, v, hist)])
    protect = ((hist == FIRST) & R["protect_first_time_customers"]) | ((hist == UNKNOWN) & R["protect_unknown_history"])
    ev[protect, 3] = -1e9                                   # no HOLD on risk alone for protected histories
    a = np.array(ACTIONS, object)[ev.argmax(1)]
    holdm = (fake & (R["fake_name_action"] == "hold")) | (unus & (R["unusable_address_action"] == "hold"))
    forced = (fake | unus) & ~holdm; a[forced] = "CONFIRM"; a[holdm] = "HOLD"
    m = zero & np.isin(a, ["NUDGE", "HOLD"]); a[m] = R["zero_value_order_action"].upper(); forced |= m
    cap = int(np.floor(R["ops_max_friction_share"] * len(a)))
    fr = np.isin(a, ["CONFIRM", "NUDGE"]) & ~forced
    room = max(cap - int((np.isin(a, ["CONFIRM", "NUDGE"]) & forced).sum()), 0)
    if fr.sum() > room:
        gain = np.where(fr, ev[np.arange(len(a)), [ACTIONS.index(x) for x in a]] - ev[:, 0], -np.inf)
        keep = np.argsort(-gain)[:room]; drop = fr.copy(); drop[keep] = False; a[drop] = "SHIP"
    return a

def friction(a): return round(float(np.isin(a, ["CONFIRM", "NUDGE"]).mean()), 3)

def main():
    R, E = load_rules(), load_econ(); df = load(); jd = RuleJudge()
    J = [jd.judge(r.customer_name, r.address, r.city, r.pincode) for r in df.itertuples()]
    prod_name, prod_feats = B.selected_features()
    A, Bt, C = [], [], []
    for m in MONTHS:
        tr, te, jtr, jte = _split(df, J, m, _end(m)); y = te.rto.values; fake, unus = _flags(jte)
        st, mod = B.fit(tr, jtr, prod_feats); p = mod.predict(build(te, st, judged=jte))
        acts = apply_policy(p, te.history_state.values, fake, unus, te.zero_value.values, R)
        A.append({"month": NAMES[m], "train_orders": len(tr), "test_orders": len(te), "test_rto": int(y.sum()),
                  "roc_auc": round(auc(y, p), 3), "brier": round(M.brier(y, p), 4), "flagged": int((acts != "SHIP").sum()),
                  "flagged_and_rto": int(((acts != "SHIP") & (y == 1)).sum()), "friction_share": friction(acts),
                  "net_HYPOTHETICAL": _nets(acts, te, E, R)})
        # ---- B: genuine chronological (selection + thresholds from pre-month data only)
        inner_tests = [x for x in ["2026-05-01"] + MONTHS if x < m]
        folds = [("2026-04-01", t, _end(t)) for t in inner_tests]
        chosen, _, _ = H.select(df, J, R, E, folds)
        pp, dd, jj = [], [], []
        for f in folds:
            ptr, pte, pjtr, pjte = _split(df, J, f[1], f[2])
            s2, m2 = B.fit(ptr, pjtr, HISTORY_MODELS[chosen]); pp.append(m2.predict(build(pte, s2, judged=pjte))); dd.append(pte); jj += pjte
        best = B.search_thresholds(np.concatenate(pp), pd.concat(dd), jj, E, R)
        Rb = {**R, "ship_below_risk": best[1], "confirm_below_risk": best[2], "nudge_below_risk": best[3]}
        st, mod = B.fit(tr, jtr, HISTORY_MODELS[chosen]); p2 = mod.predict(build(te, st, judged=jte))
        acts2 = apply_policy(p2, te.history_state.values, fake, unus, te.zero_value.values, Rb)
        Bt.append({"month": NAMES[m], "train_orders": len(tr), "inner_validation_months": [x[:7] for x in inner_tests],
                   "history_model_chosen": chosen, "thresholds_chosen": [float(best[1]), float(best[2]), float(best[3])],
                   "roc_auc": round(auc(y, p2), 3), "brier": round(M.brier(y, p2), 4), "flagged": int((acts2 != "SHIP").sum()),
                   "friction_share": friction(acts2), "net_HYPOTHETICAL": _nets(acts2, te, E, R)})
        # ---- C: argmax-EV vs bands (same model as A)
        am = argmax_policy(p, te, fake, unus, R, E)
        C.append({"month": NAMES[m], "bands_net": A[-1]["net_HYPOTHETICAL"], "argmax_net": _nets(am, te, E, R),
                  "bands_friction_share": friction(acts), "argmax_friction_share": friction(am),
                  "argmax_counts": pd.Series(am).value_counts().to_dict()})
    cells = [(c["month"], k) for c in C for k in SCENARIOS]
    better = sum(c["argmax_net"][k] >= c["bands_net"][k] for c in C for k in SCENARIOS)
    cap_ok = all(c["argmax_friction_share"] <= R["ops_max_friction_share"] + 1e-9 for c in C)
    robust = better == len(cells) and cap_ok
    losing = [f"{c['month']} {k}" for c in C for k in SCENARIOS if c["argmax_net"][k] < c["bands_net"][k]]
    tot = {k: (sum(c["argmax_net"][k] for c in C), sum(c["bands_net"][k] for c in C)) for k in SCENARIOS}
    verdict = (f"argmax-EV >= bands in {better}/{len(cells)} month x scenario cells; Jun-Sep totals argmax vs bands: "
               + ", ".join(f"{k} {a:,} vs {b:,}" for k, (a, b) in tot.items()) + f"; friction cap {R['ops_max_friction_share']:.0%} "
               + ("respected" if cap_ok else "BROKEN") + ". "
               + ("Robustly better, but the 40/60/87.5 bands are kept for now (user instruction); argmax is a pilot candidate."
                  if robust else f"Pre-stated bar (better in every cell) not met: loses {', '.join(losing)}. Argmax is ahead on totals, "
                  "but it decides with the same HYPOTHETICAL rates it is scored on and always runs at the friction cap, so its edge is "
                  "assumption-driven. Bands kept; argmax stays a comparison and pilot candidate."))
    out = {"note": __doc__, "production_history_model": prod_name, "A_fixed_policy_stability": A, "B_chronological_model_and_policy": Bt,
           "C_argmax_vs_bands": C, "C_ops_max_friction_share": R["ops_max_friction_share"], "C_verdict": verdict, "C_robustly_better": robust}
    json.dump(out, open(os.path.join(ROOT, "reports", "walkforward.json"), "w"), indent=1, default=str)
    sc = list(SCENARIOS)
    md = ["# Walk-forward Jun–Sep (no re-tuning after seeing a month)", "",
          "All ₹ are HYPOTHETICAL (assumed WhatsApp/prepaid effects, rules.csv); AUC/Brier are model metrics on real outcomes. Negative months shown as-is.", "",
          "## A. Fixed 40/60/87.5 policy — stability analysis", "",
          "Thresholds and history-model choice were made on Apr–Aug, so **Jun–Aug are not independent tests**. Model refit on all orders before each month.", "",
          "| Month | Train orders | Test orders (RTO) | AUC | Brier | Flagged (of which RTO) | Confirm+nudge share | ₹ conservative | ₹ base | ₹ optimistic |", "|---|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['month']} | {r['train_orders']} | {r['test_orders']} ({r['test_rto']}) | {r['roc_auc']:.3f} | {r['brier']:.4f} | {r['flagged']} ({r['flagged_and_rto']}) | {r['friction_share']:.0%} | " +
           " | ".join(f"{r['net_HYPOTHETICAL'][k]:,}" for k in sc) + " |" for r in A]
    md += ["", "## B. Genuine chronological model + policy evaluation", "",
           "For each month, history model AND thresholds are chosen using only earlier months (inner out-of-time folds), then applied once.", "",
           "| Month | Train orders | Inner validation | Model chosen | Thresholds chosen | AUC | Brier | Flagged | Confirm+nudge share | ₹ conservative | ₹ base | ₹ optimistic |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['month']} | {r['train_orders']} | {', '.join(r['inner_validation_months'])} | {r['history_model_chosen']} | {'/'.join(f'{t:.3f}' for t in r['thresholds_chosen'])} | {r['roc_auc']:.3f} | {r['brier']:.4f} | {r['flagged']} | {r['friction_share']:.0%} | " +
           " | ".join(f"{r['net_HYPOTHETICAL'][k]:,}" for k in sc) + " |" for r in Bt]
    md += ["", f"## C. Argmax-EV (comparison only) vs bands — Ops friction cap {R['ops_max_friction_share']:.0%} of orders", "",
           "Argmax decides with base-case assumptions and is scored under each scenario; same model as table A.", "",
           "| Month | Bands ₹ cons / base / opt | Argmax ₹ cons / base / opt | Bands friction | Argmax friction |", "|---|---|---|---|---|"]
    md += [f"| {c['month']} | " + " / ".join(f"{c['bands_net'][k]:,}" for k in sc) + " | " + " / ".join(f"{c['argmax_net'][k]:,}" for k in sc) +
           f" | {c['bands_friction_share']:.0%} | {c['argmax_friction_share']:.0%} |" for c in C]
    md += ["", f"**Verdict:** {verdict}"]
    open(os.path.join(ROOT, "reports", "walkforward.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md)); return out

if __name__ == "__main__":
    main()
