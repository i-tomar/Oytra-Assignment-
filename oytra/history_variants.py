"""Which customer-history model? Chosen by CHRONOLOGICAL validation inside Apr-Aug only.
Folds: train Apr-May -> test Jun; Apr-Jun -> Jul; Apr-Jul -> Aug. September is NOT used for selection.
Models: no_history | reported_history | history_quality_flag (history zeroed when UNKNOWN_OR_INCONSISTENT + flag).
Selection rule (fixed before running): start from the simplest model; a more complex model replaces it only if it
  (a) raises mean ROC-AUC by >= 0.01, (b) wins AUC in a majority of folds (2 of 3), and (c) does not worsen mean Brier.
Otherwise the difference is treated as noise and the simpler model is kept.
Then the chosen model is scored on September: a RETROSPECTIVE temporal holdout (used during development), not untouched.
Run: python -m oytra.history_variants -> reports/history_model_selection.{json,md}"""
import os, json, numpy as np
from .config import load_rules, load_econ, ROOT
from .data import load
from .llm import RuleJudge
from .features import HISTORY_MODELS, SIMPLICITY_ORDER, build
from .model import auc
from .policy import apply_policy
from . import metrics as M

FOLDS = [("2026-04-01", "2026-06-01", "2026-07-01"), ("2026-04-01", "2026-07-01", "2026-08-01"), ("2026-04-01", "2026-08-01", "2026-09-01")]
AUC_MARGIN = 0.01

def evaluate(df, J, feats, start, end, R, E):
    from .backtest import fit, rupees
    trm = (df.dt < start).values; tem = ((df.dt >= start) & (df.dt < end)).values
    tr, te = df[trm], df[tem]
    jtr = [j for j, m in zip(J, trm) if m]; jte = [j for j, m in zip(J, tem) if m]
    st, mod = fit(tr, jtr, feats)
    p = mod.predict(build(te, st, judged=jte)); y = te.rto.values
    fake = np.array([j["name_fake"] for j in jte], bool); unus = np.array([j["address_score"] == 0 for j in jte], bool)
    a = apply_policy(p, te.history_state.values, fake, unus, te.zero_value.values, R)
    return p, {"train_orders": int(trm.sum()), "test_orders": int(tem.sum()), "test_rto": int(y.sum()),
               "roc_auc": round(auc(y, p), 3), "pr_auc": round(M.average_precision(y, p), 3), "brier": round(M.brier(y, p), 4),
               "ece": round(M.ece(y, p), 3), "net_rupees_base_HYPOTHETICAL": round(rupees(a, te, E, R)["net"])}

def select(df, J, R, E, folds=FOLDS):
    res = {}
    for name in SIMPLICITY_ORDER:
        rows = []
        for f in folds:
            _, r = evaluate(df, J, HISTORY_MODELS[name], f[1], f[2], R, E)
            r["fold"] = f"train <{f[1]} -> test {f[1][:7]}"; rows.append(r)
        res[name] = {"folds": rows, **{f"mean_{k}": round(float(np.mean([r[k] for r in rows])), 4) for k in ["roc_auc", "pr_auc", "brier", "ece", "net_rupees_base_HYPOTHETICAL"]}}
    chosen, why = SIMPLICITY_ORDER[0], []
    for cand in SIMPLICITY_ORDER[1:]:
        a, b = res[cand], res[chosen]
        gain = a["mean_roc_auc"] - b["mean_roc_auc"]
        wins = sum(x["roc_auc"] > z["roc_auc"] for x, z in zip(a["folds"], b["folds"]))
        ok = gain >= AUC_MARGIN and wins * 2 > len(folds) and a["mean_brier"] <= b["mean_brier"] + 1e-4
        why.append(f"{cand} vs {chosen}: mean AUC {gain:+.3f}, wins {wins}/3 folds, mean Brier {a['mean_brier'] - b['mean_brier']:+.4f} -> "
                   + (f"switch to {cand}" if ok else f"within noise / not better, keep {chosen}"))
        if ok: chosen = cand
    return chosen, res, why

def main():
    R, E = load_rules(), load_econ(); df = load(); j = RuleJudge()
    J = [j.judge(r.customer_name, r.address, r.city, r.pincode) for r in df.itertuples()]
    chosen, res, why = select(df, J, R, E)
    p, sep = evaluate(df, J, HISTORY_MODELS[chosen], "2026-09-01", "2026-10-01", R, E)
    sep_all = {n: evaluate(df, J, HISTORY_MODELS[n], "2026-09-01", "2026-10-01", R, E)[1] for n in SIMPLICITY_ORDER}
    out = {"selection_rule": __doc__.split("Selection rule")[1].split("Then")[0].strip(), "folds": [f"{a[:7]}..{b[:7]} -> {b[:7]}" for a, b, c in FOLDS],
           "results": res, "decision_trail": why, "selected_model": chosen,
           "september_retrospective_holdout": {"label": "retrospective temporal holdout (used during development), not an untouched test set",
                                               "selected": sep, "all_models_for_reference_not_used_for_selection": sep_all},
           "future_work": "A stable Shopify customer ID (instead of phone) would make history_state far more reliable."}
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "reports", "history_model_selection.json"), "w"), indent=1)
    md = ["# History model selection (chronological validation inside Apr–Aug)", "",
          "ROC-AUC / Brier / ECE are model metrics; ₹ is base-case HYPOTHETICAL at fixed 40/60/87.5 thresholds.", "",
          "| Model | Jun AUC | Jul AUC | Aug AUC | mean AUC | mean PR-AUC | mean Brier | mean ECE | mean ₹/month (hyp.) |", "|---|---|---|---|---|---|---|---|---|"]
    for n in SIMPLICITY_ORDER:
        r = res[n]; md.append(f"| {n} | " + " | ".join(f"{x['roc_auc']:.3f}" for x in r["folds"]) +
                              f" | {r['mean_roc_auc']:.3f} | {r['mean_pr_auc']:.3f} | {r['mean_brier']:.4f} | {r['mean_ece']:.3f} | {r['mean_net_rupees_base_HYPOTHETICAL']:,.0f} |")
    md += ["", "Training sizes per fold: " + ", ".join(f"{x['fold']}: {x['train_orders']} train / {x['test_orders']} test" for x in res[chosen]["folds"]), "",
           "Decision trail:", ""] + [f"- {w}" for w in why] + ["", f"**Selected: `{chosen}`**", "",
           "## September — retrospective temporal holdout (used during development), not an untouched test set", "",
           "| Model | AUC | PR-AUC | Brier | ECE | ₹ base (hyp.) |", "|---|---|---|---|---|---|"]
    md += [f"| {n}{' (selected)' if n == chosen else ''} | {r['roc_auc']:.3f} | {r['pr_auc']:.3f} | {r['brier']:.4f} | {r['ece']:.3f} | {r['net_rupees_base_HYPOTHETICAL']:,} |" for n, r in sep_all.items()]
    md += ["", "Future work: Shopify customer ID instead of phone as the customer key."]
    open(os.path.join(ROOT, "reports", "history_model_selection.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md)); return out

if __name__ == "__main__":
    main()
