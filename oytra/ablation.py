"""Feature ablation on the identical split (train Apr-Aug, test Sep): drop one feature or group, refit, re-score.
Same thresholds/policy as production, so September net Rs is comparable. -> reports/ablation.json / .md
Run: python -m oytra.ablation"""
import os, json
import numpy as np
from .config import load_rules, load_econ, ROOT
from .data import load
from .features import FEATURES, HISTORY_FEATURES
from .llm import RuleJudge
from .variants import run_variant
from . import metrics as M

GROUPS = {
    "group: customer history (reported)": HISTORY_FEATURES,
    "group: area (pincode/state RTO rate)": ["pin_logit"],
    "group: address / name / phone quality": ["address_score", "name_fake", "phone_invalid"],
    "group: order value + night-time": ["value_k", "night"],
    "group: basket (single item)": ["single_item"],
}

def main():
    R, E = load_rules(), load_econ(); df = load(); J = [RuleJudge().judge(r.customer_name, r.address, r.city, r.pincode) for r in df.itertuples()]
    rows = []
    for name, drop in [("full model (production)", [])] + [(f"drop {f}", [f]) for f in FEATURES] + list(GROUPS.items()):
        p, y, r = run_variant(df, J, drop, [], R, E)
        rows.append({"variant": name, "dropped": drop, "test_auc": r["test_auc"], "pr_auc": round(M.average_precision(y, p), 3),
                     "brier": round(M.brier(y, p), 4), "september_net_rupees": r["september_net_rupees_base_case"]})
    base = rows[0]
    for r in rows: r["delta_auc"] = round(r["test_auc"] - base["test_auc"], 3); r["delta_net"] = r["september_net_rupees"] - base["september_net_rupees"]
    out = {"split": "train Apr-Aug (1,658), test Sep (329); thresholds 0.4/0.6/0.875 from rules.csv; base-case Rs assumptions",
           "note": "One September month (86 RTOs): AUC differences under ~0.01 and Rs differences of a few hundred are within noise.",
           "rows": rows}
    json.dump(out, open(os.path.join(ROOT, "reports", "ablation.json"), "w"), indent=1)
    md = ["# Feature ablation (same Apr–Aug → Sep split)", "", out["note"], "",
          "| Variant | AUC | ΔAUC | PR-AUC | Brier | Sep net ₹ | Δ₹ |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['variant']} | {r['test_auc']:.3f} | {r['delta_auc']:+.3f} | {r['pr_auc']:.3f} | {r['brier']:.4f} | {r['september_net_rupees']:,} | {r['delta_net']:+,} |" for r in rows]
    open(os.path.join(ROOT, "reports", "ablation.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md)); return out

if __name__ == "__main__":
    main()
