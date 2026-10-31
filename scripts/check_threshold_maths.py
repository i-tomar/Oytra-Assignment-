"""Recompute every number quoted in docs/THRESHOLD_MATHS.md from code + data and check the doc quotes them.
Run: PYTHONPATH=. python scripts/check_threshold_maths.py   (also run by the tests)
Model-based September numbers are read from reports/backtest.json, which oytra.backtest writes from code."""
import os, sys, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from oytra.config import load_rules, load_econ, ROOT
from oytra.data import load
from oytra.economics import delivered_value, value
from oytra.policy import FIRST

def crossing(a, b, v, E, R):
    """Smallest risk p (0.1% grid) at which action a is worth at least action b, or None."""
    for p in np.arange(0, 1.0005, 0.001):
        if value(a, p, v, False, E, R) >= value(b, p, v, False, E, R): return round(100 * p, 1)
    return None

def compute():
    E, R = load_econ(), load_rules(); n = {}
    L = E["rto_loss"]; aov = E["brief_aov"]
    raw = pd.read_csv(os.path.join(ROOT, "data", "orders_sample.csv"))
    df = load()
    n["L"] = round(L, 1)
    n["mean_after_dedupe"] = round(raw.drop_duplicates().order_value.mean(), 2)
    n["mean_labelled"] = round(df.order_value.mean(), 2); n["median_labelled"] = round(df.order_value.median())
    for tag, v in (("649", aov), ("mean", n["mean_labelled"])):
        V = delivered_value(v, E, R); n[f"V_{tag}"] = round(V, 2)
        n[f"hold_be_{tag}"] = round(100 * V / (V + L), 1)                       # HOLD beats SHIP
        n[f"confirm_be_{tag}"] = crossing("CONFIRM", "SHIP", v, E, R)
        n[f"nudge_be_{tag}"] = crossing("NUDGE", "SHIP", v, E, R)
        n[f"nudge_over_confirm_{tag}"] = crossing("NUDGE", "CONFIRM", v, E, R)
        n[f"hold_over_confirm_{tag}"] = crossing("HOLD", "CONFIRM", v, E, R)
    n["first_time_share_pct"] = round(100 * (df.history_state == FIRST).mean())
    b = json.load(open(os.path.join(ROOT, "reports", "backtest.json")))
    o = b["optimizer_diagnostic_thresholds_not_applied"]
    n["optimiser"] = (o["ship_below_risk"], o["confirm_below_risk"], o["nudge_below_risk"])
    s = b["september"]; n["sep_base"] = s["our_rules"]["net"]; n["sep_ops"] = s["ops_cancel_risky (Operations)"]["net"]
    sc = {k: v["our_rules_net"] for k, v in b["september_estimated_scenarios"].items()}
    n["sep_scenarios"] = sc
    return n

def fmt(v): return f"{v:,}" if isinstance(v, int) else str(v)
def rs(v): return f"−₹{fmt(-v)}" if v < 0 else f"₹{fmt(v)}"

def expected_strings(n):
    out = [f"₹{n['L']}", f"₹{n['mean_after_dedupe']}", f"₹{n['mean_labelled']}", f"₹{n['median_labelled']}", f"{n['first_time_share_pct']}%",
           rs(n["sep_base"]), rs(n["sep_ops"])] + [rs(v) for v in n["sep_scenarios"].values()]
    for t in ("649", "mean"):
        out += [f"₹{n[f'V_{t}']}"] + [f"{n[k]}%" for k in (f"hold_be_{t}", f"confirm_be_{t}", f"nudge_be_{t}", f"nudge_over_confirm_{t}", f"hold_over_confirm_{t}") if n[k] is not None]
    return out

def main():
    n = compute(); doc = open(os.path.join(ROOT, "docs", "THRESHOLD_MATHS.md")).read()
    missing = [s for s in expected_strings(n) if s not in doc]
    for k, v in n.items(): print(f"{k:28s} {v}")
    print("MISSING FROM DOC:" if missing else "All numbers in docs/THRESHOLD_MATHS.md reproduce from code.", missing or "")
    return n, missing

if __name__ == "__main__":
    _, miss = main(); sys.exit(1 if miss else 0)
